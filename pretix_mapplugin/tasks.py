import logging
from pretix.base.models import Order
from pretix.celery_app import app # Import the Pretix Celery app instance
from .geocoding import get_formatted_address_from_order, geocode_address # Import from Step 3
from .models import OrderGeocodeData

logger = logging.getLogger(__name__)

@app.task(bind=True, max_retries=3, default_retry_delay=60) # Configure retry behavior
def geocode_order_task(self, order_pk: int):
    """
    Celery task to geocode an order's address and store the result.
    """
    try:
        order = Order.objects.select_related('invoice_address').get(pk=order_pk)
        logger.info(f"Starting geocoding task for Order {order.code} (PK: {order_pk})")

        # Check if already geocoded to prevent redundant work (e.g., if task retries)
        if OrderGeocodeData.objects.filter(order=order).exists():
            logger.info(f"Geocode data already exists for Order {order.code}. Skipping.")
            return # Exit successfully

        # 1. Get formatted address
        address_str = get_formatted_address_from_order(order)
        if not address_str:
            logger.warning(f"Order {order.code} has no invoice address to geocode.")
            return # Exit successfully, nothing to do

        # 2. Perform geocoding (using function from Step 3)
        logger.debug(f"Attempting to geocode address for Order {order.code}: '{address_str}'")
        coordinates = geocode_address(address_str) # This handles its own errors/logging

        # 3. Store result if successful
        if coordinates:
            latitude, longitude = coordinates
            try:
                # Use update_or_create to handle potential race conditions gracefully,
                # although the initial check makes it less likely.
                obj, created = OrderGeocodeData.objects.update_or_create(
                    order=order,
                    defaults={
                        'latitude': latitude,
                        'longitude': longitude
                    }
                )
                if created:
                    logger.info(f"Successfully geocoded and stored coordinates for Order {order.code}: ({latitude}, {longitude})")
                else:
                     logger.info(f"Successfully geocoded and updated coordinates for Order {order.code}: ({latitude}, {longitude})")

            except Exception as e:
                logger.exception(f"Failed to save geocode data for Order {order.code} to database: {e}")
                # Optionally retry the task if saving failed
                self.retry(exc=e)
        else:
            # Geocoding function failed (already logged within geocode_address)
            logger.warning(f"Geocoding failed for Order {order.code}. No coordinates stored.")
            # Decide if you want to retry here based on the type of geocoding failure
            # For example, don't retry if address was not found, but maybe retry on timeout.
            # The geocode_address function would need to return more info for that.
            # For now, we just log and don't store anything.

    except Order.DoesNotExist:
        logger.error(f"Order with PK {order_pk} not found for geocoding task.")
        # Don't retry if the order doesn't exist
    except Exception as e:
        # Catch any other unexpected errors in the task
        logger.exception(f"Unexpected error in geocode_order_task for Order PK {order_pk}: {e}")
        # Retry on unexpected errors
        self.retry(exc=e)