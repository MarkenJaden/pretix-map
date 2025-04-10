import logging

from django.dispatch import receiver
from django.urls import resolve, Resolver404
from django.http import HttpRequest, HttpResponse
from django.utils.translation import gettext_lazy as _

# --- Import the CORRECT CSP helpers from Pretix ---
from pretix.base.middleware import _parse_csp, _merge_csp, _render_csp

# --- Signals ---
from pretix.base.signals import order_paid
# Use process_response for CSP header modification
from pretix.presale.signals import process_response

# --- Tasks ---
from .tasks import geocode_order_task

# --- Logging ---
logger = logging.getLogger(__name__)

# --- Constants ---
EXPECTED_MAP_VIEW_NAME = 'plugins:pretix_mapplugin:event.settings.salesmap.show'
# Note: No need for CSP_IMG_SRC_ADDITIONS constant, define directly in additions dict

# --- Helper function to get the CORE Pretix nonce ---
def _get_request_nonce(request: HttpRequest):
    """ Safely retrieves the core Pretix CSP nonce from the request object. """
    return getattr(request, 'csp_nonce', None) # Return None if not found


# --- Signal Receiver for Geocoding ---

@receiver(order_paid, dispatch_uid="sales_mapper_order_paid_geocode")
def trigger_geocoding_on_payment(sender, order, **kwargs):
    """ Listens for the order_paid signal and queues the geocoding task. """
    try:
        geocode_order_task.apply_async(args=[order.pk])
        logger.info(f"Geocoding task queued for paid order {order.code} (PK: {order.pk}).")
    except Exception as e:
        logger.exception(f"Failed to queue geocoding task for order {order.code}: {e}")


# --- Signal Receiver for Modifying CSP Header ---

@receiver(signal=process_response, dispatch_uid="sales_mapper_csp_header_modify")
def modify_csp_header_for_map(sender, request: HttpRequest, response: HttpResponse, **kwargs):
    """
    Listens for the process_response signal and modifies the CSP header
    specifically for the sales map view using Pretix's internal helpers.
    """
    # 1. Check if it's the map view URL we need to modify
    try:
        url = resolve(request.path_info)
        if url.view_name != EXPECTED_MAP_VIEW_NAME:
            return response # Not our map view, do nothing
    except Resolver404:
        return response # Not a resolvable view, do nothing

    # 2. Get the core Pretix nonce
    nonce = _get_request_nonce(request)
    # We *expect* the nonce to be available here, but log if not.
    # The SecurityMiddleware runs later and should generate the final header.
    # Our goal is to add our required sources so the merge works.
    if not nonce:
        logger.warning("Core Pretix CSP Nonce not found on request during process_response for map view.")

    # 3. Parse existing CSP header using Pretix's helper
    if 'Content-Security-Policy' in response:
        header_value = response['Content-Security-Policy']
        if isinstance(header_value, bytes):
             header_value = header_value.decode('utf-8')
        current_csp = _parse_csp(header_value)
        logger.debug(f"Original CSP header found by plugin: {header_value}")
    else:
        current_csp = {}
        logger.debug("No existing CSP header found by plugin.")

    # 4. Define CSP additions needed for the map
    map_csp_additions = {
        # Add the core Pretix nonce value to script-src
        'script-src': [f"'nonce-{nonce}'"] if nonce else ["'self' 'unsafe-inline'"],
        # Add the OpenStreetMap domain to img-src
        'img-src': ['https://*.tile.openstreetmap.org'],
        # Add style-src unsafe-inline ONLY if you still need it (i.e., didn't fix inline style)
        # 'style-src': ["'unsafe-inline'"],
    }

    # 5. Merge additions into the policy using Pretix's helper
    _merge_csp(current_csp, map_csp_additions)
    logger.debug(f"CSP dict after plugin merge: {current_csp}")

    # 6. Render and set the new/modified CSP header using Pretix's helper
    if current_csp:
        new_header_value = _render_csp(current_csp)
        response['Content-Security-Policy'] = new_header_value
        logger.debug(f"Plugin setting modified CSP header to: {new_header_value}")
    # If current_csp is still empty after merge, don't set the header

    return response