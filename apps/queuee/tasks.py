import logging
import json
import time
from celery import Task, shared_task
from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
import redis
from .rate_limiter import RateLimiter, RateLimiterUnavailable
from apps.shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Global rate limiter instance (shared across workers)
_rate_limiter = RateLimiter()


class EmailTask(Task):
    """
    Custom task class that overrides on_failure to move failed jobs
    to a dead-letter queue when max retries are exhausted.
    """
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        # Check if this failure is due to exceeding max retries
        if isinstance(exc, MaxRetriesExceededError):
            logger.error(f"Task {task_id} exceeded max retries – moving to dead-letter")
            move_to_dead_letter.delay(task_id, args, kwargs, str(exc))
        else:
            # Other exceptions will be retried automatically
            logger.warning(f"Task {task_id} failed with {exc} – will retry later")
        super().on_failure(exc, task_id, args, kwargs, einfo)


@shared_task(
    bind=True,
    base=EmailTask,                     # Use our custom task class
    autoretry_for=(Exception,),
    retry_backoff=30,                   # 30s, 60s, 120s, 240s, 480s
    retry_backoff_max=600,
    max_retries=5,
    acks_late=True,                     # Critical for SIGKILL resilience
)
def send_email(self, to: str, subject: str, body: str = "", transaction_id: str = None):
    """
    Send a transactional email with rate limiting and retries.
    """
    logger.info(f"Attempting to send email to {to} (task_id={self.request.id})")

    # Step 1: Acquire a token from the rate limiter
    try:
        allowed = _rate_limiter.acquire(identifier="global")
    except RateLimiterUnavailable:
        # Redis is down – fail closed. Retry later (autoretry will catch this).
        raise Exception("Rate limiter unavailable (Redis down)")

    if not allowed:
        # Rate limited – raise so Celery retries later.
        logger.warning(f"Rate limited for {to}, will retry later")
        raise Exception("Rate limit exceeded")

    # Step 2: Send the email (simulated)
    try:
        success = _send_email_to_provider(to, subject, body, transaction_id)
        if not success:
            raise Exception("Email provider returned failure")
        logger.info(f"Email sent successfully to {to}")
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        raise

    return {"to": to, "status": "sent", "task_id": self.request.id}


def _send_email_to_provider(to: str, subject: str, body: str, transaction_id: str) -> bool:
    """Mock email provider – fails intentionally for certain addresses."""
    if "fail@example.com" in to:
        logger.warning(f"Intentional failure for {to}")
        return False
    import random
    if random.random() < 0.05:
        logger.warning(f"Random failure for {to}")
        return False
    return True


# ----- Dead-letter handling -----
@shared_task
def move_to_dead_letter(task_id, args, kwargs, error):
    """Store permanently failed jobs in Redis for manual inspection."""
    redis_client = get_redis_client()
    dead_letter_key = "dead_letter:email"
    payload = {
        "task_id": task_id,
        "args": args,
        "kwargs": kwargs,
        "error": error,
        "timestamp": str(__import__('datetime').datetime.now()),
    }
    redis_client.lpush(dead_letter_key, json.dumps(payload))
    logger.error(f"Moved task {task_id} to dead-letter queue")