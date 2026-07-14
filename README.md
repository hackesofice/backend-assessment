## Backend Technical Assessment – Artikate Studio

This repository contains my solution for the Backend Developer assessment.  
It covers:  
- **Section 1** – Diagnose and fix an N+1 performance regression (with django-silk).  
- **Section 2** – Rate‑limited async job queue (Celery + Redis, token‑bucket limiter).  
- **Section 3** – Multi‑tenant ORM isolation (custom manager + thread‑local middleware).  
- **Section 4** – Written architecture review (see `ANSWERS.md`).  
- **Optional** – Screen recording of the queue in action (link below).

---

## 🚀 Quick Start (under 5 minutes)

### Prerequisites
- Python 3.10 or 3.11
- Redis server (running on `localhost:6379`) – or use the provided Docker command.
- PostgreSQL (optional – SQLite works for development, but I recommend PostgreSQL for the test data).

### 1. Clone the repository
```bash
git clone https://github.com/hackesofice/backend-assessment.git
cd backend-assessment
```

### 2. Create and activate a virtual environment
```bash

python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate
```


### 3. Install dependencies
```bash

pip install -r requirements.txt

```


### 4. Set up environment variables
Copy .env.example to .env and adjust values if needed (the defaults work locally).
```bash
cp .env.example .env
```

**`Key variables`**:

- `DATABASE_URL` – defaults to `sqlite:///db.sqlite3`

- `REDIS_URL` – defaults to `redis://localhost:6379/0`

- `SECRET_KEY` – generate one or use the example (only for local).


### 5. Run database migrations
```bash
python manage.py makemigrations
python manage.py migrate

```


### 6. (Optional) Seed test data for Section 1

To reproduce the N+1 problem with 200+ orders:
```bash

python manage.py seed_orders --customers=10 --orders-per-customer=50

```


### 7. Start Redis (if not already running)

Using Docker (easiest):
```bash

docker run -d -p 6379:6379 redis:7

```

Or start your local Redis service.


### 8. Run the Celery worker (for Section 2)

In a separate terminal:
```bash

celery -A assessment.celery worker --loglevel=info

```


### 9. Run the development server
```bash

python manage.py runserver

```


### 10. Run all tests
```bash

pytest

```

All tests must pass from a clean environment. The test suite includes:

- Performance assertions (query counts) for Section 1.

- Rate‑limiter atomicity and 200/min constraints for Section 2.

- Tenant isolation breaches for Section 3.

### 📁 Project Structure (abridged)
```text

assessment/                # Django project
├── settings.py
├── urls.py
└── celery.py              # Celery app
|
apps/
├── orders/                # Section 1 – broken & fixed view
├── queue/                 # Section 2 – Celery tasks + rate limiter
├── tenants/               # Section 3 – tenant manager + middleware
└── shared/                # Redis client helper

DESIGN.md                  # Section 2 architecture trade‑offs
ANSWERS.md                 # All written answers (incident log, async, etc.)

```


### 🔧 Running specific sections
#### Section 1 – View the performance fix

- Broken endpoint: `GET /api/orders/summary-broken/` – times out with >200 orders.

- Fixed endpoint: `GET /api/orders/summary-fixed/` – uses prefetch_related and select_related.

- Profiler evidence: `django-silk` is installed. Access `/silk/` to see query counts and timings.

#### Section 2 – Trigger the email queue

You can submit a batch of jobs via the Django shell:
```python

from apps.queuee.tasks import send_email
for i in range(500):
    send_email.delay(f"user{i}@example.com", "Order confirmed")

```


Or use the test suite: pytest apps/queue/tests/.

#### Section 3 – Tenant isolation

- Middleware extracts tenant from a X-Tenant-ID header (or subdomain – see code).

- All Order.objects.all() calls are automatically scoped.

- To test: run pytest apps/tenants/tests/.


## 📹 Optional screen recording (Section 5)
*Skipped – this section is optional and not required for the core assessment.*


### 📝 Notes to the reviewer

- All written reasoning is in ANSWERS.md and DESIGN.md – I’ve named specific Django/Redis mechanisms throughout.

- The code is structured so each section is self‑contained, making review straightforward.

- I’ve used a custom Redis‑based token‑bucket (Lua script) for atomic rate limiting – not a third‑party library.

- For the async safety question (Section 3), I discuss contextvars and why thread‑locals fail in async Django views.

Thank you for reviewing my submission!

If you have any trouble running the code, please reach out via the contact who shared this document.


---
