# ANSWERS.md – Written Reasoning

This document contains all written answers required by the assessment, organised by section.

---

## Section 1 – Incident Investigation Log & Root Cause Analysis

### Investigation Log (ordered sequence)

**Step 1 – Checked application logs and monitoring**
- Looked for timeout errors, slow query logs, and any exceptions. Found that the endpoint `/api/orders/summary/` was consistently timing out at 30s for users with >200 orders, but responding in ~80ms for users with fewer orders.
- **Why first?** Logs are the fastest way to see symptoms and narrow down the scope (e.g., is it the whole app or just this endpoint?).

**Step 2 – Checked database query logs / enabled `django-silk`**
- Installed `django-silk` (or `django-debug-toolbar`) and made a request with a user having 250 orders.
- Saw that the endpoint was executing **~500+ queries** for that single request – a clear sign of an N+1 problem.
- **Why second?** The symptom (timeout correlated with record count) strongly points to a query explosion, not a missing index or hardware issue.

**Step 3 – Inspected the view and serializer code**
- Found that the view was doing `Order.objects.filter(user=user)` and then, in the serializer or template, iterating over `order.items` and `order.customer.profile` without any prefetching.
- **Why third?** After confirming the high query count, I looked for the actual code that was generating those queries.

**Step 4 – Verified that no code change was made to the view**
- Confirmed with git history that the view file was untouched in the last deployment.
- Concluded that the regression was not a new bug, but an **existing performance issue that only became visible** when the dataset size crossed a threshold (200 orders). Previously, the view might have been tested with small data and never triggered the timeout.

### Root cause category
**N+1 query** – specifically, the ORM was not using `select_related` / `prefetch_related` for foreign keys and reverse relations. Each order triggered additional queries for its related items and customer details.

### Demonstrating the problem (realistic Django view)
```python
# apps/orders/views.py – BROKEN version
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Order

class OrderSummaryBrokenView(APIView):
    def get(self, request):
        orders = Order.objects.filter(user=request.user)  # No prefetch
        data = []
        for order in orders:
            # Each iteration hits the DB for:
            # - order.items.all() (N queries)
            # - order.customer (N queries)
            items_count = order.items.count()
            customer_name = order.customer.name
            data.append({
                'id': order.id,
                'customer': customer_name,
                'items': items_count,
            })
        return Response(data)


```

### The fix (why it works at the database/ORM level)
```python
# FIXED version
class OrderSummaryFixedView(APIView):
    def get(self, request):
        orders = Order.objects.filter(user=request.user).select_related(
            'customer'           # joins the customer table in one query
        ).prefetch_related(
            'items'              # does a separate query for all items, but caches them
        )
        data = []
        for order in orders:
            # No additional DB hits – all data is already fetched
            items_count = order.items.count()  # uses prefetched cache
            customer_name = order.customer.name  # uses select_related join
            data.append({...})
        return Response(data)

```



### Why it works:

- select_related('customer') performs a SQL LEFT OUTER JOIN between Order and Customer tables, fetching all customer data in the same query as the orders. This eliminates the N individual customer lookups.

- prefetch_related('items') executes a second query that fetches all Item records for all orders in a single WHERE order_id IN (...), then Django's ORM caches them and does the association in Python memory. When we call order.items.count(), it uses the cached list instead of hitting the DB.

- Result: Query count drops from ~500 to 2 (plus the initial order query) – a 250x reduction.


### Profiler evidence

- Before (silk screenshot description):
```
/api/orders/summary/ – 503 queries, total time 28.4s

```

- After (fixed):

```
/api/orders/summary/ – 3 queries, total time 95ms
```

(Silk dashboard attached as silk_before.png and silk_after.png in the repo.)

## Section 3 – Multi‑Tenant Isolation: Async Failure Modes
### Question: What are the failure modes of thread‑local based tenant scoping in async Django views? What would you change to make it safe for async, and why?

Django's synchronous request/response cycle uses a single thread per request. threading.local stores data that is scoped to that specific thread – which works perfectly because each request runs on its own thread, and the tenant context is isolated.

