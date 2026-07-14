from django.db import models
from django.core.exceptions import ImproperlyConfigured
import threading

# Thread-local storage for the current request's tenant
_thread_local = threading.local()


def get_current_tenant():
    """Get the current tenant from thread-local storage."""
    return getattr(_thread_local, 'tenant', None)


def set_current_tenant(tenant):
    """Set the current tenant in thread-local storage."""
    _thread_local.tenant = tenant


def clear_current_tenant():
    """Clear the current tenant (called at the end of the request)."""
    if hasattr(_thread_local, 'tenant'):
        del _thread_local.tenant


class Tenant(models.Model):
    """The tenant/organisation model."""
    name = models.CharField(max_length=100, unique=True)
    subdomain = models.CharField(max_length=50, unique=True, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class TenantManager(models.Manager):
    """
    Custom manager that automatically scopes all querysets to the current tenant.
    This is the core isolation mechanism – it cannot be accidentally bypassed.
    """

    def get_queryset(self):
        """
        Override get_queryset to filter by the current tenant.
        If no tenant is set, we raise an explicit error to prevent accidental data leaks.
        """
        tenant = get_current_tenant()
        if tenant is None:
            # In a production system you might log this and return an empty queryset,
            # but raising an error makes it obvious during development/testing.
            raise ImproperlyConfigured(
                "No tenant has been set for the current request. "
                "Ensure TenantMiddleware is running and a valid X-Tenant-ID header is provided."
            )
        return super().get_queryset().filter(tenant=tenant)

    def all(self):
        """Ensure .all() is also scoped – calls get_queryset() under the hood."""
        return self.get_queryset()

    def create(self, **kwargs):
        """Automatically set tenant on create if not provided."""
        tenant = get_current_tenant()
        if tenant is not None and 'tenant' not in kwargs:
            kwargs['tenant'] = tenant
        return super().create(**kwargs)