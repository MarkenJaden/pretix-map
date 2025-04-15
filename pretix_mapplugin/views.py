import logging
from django.http import JsonResponse, HttpResponse
from django.views.generic import View, TemplateView
from django.utils.translation import gettext_lazy as _
from pretix.control.views.event import EventSettingsViewMixin
from .models import OrderGeocodeData

# --- Import CSP helpers ---
try:
    from pretix.base.csp import _parse_csp, _merge_csp, _render_csp
except ImportError:
    from pretix.base.middleware import _parse_csp, _merge_csp, _render_csp

logger = logging.getLogger(__name__)


class SalesMapDataView(EventSettingsViewMixin, View):
    permission = 'can_view_orders'

    def get(self, request, *args, **kwargs):
        event = self.request.event
        try:
            geocode_entries = OrderGeocodeData.objects.filter(
                order__event=event, latitude__isnull=False, longitude__isnull=False
            ).select_related('order')
            coordinates = [
                {"lat": entry.latitude, "lon": entry.longitude, "tooltip": f"Order: {entry.order.code}"}
                for entry in geocode_entries
            ]
            logger.debug(f"Returning {len(coordinates)} coordinates for event {event.slug}")
            return JsonResponse({'locations': coordinates})
        except OrderGeocodeData.DoesNotExist:
            logger.info(f"No geocode data found for event {event.slug}")
            return JsonResponse({'locations': []})
        except Exception as e:
            logger.exception(f"Error retrieving geocode data for event {event.slug}: {e}")
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