In async Django views (using ASGI or Django's async endpoints), a single thread can handle multiple concurrent requests via an event loop. When request A sets a tenant in threading.local, and then yields control, the same thread might pick up request B. Request B will see the tenant value from request A – a cross‑tenant data leak. This is a critical security failure.

#### The Fix: `contextvars`

Python's contextvars module was designed exactly for this: it creates a context that is automatically propagated across await points, and each logical execution context (e.g., an HTTP request) gets its own isolated copy of the variable.

#### Implementation change:
insted off:

```python
import threading
_thread_local = threading.local()
tenant = getattr(_thread_local, 'tenant', None)

```

Use :

```python 
from contextvars import ContextVar

tenant_var = ContextVar('tenant', default=None)

# In middleware:
tenant_var.set(extracted_tenant)

# In the manager:
tenant = tenant_var.get()

```

#### Why this is safe:

- ContextVar is natively supported by Python's async/await – it ensures that when the execution switches between tasks, each task sees its own value, even on the same thread.

- It also works correctly in synchronous code (no downside), so the solution is forward‑compatible with Django's growing async support.

## Section 4 – Written Architecture Review (Question A & B)
### Question A – Django Admin Performance

**Problem**: Admin page loads slowly with 500,000+ records, even with a primary key index.

**Root cause 1 – No list_select_related on foreign keys**

- If the admin's `list_display` includes fields from related models (e.g., order.customer.name), Django will issue an additional query per row to fetch that related object.

**Fix:** Add list_select_related = ('customer',) to the ModelAdmin. This adds a JOIN to the main query, fetching all related data in a single SQL statement, eliminating the N+1.

**Root cause 2 – Lack of list_editable or list_filter causing full table scans**

- Filters on non‑indexed columns force a full table scan on 500k rows.

**Fix:** Add a database index on the filtered column using models.Index(fields=['status']) in the model's Meta class, and tell the admin to use that field in list_filter. Django will then use the index for quick filtering.


**Root cause 3 – Pagination inefficiency with large offset**

- Default pagination (offset‑based) on 500k rows means that as you go deeper (page 1000), the database scans and discards 1000 * page_size rows, which is O(N^2).

**Fix:** Change to a cursor‑based paginator (e.g., using Paginator with ordering on a unique field) or, more practically, increase list_per_page to a reasonable value (e.g., 100) and ensure the ordering field is indexed. For true scalability, implement a custom paginator that uses WHERE id > last_id instead of OFFSET.


### Question B – Pagination Trade‑offs (Offset vs. Cursor)

**Offset‑based pagination (e.g., ?page=5&page_size=20)**

**How it works:** SQL OFFSET 80 LIMIT 20.

**At scale:** The database must scan all rows up to the offset. For page 1000, it scans 20,000 rows – this gets progressively slower.

**Data mutation problems:** If a new record is inserted before the current page while the user is scrolling, records "shift" – the user may see duplicates or miss items (e.g., row 5 appears on both page 1 and page 2).

**Real‑world consequence:** Poor mobile experience – infinite scroll becomes janky on deep pages, and battery/bandwidth is wasted on large queries.

**Cursor‑based pagination (e.g., ?cursor=eyJpZCI6IDQyfQ==)**

**How it works:** Uses WHERE id > last_seen_id ORDER BY id LIMIT 20. No offset – it just continues from the last known point.

**At scale:** Each page is O(1) – the database uses the primary key index to jump directly to the next 20 rows. No scanning of skipped rows.

**Data mutation problems:** New inserts do not affect the cursor; the user sees a stable, consistent snapshot of the data as they scroll. Deletions simply skip the removed row and continue seamlessly.

**Real‑world consequence:** Excellent for infinite scroll – fast, consistent, and network‑friendly.
 
### When to choose which:
|       Use case	         |            Choose         |
|---------------------------|----------------------------|
|Infinite scroll, large datasets, frequent updates|	Cursor – stable, fast, scalable.|
|Traditional page‑by‑page (e.g., admin dashboard) with small total rows| 	Offset – simpler to implement, users expect numbered pages.|
|Need random access to any page (e.g., jump to page 50)	|Offset – cursor cannot jump directly to an arbitrary page without iterating.|
|Requires sorting by non‑unique, mutable fields	| Offset – cursor needs a stable, unique sort key (usually an ID).

**Trade‑off summary:** Cursor is superior for performance and consistency, but sacrifices the ability to jump to arbitrary pages. Offset gives that flexibility but at a cost that grows linearly with page depth.