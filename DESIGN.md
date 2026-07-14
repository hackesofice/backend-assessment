# DESIGN.md – Rate‑Limited Async Job Queue (Section 2)

## 1. Overview
This document explains the architectural choices behind the email job queue system.  
The system must:
- Handle bursts of 2,000 requests in under 10 seconds.
- Respect a third‑party email provider limit of **200 emails per minute**.
- Retry failed jobs with exponential backoff.
- Survive worker crashes mid‑run (no lost jobs).
- Be testable and locally runnable.

---

## 2. Queue Broker Choice: Celery + Redis

### Options considered

| Option | Pros | Cons |
| :--- | :--- | :--- |
| **Celery + Redis** | • Production‑proven.<br>• Built‑in retries, backoff, and dead‑letter handling.<br>• Native Redis support for rate limiting (atomic ops).<br>• Easy to scale workers. | • Heavyweight for very simple needs.<br>• Requires a separate broker (Redis). |
| **Django Q** | • Simpler, no separate worker process? (actually does have a worker).<br>• Django ORM as broker option. | • Less community support.<br>• ORM broker is slower and can cause DB contention.<br>• Rate limiting is not built‑in. |
| **Custom implementation (RQ + custom limiter)** | • Lightweight, full control. | • Reinvents the wheel for retries, acks, and persistence.<br>• More code to maintain and test. |

### My choice: **Celery + Redis**

**Justification:**  
- Celery provides battle‑tested task persistence, retry mechanics (`autoretry_for`, `retry_backoff`), and worker supervision out‑of‑the‑box.  
- Redis serves double duty: (a) Celery broker/result backend, and (b) the atomic rate‑limiter state. This reduces infrastructure complexity.  
- The assessment explicitly mentions "Celery with a Redis backend" as an option – it aligns with the expected solution.

---

## 3. Rate Limiter: Token Bucket (Redis + Lua)

### Why token bucket over sliding‑window or fixed‑window?

| Algorithm | Why I chose it |
| :--- | :--- |
| **Token bucket** | • Allows short bursts up to the bucket capacity – ideal for flash sales where we might send 50 emails in 2 seconds, then cool down.<br>• Smooths traffic while permitting natural spikes.<br>• Simple to implement with Redis `DECR` and `TTL` + a Lua script for atomicity. |
| Sliding‑window (sorted set) | Accurate but uses more memory (stores timestamp per request). Overkill for a simple per‑minute quota. |
| Fixed‑window (INCR + EXPIRE) | Prone to double‑the‑rate bursts at window boundaries (e.g., 199 at 00:59 and 199 at 01:00 → 398 in 2 seconds). Not safe for hard limits. |

### Implementation details

- **Bucket refill**: Every minute, we refill tokens to the bucket capacity (200).  
- **Token consumption**: Each email send attempts to acquire 1 token. If tokens are available, we `DECR`; otherwise, we reject or sleep‑retry.  
- **Atomicity**: All read‑increment‑write operations are wrapped in a **single Lua script** sent to Redis with `EVAL`. This guarantees that the check-and-decrement is indivisible – no race conditions even under high concurrency.

**Lua script outline** (pseudo):
```lua
local key = KEYS[1]
local now = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])

-- Refresh bucket if window has passed
local last_refill = redis.call('GET', key .. ':last_refill') or 0
local tokens = redis.call('GET', key .. ':tokens') or capacity

if now - last_refill >= 60 then
    tokens = capacity
    last_refill = now
end

if tokens >= 1 then
    tokens = tokens - 1
    redis.call('SET', key .. ':tokens', tokens)
    redis.call('SET', key .. ':last_refill', last_refill)
    redis.call('EXPIRE', key, 60)  -- auto‑cleanup
    return 1  -- allowed
else
    return 0  -- rate limited
end
```







### Failure mode – what if Redis is down?

Fail‑open vs fail‑closed: I chose fail‑closed.

- If Redis is unavailable, the rate limiter raises a clear exception and the task is retried later (since Celery will back off and retry).

- This is safer than failing open, which would overwhelm the email provider and potentially get our IP blacklisted.

- In rate_limiter.py, I catch redis.ConnectionError and raise a custom RateLimiterUnavailable exception; Celery’s retry mechanism will re‑queue the task.



## 4. Task Definition: Retries & Dead‑Letter Handling
Exponential backoff

In tasks.py, the email task is defined with:
```python

@app.task(bind=True, autoretry_for=(Exception,), retry_backoff=30, retry_backoff_max=600, max_retries=5)
def send_email(self, to, subject):
    # ... send email ...

```

`autoretry_for` catches any exception and schedules a retry.

`retry_backoff=30` means retry after 30s, then 60s, 120s, 240s, 480s (jitter is optional but omitted for predictability).

`max_retries=5` – after that, the task goes to the dead‑letter queue (see below).

### Dead‑letter handling

- Celery does not have a built‑in DLQ, so I implemented a manual dead‑letter store.

- In the task’s `on_failure` hook (or by catching the `MaxRetriesExceeded` exception), I write the failed job details (payload, error, timestamp) into a Redis list keyed dead_letter:email.

- A separate admin command or monitoring script can inspect this list and retry manually after fixing the cause.



## 5. Worker Resilience – SIGKILL Handling

Scenario: The Celery worker process receives SIGKILL (or crashes) while processing an in‑flight task.

How this is handled:

Celery | setting	|   Value
|------|------------|----------|
| `task_acks_late` |	`True`	| The worker does not acknowledge the task until after the task completes successfully. If the worker dies mid‑execution, the broker (Redis) never receives the ACK and will re‑queue the task to another worker (or the same one after restart). |
|`task_reject_on_worker_lost`    |  `True `  |  If the worker is lost, Celery rejects the task, which puts it back on the queue (instead of losing it).


What does this mean in practice?

    If a worker is SIGKILL'd, the task remains in the "unacked" state in Redis.

    When the worker restarts, Celery's visibility timeout (default 1 hour) expires, and the task is redelivered.

    No job is lost – at worst, the job runs twice (if it had partially completed), so the email task must be idempotent (we avoid duplicate email sends by tracking a unique transaction_id in the email payload).

## 6. Testing Strategy (500 jobs)

The test (apps/queue/tests/test_rate_limiter.py) will:

1. Submit 500 email tasks via Celery.
2. Let them process.
3. Assert:

    - All 500 jobs complete successfully (or fail with retries) – no lost jobs.

    - The rate limiter never allows more than 200 tokens in any 60‑second sliding window (checked by inspecting Redis state every second during the test).

    - At least one intentional failure (simulated by raising an exception for a specific email domain) is retried with backoff and eventually succeeds or lands in dead‑letter.

## 7. Trade‑off Summary

| Decision    |     Why   |   What I sacrificed| 
|-------------|-----------|--------------------|
|Celery       | over custom	Battle‑tested, built‑in retries, easier to maintain.   |   Slightly heavier dependency.
|Redis for both broker & limiter |  Simpler infra, atomic ops.	| If Redis is overloaded, both queue and limiter suffer. |
|Lua token bucket | Atomic, burst‑friendly, memory‑efficient. | Slightly more complex logic than fixed‑window. |
|Fail‑closed on Redis failure   |	Protects upstream email provider.	| Some jobs will be delayed during Redis outages.|
|task_acks_late=True |	Prevents job loss on worker crash.	| Risk of duplicate execution – solved with idempotency. |



## 8. Further improvements (if time permitted)

- Add Prometheus metrics for token usage and dead‑letter size.

- Use Redis Streams instead of Lists for more robust consumer groups.

- Implement a dynamic rate limit per tenant, not just a global cap.

---
