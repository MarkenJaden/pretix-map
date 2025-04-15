import logging

# --- Import Django settings ---
from django.conf import settings
from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim
from time import sleep

# Configure logging for your plugin
logger = logging.getLogger(__name__)

# --- Configuration Default ---
# Define a default/fallback User-Agent. Users *should* override this in pretix.cfg.
DEFAULT_NOMINATIM_USER_AGENT = "pretix-map-plugin/unknown (Please configure nominatim_user_agent in pretix.cfg)"


# --- Geocoding Function ---

def geocode_address(address_string: str) -> tuple[float, float] | None:
    """
    Tries to geocode a given address string using Nominatim, reading the
    User-Agent from Pretix configuration.

    Args:
        address_string: A single string representing the address.

    Returns:
        A tuple (latitude, longitude) if successful, otherwise None.
    """
    # --- Get User-Agent from Pretix Settings ---
    # Access plugin settings via settings.plugins.<your_plugin_name>
    # The .get() method allows providing a default value if the setting is missing.
    user_agent = settings.plugins.pretix_mapplugin.get(
        'nominatim_user_agent',  # The setting name defined in pretix.cfg
        DEFAULT_NOMINATIM_USER_AGENT
    )

    # Log a warning if the default User-Agent is being used, as it's required
    # by Nominatim policy to be specific and include contact info.
    if user_agent == DEFAULT_NOMINATIM_USER_AGENT:
        logger.warning(
            "Using default Nominatim User-Agent. Please set a specific "
            "'nominatim_user_agent' under [pretix_mapplugin] in your "
            "pretix.cfg according to Nominatim's usage policy."
        )
    # --- End Settings Retrieval ---

    # Initialize the geolocator with the configured or default user_agent
    geolocator = Nominatim(user_agent=user_agent)

    try:
        # Add a 1-second delay to respect Nominatim's usage policy (1 req/sec)
        sleep(1)

        location = geolocator.geocode(address_string, timeout=10)

        if location:
            logger.debug(
                f"Geocoded '{address_string}' to ({location.latitude}, {location.longitude}) using User-Agent: {user_agent}")
            return (location.latitude, location.longitude)
        else:
            logger.warning(f"Could not geocode address: {address_string} (Address not found by Nominatim)")
            return None

    except GeocoderTimedOut:
        logger.error(f"Geocoding timed out for address: {address_string}")
        return None
    except GeocoderServiceError as e:
        logger.error(f"Geocoding service error for address '{address_string}': {e}")
        return None
    except Exception as e:
        logger.exception(f"An unexpected error occurred during geocoding for address '{address_string}': {e}")
        return None


# --- Helper to Format Address from Pretix Order (No changes needed here) ---

def get_formatted_address_from_order(order) -> str | None:
    """
    Creates a formatted address string from a Pretix order's invoice address.
    """
    if not order.invoice_address:
        return None
    parts = []
    if order.invoice_address.street: parts.append(order.invoice_address.street)
    if order.invoice_address.city: parts.append(order.invoice_address.city)
    if order.invoice_address.zipcode: parts.append(order.invoice_address.zipcode)
    if order.invoice_address.state: parts.append(order.invoice_address.state)
    if order.invoice_address.country: parts.append(str(order.invoice_address.country.name))
    if not parts: return None
    full_address = ", ".join(filter(None, parts))
    return full_address


# --- Example Usage (Conceptual - No changes needed here) ---
# This function itself isn't called directly, the logic is in tasks.py
def process_order_for_geocoding(order):
    """Conceptual function showing how to use the geocoding."""
    address_str = get_formatted_address_from_order(order)
    if not address_str:
        logger.info(f"Order {order.code} has no invoice address to geocode.")
        return None

    coordinates = geocode_address(address_str)  # This now uses the configured User-Agent

    if coordinates:
        latitude, longitude = coordinates
        logger.info(f"Successfully geocoded Order {order.code}: ({latitude}, {longitude})")
        # Store coordinates...
        return coordinates
    else:
        logger.warning(f"Failed to geocode Order {order.code} with address: {address_str}")
        return None
