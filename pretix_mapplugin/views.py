import logging
from django.db.models import Prefetch  # Needed for prefetch_related optimization
from django.http import HttpResponse, JsonResponse  # Import HttpResponse

# --- CORRECTED IMPORTS ---
from django.urls import reverse  # Needed to generate URLs
from django.utils.formats import date_format  # For localized date formatting
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView, View
from pretix.base.models import Order  # Make sure Order is imported
from pretix.control.views.event import EventSettingsViewMixin

from .models import OrderGeocodeData

# --- END CORRECTED IMPORTS ---


# --- Import CSP helpers (Still needed for SalesMapView) ---
try:
    from pretix.base.csp import _merge_csp, _parse_csp, _render_csp
except ImportError:
    from pretix.base.middleware import _merge_csp, _parse_csp, _render_csp

logger = logging.getLogger(__name__)


# --- SalesMapDataView (Modified to provide more data) ---
class SalesMapDataView(EventSettingsViewMixin, View):
    permission = 'can_view_orders'

    def get(self, request, *args, **kwargs):
        event = self.request.event
        organizer = request.organizer  # Get organizer for URL generation

        locations_data = []  # Initialize list to hold data for JSON

        try:
            # Fetch geocode entries, prefetch related order and its positions
            geocode_entries = OrderGeocodeData.objects.filter(
                order__event=event,
                latitude__isnull=False,
                longitude__isnull=False
            ).select_related(
                'order'  # Select the direct foreign key
            ).prefetch_related(
                Prefetch('order__positions')  # Use Prefetch for better control if needed, or just 'order__positions'
            )

            for entry in geocode_entries:
                order = entry.order
                order_url = None
                tooltip_parts = []

                # 1. Generate Order URL
                try:
                    # Use the standard name for the control panel order detail view
                    # Ensure 'control:event.order' is the correct name in your Pretix version
                    order_url = reverse('control:event.order', kwargs={
                        'organizer': organizer.slug,
                        'event': event.slug,
                        'code': order.code,
                    })
                except Exception as e:
                    logger.warning(f"Could not reverse URL for order {order.code}: {e}")

                # 2. Build Tooltip String
                tooltip_parts.append(f"<strong>Order:</strong> {order.code}")

                # Format order date (using Django's localized formatting)
                try:
                    formatted_date = date_format(order.datetime, format='SHORT_DATETIME_FORMAT', use_l10n=True)
                    tooltip_parts.append(f"<strong>Date:</strong> {formatted_date}")
                except Exception as e:
                    logger.warning(f"Could not format date for order {order.code}: {e}")
                    tooltip_parts.append("<strong>Date:</strong> N/A")  # Fallback

                # Count positions (tickets/items) - efficient due to prefetch_related
                position_count = order.positions.count()  # count() is efficient on prefetched QuerySets
                tooltip_parts.append(f"<strong>Items:</strong> {position_count}")

                # Combine tooltip parts with HTML line breaks
                tooltip_string = "<br>".join(tooltip_parts)

                # 3. Append data to the list
                locations_data.append({
                    "lat": entry.latitude,
                    "lon": entry.longitude,
                    "tooltip": tooltip_string,  # The enhanced tooltip
                    "order_url": order_url,  # The URL for clicking
                })

            logger.debug(f"Returning {len(locations_data)} enriched coordinates for event {event.slug}")
            return JsonResponse({'locations': locations_data})

        except OrderGeocodeData.DoesNotExist:
            logger.info(f"No geocode data found for event {event.slug}")
            return JsonResponse({'locations': []})
        except Exception as e:
            logger.exception(f"Error retrieving or processing geocode data for event {event.slug}: {e}")
            # Provide a more generic error in production
            return JsonResponse({'error': _('Could not retrieve coordinate data due to a server error.')}, status=500)


class SalesMapView(EventSettingsViewMixin, TemplateView):
    permission = 'can_view_orders'
    template_name = 'pretix_mapplugin/map_page.html'

    def get(self, request, *args, **kwargs):
        try:
            response = super().get(request, *args, **kwargs)
        except Exception as e:
            logger.exception(f"Error rendering template {self.template_name}: {e}")
            return HttpResponse(_("Error loading map page."), status=500)

        logger.debug(f"View: Attempting CSP modification for {request.path}")

        # 2. Get existing CSP header
        current_csp = {}
        header_key = 'Content-Security-Policy'
        if header_key in response:
            header_value = response[header_key]
            if isinstance(header_value, bytes):
                header_value = header_value.decode('utf-8')
            try:
                current_csp = _parse_csp(header_value)
                logger.debug(f"View: Found existing CSP header: {header_value}")
            except Exception as e:
                logger.error(f"View: Error parsing existing CSP header '{header_value}': {e}")
                current_csp = {}
        else:
            logger.debug("View: No existing CSP header found.")
            current_csp = {}

        # 3. Define additions: img-src AND style-src
        map_csp_additions = {
            'img-src': [
                'https://*.tile.openstreetmap.org',
            ],
            'style-src': [
                "'unsafe-inline'",  # Allow inline styles needed by Leaflet/plugins
            ]
        }

        # 4. Merge additions
        try:
            _merge_csp(current_csp, map_csp_additions)
            logger.debug(f"View: CSP dict after merge: {current_csp}")
        except Exception as e:
            logger.error(f"View: Error merging CSP additions: {e}")

        # 5. Render and set the header
        if current_csp:
            try:
                new_header_value = _render_csp(current_csp)
                response[header_key] = new_header_value
                logger.info(f"View: Setting/modifying CSP header to: {new_header_value}")
            except Exception as e:
                logger.error(f"View: Error rendering final CSP header: {e}")
        else:
            logger.warning("View: CSP dictionary is empty after merge, header not set.")

        # 6. Return the modified response object
        return response
