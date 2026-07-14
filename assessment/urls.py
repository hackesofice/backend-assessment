from django.contrib import admin
from django.urls import path, include
from django.conf import settings

urlpatterns = [
    path('admin/', admin.site.urls),

    # Section 1 – Order summary endpoints (broken + fixed)
    path('api/orders/', include('apps.orders.urls')),

    # Section 2 – Queue trigger endpoint (optional, for manual testing)
    path('api/queue/', include('apps.queuee.urls')),

    # django-silk profiler UI – available only when DEBUG is True
    path('silk/', include('silk.urls', namespace='silk')),
    path('api/queue/', include('apps.queuee.urls')),
]

if settings.DEBUG:
    from django.conf.urls.static import static
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)