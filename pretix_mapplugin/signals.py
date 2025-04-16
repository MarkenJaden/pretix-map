import logging
from django.dispatch import receiver
from django.urls import reverse, NoReverseMatch
from django.utils.translation import gettext_lazy as _
from django.http import HttpRequest
from django.conf import settings

# --- Pretix Signals ---
from pretix.base.signals import order_paid
from pretix.control.signals import nav_event

# --- Tasks ---
from .tasks import geocode_order_task
# --- Geocoding Default ---
from .geocoding import DEFAULT_NOMINATIM_USER_AGENT

logger = logging.getLogger(__name__)

# --- Constants ---
MAP_VIEW_URL_NAME = 'plugins:pretix_mapplugin:event.settings.salesmap.show'
REQUIRED_MAP_PERMISSION = 'can_view_orders'
PLUGIN_NAME = 'pretix_mapplugin'


# --- Signal Receiver for Geocoding (Passes organizer_pk) ---
@receiver(order_paid, dispatch_uid="sales_mapper_order_paid_geocode")
def trigger_geocoding_on_payment(sender, order, **kwargs):
    """
    Listens for the order_paid signal, reads geocoding config,
    and queues the geocoding task with order_pk, organizer_pk, and config.
    """
    user_agent = DEFAULT_NOMINATIM_USER_AGENT
    organizer_pk = None  # Initialize
    try:
        # Ensure order has event and organizer before proceeding
        if not order or not order.event or not order.event.organizer:
            logger.error(f"Order {order.code} is missing event or organizer information. Cannot queue task.")
            return

        organizer_pk = order.event.organizer.pk  # Get organizer PK

        # --- Read User-Agent from settings ---
        if hasattr(settings, 'plugins') and hasattr(settings.plugins, PLUGIN_NAME):
            plugin_settings = getattr(settings.plugins, PLUGIN_NAME)
            user_agent = plugin_settings.get('nominatim_user_agent', DEFAULT_NOMINATIM_USER_AGENT)
        else:
            logger.warning(f"Could not access settings.plugins.{PLUGIN_NAME}, using default User-Agent.")

        # --- Queue task with user_agent and organizer_pk as keyword arguments ---
        geocode_order_task.apply_async(
            args=[order.pk],  # Keep order_pk as positional argument
            kwargs={
                'nominatim_user_agent': user_agent,
                'organizer_pk': organizer_pk  # Pass organizer PK
            }
        )
        logger.info(f"Geocoding task queued for paid order {order.code} (PK: {order.pk}, Org PK: {organizer_pk}).")

    except ImportError:
        logger.exception("Could not import geocode_order_task. Check tasks.py.")
    except Exception as e:
        # Log the organizer PK as well if available
        org_info = f" (Org PK: {organizer_pk})" if organizer_pk else ""
        logger.exception(f"Failed to queue geocoding task for order {order.code}{org_info}: {e}")


# --- Signal Receiver for Adding Navigation Item (No changes needed) ---
@receiver(nav_event, dispatch_uid="sales_mapper_nav_event_add_map")
def add_map_nav_item(sender, request: HttpRequest, **kwargs):
    """
    Adds a navigation item for the Sales Map to the event control panel sidebar.
    """
    has_permission = request.user.has_event_permission(request.organizer, request.event, REQUIRED_MAP_PERMISSION,
                                                       request=request)
    if not has_permission: return []
    try:
        map_url = reverse(MAP_VIEW_URL_NAME, kwargs={
            'organizer': request.organizer.slug,
            'event': request.event.slug,
        })
    except NoReverseMatch:
        logger.error(f"Could not reverse URL for map view '{MAP_VIEW_URL_NAME}'. Check urls.py.")
        return []
    is_active = False
    if hasattr(request, 'resolver_match') and request.resolver_match:
        is_active = request.resolver_match.view_name == MAP_VIEW_URL_NAME
    return [{
        'label': _('Sales Map'),
        'url': map_url,
        'active': is_active,
        'icon': 'map-o',
    }]
