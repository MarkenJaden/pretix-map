import logging
from django.http import JsonResponse, HttpResponseForbidden
from django.views.generic import View # Using class-based view for structure
from pretix.control.permissions import event_permission_required # Permission decorator
from pretix.base.models import Event # To check permissions against
from .models import OrderGeocodeData # Our model from Step 4

logger = logging.getLogger(__name__)

class SalesMapDataView(View):
    """
    Provides geocoded coordinate data for an event's paid orders.
    Accessible via GET request.
    """

    @event_permission_required('can_view_orders') # Require permission to view orders
    def get(self, request, *args, **kwargs):
        """
        Handles GET requests to fetch coordinate data.

        Args:
            request: The HttpRequest object.
            *args, **kwargs: Captured URL parameters (organizer, event).

        Returns:
            JsonResponse containing a list of coordinates or an error response.
        """
        event = self.request.event # Event object is attached by Pretix middleware

        try:
            # Query the OrderGeocodeData model
            # Filter by orders belonging to the current event
            # We only want orders that actually have geocode data stored
            geocode_entries = OrderGeocodeData.objects.filter(
                order__event=event
            ).select_related('order') # Optional: select_related if you need order info

            # Format the data for JSON response
            # A simple list of [lat, lon] pairs is often useful for mapping libraries
            coordinates = [
                [entry.latitude, entry.longitude]
                for entry in geocode_entries
                if entry.latitude is not None and entry.longitude is not None # Ensure valid coords
            ]

            # Alternatively, list of objects:
            # coordinates = [
            #     {'lat': entry.latitude, 'lon': entry.longitude}
            #     for entry in geocode_entries
            #     if entry.latitude is not None and entry.longitude is not None
            # ]

            logger.debug(f"Returning {len(coordinates)} coordinates for event {event.slug}")

            return JsonResponse({'coordinates': coordinates})

        except Exception as e:
            logger.exception(f"Error retrieving geocode data for event {event.slug}: {e}")
            # Return a generic server error response
            return JsonResponse({'error': 'Could not retrieve coordinate data.'}, status=500)

# You might also have the view for the HTML page that *contains* the map here:
from django.shortcuts import render
from django.views import View
from pretix.control.views.event import EventSettingsViewMixin # For consistent look & feel

class SalesMapView(EventSettingsViewMixin, View):
     """
     Renders the HTML page that will contain the interactive map.
     """
     permission = 'can_view_orders' # Same permission as the data endpoint
     template_name = 'pretix_mapplugin/map_page.html' # Path to your template

     def get(self, request, *args, **kwargs):
         # This view just needs to render the template.
         # The actual map data will be fetched by JavaScript calling the API view.
         context = self.get_context_data(**kwargs)
         return render(request, self.template_name, context)