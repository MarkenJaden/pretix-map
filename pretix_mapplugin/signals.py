import logging
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from pretix.base.signals import order_paid # Signal when an order transitions to paid

# Make sure our tasks are imported so Celery can find them
from .tasks import geocode_order_task

logger = logging.getLogger(__name__)

@receiver(order_paid, dispatch_uid="sales_mapper_order_paid_geocode")
def trigger_geocoding_on_payment(sender, order, **kwargs):
    """
    Listens for the order_paid signal and queues the geocoding task.
    """
    try:
        # Queue the background task, passing the order's primary key
        geocode_order_task.apply_async(args=[order.pk])
        logger.info(
            f"Geocoding task queued for paid order {order.code} (PK: {order.pk})."
        )
    except Exception as e:
        # Log if queuing itself fails (e.g., Redis/broker connection issue)
        logger.exception(
            f"Failed to queue geocoding task for order {order.code}: {e}"
        )

# You can add more signal receivers here if needed for other plugin functionality