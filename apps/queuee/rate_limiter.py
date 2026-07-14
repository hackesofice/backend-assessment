import time
import logging
from typing import Optional
from redis import Redis
from django.conf import settings
from apps.shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Redis key prefixes
TOKEN_BUCKET_KEY = "rate_limiter:token_bucket"
LAST_REFILL_KEY = "rate_limiter:last_refill"


class RateLimiter:
    """
    Token bucket rate limiter using Redis and a Lua script for atomicity.
    Designed to respect a hard limit of 'capacity' tokens per minute.
    """

    # Lua script for atomic check-and-decrement.
    # Returns 1 if token was acquired, 0 if rate limited.
    LUA_SCRIPT = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local capacity = tonumber(ARGV[2])
    local window_seconds = tonumber(ARGV[3])

    -- Token bucket keys
    local tokens_key = key .. ':tokens'
    local refill_key = key .. ':last_refill'

    -- Get current state
    local tokens = redis.call('GET', tokens_key)
    local last_refill = redis.call('GET', refill_key)

    if tokens == false then
        tokens = capacity
    else
        tokens = tonumber(tokens)
    end

    if last_refill == false then
        last_refill = 0
    else
        last_refill = tonumber(last_refill)
    end

    -- Refill if window has elapsed
    if now - last_refill >= window_seconds then
        tokens = capacity
        last_refill = now
    end

    -- Try to consume a token
    if tokens >= 1 then
        tokens = tokens - 1
        redis.call('SET', tokens_key, tokens)
        redis.call('SET', refill_key, last_refill)
        redis.call('EXPIRE', tokens_key, window_seconds * 2)   -- auto-cleanup
        redis.call('EXPIRE', refill_key, window_seconds * 2)
        return 1  -- Allowed
    else
        return 0  -- Rate limited
    end
    """

    def __init__(
        self,
        redis_client: Optional[Redis] = None,
        capacity: int = 200,
        window_seconds: int = 60,
        key_prefix: str = "rate_limiter:email",
    ):
        self.redis = redis_client or get_redis_client()
        self.capacity = capacity
        self.window_seconds = window_seconds
        self.key_prefix = key_prefix

        # Register the Lua script with Redis (cached script SHA)
        self._script_sha = self.redis.script_load(self.LUA_SCRIPT)

    def _get_bucket_key(self, identifier: str = "global") -> str:
        """Return the Redis key for a given bucket (e.g., per-tenant or global)."""
        return f"{self.key_prefix}:{identifier}"

    def acquire(self, identifier: str = "global", timeout: float = 0.1) -> bool:
        """
        Attempt to acquire a token from the bucket.
        Returns True if allowed, False if rate limited.
        Raises RateLimiterUnavailable if Redis is unreachable (fail-closed).
        """
        try:
            key = self._get_bucket_key(identifier)
            now = int(time.time())

            # Execute Lua script atomically
            result = self.redis.evalsha(
                self._script_sha,
                1,  # number of keys
                key,
                now,
                self.capacity,
                self.window_seconds,
            )
            return bool(result)

        except redis.RedisError as e:
            logger.error(f"Redis error in rate limiter: {e}")
            # Fail-closed: raise so the task can retry later
            raise RateLimiterUnavailable("Redis is unavailable") from e

    def reset(self, identifier: str = "global"):
        """Reset the bucket (useful for tests)."""
        key = self._get_bucket_key(identifier)
        self.redis.delete(f"{key}:tokens", f"{key}:last_refill")


class RateLimiterUnavailable(Exception):
    """Raised when Redis cannot be reached – the app fails closed."""
    pass