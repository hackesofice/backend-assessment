from django.db import models
from django.contrib.auth import get_user_model
from apps.tenants.models import Tenant, TenantManager

User = get_user_model()


class Customer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer')
    name = models.CharField(max_length=100)
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Order(models.Model):
    # --- Multi-tenant isolation (Section 3) ---
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='orders')
    objects = TenantManager()          # <-- This is the custom manager that auto-scopes

    # --- Regular fields ---
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='orders',
        null=True,
        blank=True
    )
    order_date = models.DateTimeField(auto_now_add=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('shipped', 'Shipped'), ('delivered', 'Delivered')],
        default='pending'
    )

    class Meta:
        indexes = [
            models.Index(fields=['user', 'order_date']),
            models.Index(fields=['status']),
            models.Index(fields=['tenant', 'order_date']),  # Important for multi-tenant queries
        ]

    def __str__(self):
        return f"Order #{self.id} - {self.user.username}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product_name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"