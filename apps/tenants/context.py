# This file re-exports the thread-local functions so other apps can import cleanly.
# You can also import directly from .models.

from .models import get_current_tenant, set_current_tenant, clear_current_tenant

__all__ = ['get_current_tenant', 'set_current_tenant', 'clear_current_tenant']
