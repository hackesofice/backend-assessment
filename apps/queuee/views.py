from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .tasks import send_email


class TriggerEmailQueueView(APIView):
    """
    A simple endpoint to submit a batch of email jobs.
    Used for manual testing and demo.
    """

    def post(self, request):
        count = request.data.get('count', 10)
        emails = request.data.get('emails', None)

        if emails is None:
            # Generate dummy emails
            emails = [f"user{i}@example.com" for i in range(count)]

        submitted = []
        for email in emails:
            task = send_email.delay(
                to=email,
                subject="Order Confirmation",
                body="Your order has been confirmed.",
                transaction_id=f"txn_{email}_{__import__('time').time()}",
            )
            submitted.append({"email": email, "task_id": task.id})

        return Response({
            "submitted": len(submitted),
            "tasks": submitted,
        }, status=status.HTTP_202_ACCEPTED)


class DeadLetterView(APIView):
    """Inspect the dead-letter queue (for debugging)."""

    def get(self, request):
        from apps.shared.redis_client import get_redis_client
        redis_client = get_redis_client()
        items = redis_client.lrange("dead_letter:email", 0, 99)
        return Response({"dead_letter_count": len(items), "items": items})