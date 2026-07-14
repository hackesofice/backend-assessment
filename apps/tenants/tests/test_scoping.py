from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from apps.tenants.models import Tenant, TenantManager, set_current_tenant, clear_current_tenant
from apps.tenants.middleware import TenantMiddleware
from apps.orders.models import Order  # We'll import once we add tenant field
import pytest


class TenantScopingTest(TestCase):
    def setUp(self):
        # Create two tenants
        self.tenant_a = Tenant.objects.create(name='Tenant A', id=1)
        self.tenant_b = Tenant.objects.create(name='Tenant B', id=2)

        # Create a user (we need a user for the Order model's foreign key)
        self.user = User.objects.create_user(username='testuser', password='pass')

        # Manually set tenant A in thread-local so we can create orders for tenant A
        set_current_tenant(self.tenant_a)
        self.order_a1 = Order.objects.create(user=self.user, status='pending')
        self.order_a2 = Order.objects.create(user=self.user, status='shipped')

        # Switch to tenant B and create orders for tenant B
        set_current_tenant(self.tenant_b)
        self.order_b1 = Order.objects.create(user=self.user, status='pending')

        # Clear thread-local so each test starts fresh
        clear_current_tenant()

    def test_manager_requires_tenant(self):
        """Calling .all() without a tenant set should raise ImproperlyConfigured."""
        with self.assertRaises(ImproperlyConfigured):
            list(Order.objects.all())

    def test_tenant_a_cannot_see_tenant_b_data(self):
        """When tenant A is active, only tenant A's orders are visible."""
        set_current_tenant(self.tenant_a)
        orders = list(Order.objects.all())
        self.assertEqual(len(orders), 2)
        self.assertTrue(all(o.tenant_id == self.tenant_a.id for o in orders))
        # Ensure tenant B's order is not included
        self.assertNotIn(self.order_b1, orders)

    def test_tenant_b_cannot_see_tenant_a_data(self):
        """When tenant B is active, only tenant B's orders are visible."""
        set_current_tenant(self.tenant_b)
        orders = list(Order.objects.all())
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].id, self.order_b1.id)

    def test_create_automatically_sets_tenant(self):
        """Creating an order without specifying tenant should use the current tenant."""
        set_current_tenant(self.tenant_a)
        new_order = Order.objects.create(user=self.user, status='pending')
        self.assertEqual(new_order.tenant_id, self.tenant_a.id)

    def test_middleware_sets_tenant_from_header(self):
        """Integration test: middleware extracts X-Tenant-ID and sets it."""
        factory = RequestFactory()
        request = factory.get('/api/orders/summary-fixed/', headers={'X-Tenant-ID': str(self.tenant_a.id)})

        middleware = TenantMiddleware(lambda req: None)
        middleware.process_request(request)

        # The tenant should now be set in thread-local
        from apps.tenants.models import get_current_tenant
        self.assertEqual(get_current_tenant().id, self.tenant_a.id)

        # Clean up
        clear_current_tenant()

    def test_middleware_raises_if_tenant_missing(self):
        """If no X-Tenant-ID header, middleware should raise."""
        factory = RequestFactory()
        request = factory.get('/api/orders/summary-fixed/')

        middleware = TenantMiddleware(lambda req: None)
        with self.assertRaises(ImproperlyConfigured):
            middleware.process_request(request)

    def test_middleware_raises_if_tenant_invalid(self):
        """If the tenant ID doesn't exist, middleware should raise."""
        factory = RequestFactory()
        request = factory.get('/api/orders/summary-fixed/', headers={'X-Tenant-ID': '999'})

        middleware = TenantMiddleware(lambda req: None)
        with self.assertRaises(ImproperlyConfigured):
            middleware.process_request(request)

    def tearDown(self):
        # Ensure thread-local is always cleaned up after each test
        clear_current_tenant()