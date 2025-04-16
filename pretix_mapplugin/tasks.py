import logging
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist

# --- Use Pretix Celery app instance ---
from pretix.celery_app import app
# --- Import necessary Pretix models ---
from pretix.base.models import Order

# --- Import your Geocode model and geocoding functions ---
from .models import OrderGeocodeData
from .geocoding import (
    get_formatted_address_from_order,
    geocode_address,
    DEFAULT_NOMINATIM_USER_AGENT  # Import default for safety/logging
)

logger = logging.getLogger(__name__)


# Define the Celery task
# bind=True gives access to self (the task instance) for retrying
# ignore_result=True as we don't need the return value stored in Celery backend
@app.task(bind=True, max_retries=3, default_retry_delay=60, ignore_result=True)
def geocode_order_task(self, order_pk: int,
                       nominatim_user_agent: str | None = None):  # Added nominatim_user_agent kwarg
    """
    Celery task to geocode the address for a given order PK.
    Accepts the Nominatim User-Agent as an argument.
    """
    try:
        # Fetch order with related address and country data efficiently
        order = Order.objects.select_related(
            'invoice_address',
        ).get(pk=order_pk)
        logger.info(f"Starting geocoding task for Order {order.code} (PK: {order_pk})")

        # Check if already geocoded to prevent redundant work
        # Replace 'geocode_data' if your related_name is different
        relation_name = 'geocode_data'  # Ensure this matches your OrderGeocodeData.order related_name
        if hasattr(order, relation_name) and getattr(order, relation_name) is not None:
            logger.info(f"Geocode data already exists for Order {order.code}. Skipping.")
            return  # Exit successfully

        # 1. Get formatted address string
        address_str = get_formatted_address_from_order(order)
        if not address_str:
            logger.info(f"Order {order.code} has no address suitable for geocoding. Storing null coordinates.")
            # Store null to prevent reprocessing
            with transaction.atomic():
                OrderGeocodeData.objects.update_or_create(
                    order=order,
                    defaults={'latitude': None, 'longitude': None}
                )
            return  # Exit successfully, nothing to geocode

        # 2. Perform geocoding, passing the user agent received by the task
        logger.debug(f"Attempting to geocode address for Order {order.code}: '{address_str}'")
        coordinates = geocode_address(address_str, nominatim_user_agent=nominatim_user_agent)

        # 3. Store result (or null if failed) using atomic transaction
        with transaction.atomic():
            if coordinates:
                latitude, longitude = coordinates
                obj, created = OrderGeocodeData.objects.update_or_create(
                    order=order,
                    defaults={'latitude': latitude, 'longitude': longitude}
                )
                log_level = logging.INFO if created else logging.DEBUG  # Be less noisy on updates
                logger.log(log_level,
                           f"Saved{' new' if created else ' updated'} geocode data for Order {order.code}: ({latitude}, {longitude})")
            else:
                logger.warning(f"Geocoding failed for Order {order.code}. Storing null coordinates.")
                # Store nulls to indicate an attempt was made and failed
                obj, created = OrderGeocodeData.objects.update_or_create(
                    order=order,
                    defaults={'latitude': None, 'longitude': None}
                )
                log_level = logging.INFO if created else logging.DEBUG
                logger.log(log_level,
                           f"Saved{' new' if created else ' updated'} null geocode data for Order {order.code} after failed attempt.")

    except ObjectDoesNotExist:  # More specific exception
        logger.error(f"Order with PK {order_pk} not found in geocode_order_task.")
        # Don't retry if the order doesn't exist
    except Exception as e:
        # Catch any other unexpected errors
        logger.exception(f"Unexpected error in geocode_order_task for Order PK {order_pk}: {e}")
        # Retry on potentially temporary errors (database, network issues etc.)
        raise self.retry(exc=e)  # Let Celery handle retry logic
