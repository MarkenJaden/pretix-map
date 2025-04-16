import logging
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist

# --- Import django-scopes ---
from django_scopes import scope

# --- Use Pretix Celery app instance ---
from pretix.celery_app import app
# --- Import necessary Pretix models ---
from pretix.base.models import Order, Organizer  # Import Organizer

# --- Import your Geocode model and geocoding functions ---
from .models import OrderGeocodeData
from .geocoding import (
    get_formatted_address_from_order,
    geocode_address,
    DEFAULT_NOMINATIM_USER_AGENT
)

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=3, default_retry_delay=60, ignore_result=True)
# --- Accept organizer_pk as kwarg ---
def geocode_order_task(self, order_pk: int, organizer_pk: int | None = None, nominatim_user_agent: str | None = None):
    """
    Celery task to geocode the address for a given order PK.
    Accepts organizer_pk and Nominatim User-Agent as arguments.
    Fetches Organizer first, then activates scope.
    """
    organizer = None
    order = None
    try:
        # --- Step 1: Fetch Organizer (unscoped) ---
        if organizer_pk is None:
            # This should ideally not happen if called correctly, but handle defensively
            logger.error(f"organizer_pk not provided for Order PK {order_pk}. Cannot activate scope.")
            # Depending on policy, you might retry, skip, or raise an error.
            # Skipping for now.
            return

        try:
            organizer = Organizer.objects.get(pk=organizer_pk)
        except ObjectDoesNotExist:
            logger.error(f"Organizer with PK {organizer_pk} not found (for Order PK {order_pk}).")
            # Don't retry if organizer doesn't exist
            return

        # --- Step 2: Activate Scope ---
        with scope(organizer=organizer):
            # --- Step 3: Fetch Order (now within scope) ---
            try:
                order = Order.objects.select_related(
                    'invoice_address'  # Only need this direct relation now
                ).get(pk=order_pk)
            except ObjectDoesNotExist:
                logger.error(f"Order with PK {order_pk} not found within scope of Org {organizer_pk}.")
                # Don't retry if order doesn't exist in this scope
                return

            logger.info(
                f"Starting geocoding task for Order {order.code} (PK: {order_pk}) within scope of Organizer '{organizer.slug}'")

            # --- Rest of the logic runs within scope ---
            relation_name = 'geocode_data'
            if OrderGeocodeData.objects.filter(order_id=order_pk).exists():
                logger.info(f"Geocode data already exists for Order {order.code} (checked within scope). Skipping.")
                return

            address_str = get_formatted_address_from_order(order)
            if not address_str:
                logger.info(f"Order {order.code} has no address suitable for geocoding. Storing null coordinates.")
                with transaction.atomic():
                    OrderGeocodeData.objects.update_or_create(
                        order=order, defaults={'latitude': None, 'longitude': None}
                    )
                return

            logger.debug(f"Attempting to geocode address for Order {order.code}: '{address_str}'")
            coordinates = geocode_address(address_str, nominatim_user_agent=nominatim_user_agent)

            with transaction.atomic():
                if coordinates:
                    latitude, longitude = coordinates
                    obj, created = OrderGeocodeData.objects.update_or_create(
                        order=order, defaults={'latitude': latitude, 'longitude': longitude}
                    )
                    log_level = logging.INFO if created else logging.DEBUG
                    logger.log(log_level,
                               f"Saved{' new' if created else ' updated'} geocode data for Order {order.code}: ({latitude}, {longitude})")
                else:
                    logger.warning(f"Geocoding failed for Order {order.code}. Storing null coordinates.")
                    obj, created = OrderGeocodeData.objects.update_or_create(
                        order=order, defaults={'latitude': None, 'longitude': None}
                    )
                    log_level = logging.INFO if created else logging.DEBUG
                    logger.log(log_level,
                               f"Saved{' new' if created else ' updated'} null geocode data for Order {order.code} after failed attempt.")
        # --- Scope deactivated automatically ---

    # --- Outer exception handling ---
    except ObjectDoesNotExist:
        # Should be caught earlier now, but keep for safety
        obj_type = "Organizer" if organizer is None else "Order"
        obj_pk = organizer_pk if organizer is None else order_pk
        logger.error(f"{obj_type} with PK {obj_pk} not found.")
    except Exception as e:
        org_info = f" (Org PK: {organizer_pk})" if organizer_pk else ""
        order_info = f" (Order PK: {order_pk})" if order_pk else ""
        logger.exception(f"Unexpected error in geocode_order_task{org_info}{order_info}: {e}")
        # Retry on potentially temporary errors
        raise self.retry(exc=e)
