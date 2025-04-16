import logging
from django.dispatch import receiver
from django.urls import reverse, NoReverseMatch
from django.utils.translation import gettext_lazy as _
from django.http import HttpRequest
# Import Django settings to read config in web process
from django.conf import settings

# --- Pretix Signals ---
from pretix.base.signals import order_paid
from pretix.control.signals import nav_event

# --- Tasks ---
from .tasks import geocode_order_task
# --- Geocoding Default ---
from .geocoding import DEFAULT_NOMINATIM_USER_AGENT  # Import default

logger = logging.getLogger(__name__)

# --- Constants ---
MAP_VIEW_URL_NAME = 'plugins:pretix_mapplugin:event.settings.salesmap.show'
REQUIRED_MAP_PERMISSION = 'can_view_orders'
PLUGIN_NAME = 'pretix_mapplugin'  # Define plugin name for settings access


# --- Signal Receiver for Geocoding (Reads setting, passes to task) ---
@receiver(order_paid, dispatch_uid="sales_mapper_order_paid_geocode")
def trigger_geocoding_on_payment(sender, order, **kwargs):
    """
    Listens for the order_paid signal, reads geocoding config,
    and queues the geocoding task with the config.
    """
    user_agent = DEFAULT_NOMINATIM_USER_AGENT  # Start with default
    try:
        # --- Read User-Agent from settings (works in web process) ---
        # Check structure defensively before accessing
        if hasattr(settings, 'plugins') and hasattr(settings.plugins, PLUGIN_NAME):
            plugin_settings = getattr(settings.plugins, PLUGIN_NAME)
            user_agent = plugin_settings.get(
                'nominatim_user_agent',  # Setting name in pretix.cfg
                DEFAULT_NOMINATIM_USER_AGENT
            )
        else:
            logger.warning(
                f"Could not access settings.plugins.{PLUGIN_NAME}, "
                "using default Nominatim User-Agent for task."
            )

        # --- Queue task with user_agent as keyword argument ---
        geocode_order_task.apply_async(
            args=[order.pk],
            kwargs={'nominatim_user_agent': user_agent}  # Pass as kwarg
        )
        logger.info(f"Geocoding task queued for paid order {order.code} (PK: {order.pk}).")

    except ImportError:  # Error finding geocode_order_task itself if tasks.py fails
        logger.exception("Could not import geocode_order_task. Check tasks.py.")
    except Exception as e:
        logger.exception(f"Failed to queue geocoding task for order {order.code}: {e}")


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
