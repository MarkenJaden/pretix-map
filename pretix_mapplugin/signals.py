import logging
from django.dispatch import receiver
from django.urls import reverse, NoReverseMatch  # Import reverse and NoReverseMatch
from django.utils.translation import gettext_lazy as _  # For translatable labels
from django.http import HttpRequest  # For type hinting

# --- Pretix Signals ---
from pretix.base.signals import order_paid
from pretix.control.signals import nav_event  # Import the navigation signal

# --- Tasks ---
from .tasks import geocode_order_task

logger = logging.getLogger(__name__)

# --- Constants ---
MAP_VIEW_URL_NAME = 'plugins:pretix_mapplugin:event.settings.salesmap.show'
# Define the permission required to see the map link
REQUIRED_MAP_PERMISSION = 'can_view_orders'


# --- Signal Receiver for Geocoding (Keep As Is) ---
@receiver(order_paid, dispatch_uid="sales_mapper_order_paid_geocode")
def trigger_geocoding_on_payment(sender, order, **kwargs):
    # ... (keep your existing geocoding logic) ...
    try:
        geocode_order_task.apply_async(args=[order.pk])
        logger.info(f"Geocoding task queued for paid order {order.code} (PK: {order.pk}).")
    except NameError:
        logger.error("geocode_order_task not found. Make sure it's imported correctly.")
    except Exception as e:
        logger.exception(f"Failed to queue geocoding task for order {order.code}: {e}")


# --- Signal Receiver for Adding Navigation Item ---
@receiver(nav_event, dispatch_uid="sales_mapper_nav_event_add_map")
def add_map_nav_item(sender, request: HttpRequest, **kwargs):
    """
    Adds a navigation item for the Sales Map to the event control panel sidebar.
    """
    # Check if the user has the required permission for the current event
    has_permission = request.user.has_event_permission(
        request.organizer, request.event, REQUIRED_MAP_PERMISSION, request=request
    )
    if not has_permission:
        return []  # Return empty list if user lacks permission

    # Try to generate the URL for the map view
    try:
        map_url = reverse(MAP_VIEW_URL_NAME, kwargs={
            'organizer': request.organizer.slug,
            'event': request.event.slug,
        })
    except NoReverseMatch:
        logger.error(f"Could not reverse URL for map view '{MAP_VIEW_URL_NAME}'. Check urls.py.")
        return []  # Return empty list if URL cannot be generated

    # Check if the current page *is* the map page to set the 'active' state
    is_active = False
    if hasattr(request, 'resolver_match') and request.resolver_match:
        is_active = request.resolver_match.view_name == MAP_VIEW_URL_NAME

    # Define the navigation item dictionary
    nav_item = {
        'label': _('Sales Map'),  # Translatable label
        'url': map_url,
        'active': is_active,
        'icon': 'map-o',  # Font Awesome icon name (fa-map-o) - adjust if needed
        # 'category': _('Orders'), # Optional: Suggests category, placement might vary
    }

    # Return the item in a list
    return [nav_item]
