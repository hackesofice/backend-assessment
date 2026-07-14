from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.db import connection
from rest_framework.test import APIClient
from apps.orders.models import Customer, Order, OrderItem
from decimal import Decimal


class OrderPerformanceTest(TestCase):
    def setUp(self):
        # Create a test user with 50 orders (enough to show the N+1, but fast for tests)
        self.user = User.objects.create_user(username='perfuser', password='pass')
        self.customer = Customer.objects.create(user=self.user, name='Perf User', email='perf@example.com')

        for i in range(50):
            order = Order.objects.create(user=self.user, customer=self.customer, status='pending')
            OrderItem.objects.create(order=order, product_name='Item', quantity=1, unit_price=Decimal('10.00'))

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_broken_view_query_count(self):
        """Assert the broken view executes ~1 + 2N queries (N=50 → ~101)"""
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get('/api/orders/summary-broken/')
            self.assertEqual(response.status_code, 200)
            # Allow a small margin: 1 for orders + N for customers + N for item counts
            # Actually, customer is nullable, so it's 1 + N (customer) + N (item_count) = ~101
            self.assertGreater(len(ctx.captured_queries), 50, "Broken view should issue >50 queries")
            self.assertLess(len(ctx.captured_queries), 200, "Sanity check")

    def test_fixed_view_query_count(self):
        """Assert the fixed view executes only ~2-3 queries (select_related + prefetch_related)"""
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get('/api/orders/summary-fixed/')
            self.assertEqual(response.status_code, 200)
            # select_related + prefetch_related + initial order query = ~2-3
            self.assertLessEqual(len(ctx.captured_queries), 4, "Fixed view should be ~2-3 queries")

    def test_fixed_view_data_accuracy(self):
        """Ensure the fixed view returns the same data as the broken view (semantic equivalence)"""
        broken_resp = self.client.get('/api/orders/summary-broken/').json()
        fixed_resp = self.client.get('/api/orders/summary-fixed/').json()

        # Both should have the same count and order IDs (order may vary, but we compare sets)
        self.assertEqual(broken_resp['count'], fixed_resp['count'])
        broken_ids = {o['id'] for o in broken_resp['orders']}
        fixed_ids = {o['id'] for o in fixed_resp['orders']}
        self.assertEqual(broken_ids, fixed_ids)

        # Spot-check one order's data
        broken_order = broken_resp['orders'][0]
        fixed_order = next(o for o in fixed_resp['orders'] if o['id'] == broken_order['id'])
        self.assertEqual(broken_order['customer'], fixed_order['customer'])
        self.assertEqual(broken_order['items_count'], fixed_order['items_count'])
        self.assertEqual(broken_order['total_amount'], fixed_order['total_amount'])


# Helper to capture queries (Django 3.2+)
from django.test.utils import CaptureQueriesContext