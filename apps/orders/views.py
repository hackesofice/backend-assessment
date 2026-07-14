from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import connection
from .models import Order, OrderItem


# ---------- BROKEN VERSION (N+1 problem) ----------
class OrderSummaryBrokenView(APIView):
    """
    This view causes an N+1 query problem:
    - 1 query for orders
    - N queries for order.customer (N = number of orders)
    - N queries for order.items.count() (another N)
    Total: 1 + 2N queries
    For 200 orders → ~401 queries → timeout at scale.
    """

    def get(self, request):
        # No prefetching – naive ORM usage
        orders = Order.objects.filter(user=request.user)

        data = []
        for order in orders:
            # Each iteration triggers:
            # 1) order.customer (hits DB unless cached)
            # 2) order.items.count() (hits DB)
            customer_name = order.customer.name if order.customer else 'Anonymous'
            item_count = order.items.count()
            data.append({
                'id': order.id,
                'order_date': order.order_date.isoformat(),
                'customer': customer_name,
                'items_count': item_count,
                'total_amount': str(order.total_amount),
                'status': order.status,
            })

        return Response({
            'count': len(data),
            'orders': data,
            'queries': len(connection.queries),  # Included for debugging
        })


# ---------- FIXED VERSION ----------
class OrderSummaryFixedView(APIView):
    """
    Fixed with select_related and prefetch_related:
    - 1 query for orders + customer JOIN (select_related)
    - 1 query for all order items (prefetch_related)
    Total: 2 queries (plus 1 for the user filter, so ~2-3)
    Constant time, regardless of order count.
    """

    def get(self, request):
        # select_related -> JOIN customer in the same query
        # prefetch_related -> separate query for all items, cached in Python
        orders = Order.objects.filter(user=request.user).select_related(
            'customer'
        ).prefetch_related(
            'items'
        )

        data = []
        for order in orders:
            # No DB hits – customer is joined, items are prefetched
            customer_name = order.customer.name if order.customer else 'Anonymous'
            # .count() on a prefetched queryset uses the cached list (no DB hit)
            item_count = order.items.count()
            data.append({
                'id': order.id,
                'order_date': order.order_date.isoformat(),
                'customer': customer_name,
                'items_count': item_count,
                'total_amount': str(order.total_amount),
                'status': order.status,
            })

        return Response({
            'count': len(data),
            'orders': data,
            'queries': len(connection.queries),  # Should be ~2-3
        })