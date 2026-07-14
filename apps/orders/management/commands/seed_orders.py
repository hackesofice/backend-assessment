from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from apps.orders.models import Customer, Order, OrderItem
from apps.tenants.models import Tenant, set_current_tenant, clear_current_tenant
from decimal import Decimal
import random


class Command(BaseCommand):
    help = 'Seed orders for performance testing (creates a user with many orders)'

    def add_arguments(self, parser):
        parser.add_argument('--users', type=int, default=1, help='Number of users to create')
        parser.add_argument('--orders', type=int, default=250, help='Orders per user')
        parser.add_argument('--items', type=int, default=5, help='Items per order')
        parser.add_argument(
            '--tenant',
            type=int,
            default=1,
            help='Tenant ID to assign all orders to (creates tenant if it does not exist)'
        )

    def handle(self, *args, **options):
        num_users = options['users']
        orders_per_user = options['orders']
        items_per_order = options['items']
        tenant_id = options['tenant']

        # Ensure the tenant exists
        tenant, created = Tenant.objects.get_or_create(
            id=tenant_id,
            defaults={'name': f'Tenant {tenant_id}', 'subdomain': f'tenant{tenant_id}'}
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created tenant: {tenant.name}'))

        # Set the tenant in thread-local so that TenantManager auto-scopes & auto-assigns
        set_current_tenant(tenant)

        product_names = ['Laptop', 'Mouse', 'Keyboard', 'Monitor', 'USB Cable', 'Headset', 'Charger', 'Adapter']

        for i in range(num_users):
            username = f'testuser_{i+1}'
            user, created = User.objects.get_or_create(
                username=username,
                defaults={'email': f'{username}@example.com', 'password': 'pbkdf2_sha256$...'}
            )
            if created:
                user.set_password('password123')
                user.save()

            customer, _ = Customer.objects.get_or_create(
                user=user,
                defaults={'name': f'Test User {i+1}', 'email': user.email}
            )

            self.stdout.write(f'Creating {orders_per_user} orders for {username}...')

            for j in range(orders_per_user):
                # The Order's custom manager will auto-set the tenant because we have
                # set_current_tenant(tenant) above. We don't need to pass tenant explicitly.
                order = Order.objects.create(
                    user=user,
                    customer=customer,
                    total_amount=Decimal('0.00'),
                    status=random.choice(['pending', 'shipped', 'delivered'])
                )

                total = Decimal('0.00')
                for _ in range(random.randint(1, items_per_order)):
                    qty = random.randint(1, 3)
                    price = Decimal(str(round(random.uniform(10, 200), 2)))
                    item = OrderItem.objects.create(
                        order=order,
                        product_name=random.choice(product_names),
                        quantity=qty,
                        unit_price=price
                    )
                    total += price * qty

                order.total_amount = total
                order.save(update_fields=['total_amount'])

            self.stdout.write(self.style.SUCCESS(f'Done: {orders_per_user} orders for {username}'))

        # Clean up thread-local
        clear_current_tenant()
        self.stdout.write(self.style.SUCCESS('All seeding complete!'))