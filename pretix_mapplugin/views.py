import logging
from django.http import JsonResponse # Keep JsonResponse
from django.views.generic import View, TemplateView
# Import the mixin
from pretix.control.views.event import EventSettingsViewMixin
# Remove the specific permission decorator import if no longer used directly
# from pretix.control.permissions import event_permission_required
from pretix.base.models import Event # Keep if needed elsewhere
from .models import OrderGeocodeData

logger = logging.getLogger(__name__)

# --- API Data View (Corrected) ---
class SalesMapDataView(EventSettingsViewMixin, View): # Inherit Mixin first
    """
    Provides geocoded coordinate data for an event's paid orders.
    Permissions are handled by the EventSettingsViewMixin based on the 'permission' attribute.
    """
    permission = 'can_view_orders' # Define permission for the Mixin to check

    # REMOVE the decorator from the 'get' method
    # @event_permission_required('can_view_orders') <-- Remove this line
    def get(self, request, *args, **kwargs):
        """
        Handles GET requests to fetch coordinate data.
        The EventSettingsViewMixin ensures permissions are checked before this runs,
        and self.request.event is available.
        """
        # Access event via self.request.event provided by the mixin
        event = self.request.event

        try:
            geocode_entries = OrderGeocodeData.objects.filter(
                order__event=event
            ).select_related('order') # Assuming OrderGeocodeData has 'order' field

            coordinates = [
                [entry.latitude, entry.longitude]
                for entry in geocode_entries
                if entry.latitude is not None and entry.longitude is not None
            ]

            logger.debug(f"Returning {len(coordinates)} coordinates for event {event.slug}")
            return JsonResponse({'coordinates': coordinates})

        except Exception as e:
            logger.exception(f"Error retrieving geocode data for event {event.slug}: {e}")
            return JsonResponse({'error': 'Could not retrieve coordinate data.'}, status=500)


# --- HTML Page View (Should be correct from previous step) ---
class SalesMapView(EventSettingsViewMixin, TemplateView):
     permission = 'can_view_orders'
     template_name = 'pretix_mapplugin/map_page.html' # Corrected template path likely needed

     # No need to override get or get_context_data unless adding custom context