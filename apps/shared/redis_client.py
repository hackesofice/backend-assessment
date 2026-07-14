import redis
from django.conf import settings

# Singleton Redis client – reused across the app
_redis_client = None


def get_redis_client():
    """Get or create a Redis client instance."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


def get_redis_connection():
    """Alias for get_redis_client (convenience)."""
    return get_redis_client()