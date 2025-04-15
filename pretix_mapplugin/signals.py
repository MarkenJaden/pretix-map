import logging
from django.dispatch import receiver
from pretix.base.signals import order_paid

# from .tasks import geocode_order_task

logger = logging.getLogger(__name__)


# --- Signal Receiver for Geocoding ---
@receiver(order_paid, dispatch_uid="sales_mapper_order_paid_geocode")
def trigger_geocoding_on_payment(sender, order, **kwargs):
    """ Listens for the order_paid signal and queues the geocoding task. """
    try:
        from .tasks import geocode_order_task
        geocode_order_task.apply_async(args=[order.pk])
        logger.info(f"Geocoding task queued for paid order {order.code} (PK: {order.pk}).")
    except NameError:
        logger.error("geocode_order_task not found. Make sure it's imported correctly.")
    except Exception as e:
        logger.exception(f"Failed to queue geocoding task for order {order.code}: {e}")

# --- NO CSP SIGNAL HANDLERS ---
