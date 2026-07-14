from django.utils.deprecation import MiddlewareMixin
from django.core.exceptions import ImproperlyConfigured
from .models import Tenant, set_current_tenant, clear_current_tenant


class TenantMiddleware(MiddlewareMixin):
    """
    Middleware that extracts the tenant from the X-Tenant-ID header (or subdomain)
    and stores it in thread-local storage for the duration of the request.
    """

    def process_request(self, request):
        # Option 1: Extract from a header (simplest for API testing)
        tenant_id = request.headers.get('X-Tenant-ID')

        # Option 2: Extract from subdomain (e.g., tenant1.localhost:8000)
        # Uncomment this block if you prefer subdomain-based routing
        # host = request.get_host()
        # subdomain = host.split('.')[0] if '.' in host and not host.startswith('www') else None
        # if subdomain:
        #     try:
        #         tenant = Tenant.objects.get(subdomain=subdomain)
        #         set_current_tenant(tenant)
        #         return
        #     except Tenant.DoesNotExist:
        #         pass

        if tenant_id:
            try:
                tenant = Tenant.objects.get(id=tenant_id)
                set_current_tenant(tenant)
                # Attach to request for convenience (optional)
                request.tenant = tenant
            except Tenant.DoesNotExist:
                raise ImproperlyConfigured(f"Tenant with ID {tenant_id} does not exist.")
        else:
            # In a real app, you might fall back to a default tenant or raise.
            # For this assessment, we raise to make testing explicit.
            raise ImproperlyConfigured(
                "X-Tenant-ID header is required for all requests."
            )

    def process_response(self, request, response):
        # Clean up thread-local storage after the request is done
        clear_current_tenant()
        return response

    def process_exception(self, request, exception):
        # Ensure cleanup even if an exception occurs
        clear_current_tenant()