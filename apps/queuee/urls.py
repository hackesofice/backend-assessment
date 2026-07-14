from django.urls import path
from .views import TriggerEmailQueueView, DeadLetterView

urlpatterns = [
    path('trigger/', TriggerEmailQueueView.as_view(), name='trigger-email-queue'),
    path('dead-letter/', DeadLetterView.as_view(), name='dead-letter'),
]