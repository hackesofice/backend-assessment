from django.urls import path
from .views import OrderSummaryBrokenView, OrderSummaryFixedView

urlpatterns = [
    path('summary-broken/', OrderSummaryBrokenView.as_view(), name='order-summary-broken'),
    path('summary-fixed/', OrderSummaryFixedView.as_view(), name='order-summary-fixed'),
]