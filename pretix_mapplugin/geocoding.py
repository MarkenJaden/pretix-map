import logging
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from time import sleep

# DO NOT import settings here, as it won't work reliably in Celery

logger = logging.getLogger(__name__)

# Define a default/fallback User-Agent. Users *should* override this in pretix.cfg.
DEFAULT_NOMINATIM_USER_AGENT = "pretix-map-plugin/unknown (Please configure nominatim_user_agent in pretix.cfg)"


# --- Geocoding Function (Accepts user_agent) ---
def geocode_address(address_string: str, nominatim_user_agent: str | None = None) -> tuple[float, float] | None:
    """
    Tries to geocode a given address string using Nominatim, using the
    provided User-Agent string.

    Args:
        address_string: A single string representing the address.
        nominatim_user_agent: The User-Agent string to use for Nominatim.

    Returns:
        A tuple (latitude, longitude) if successful, otherwise None.
    """
    # Use the provided User-Agent or the default
    user_agent = nominatim_user_agent or DEFAULT_NOMINATIM_USER_AGENT

    if user_agent == DEFAULT_NOMINATIM_USER_AGENT:
        # Log warning if default is used - admins should configure this
        logger.warning(
            "Using default Nominatim User-Agent. Please set a specific "
            "'nominatim_user_agent' under [pretix_mapplugin] in your "
            "pretix.cfg according to Nominatim's usage policy."
        )

    # Initialize the geolocator with the determined user_agent
    geolocator = Nominatim(user_agent=user_agent)

    try:
        # Add a 1-second delay to respect Nominatim's usage policy (1 req/sec)
        sleep(1)

        # Perform geocoding
        location = geolocator.geocode(address_string, timeout=10)  # 10-second timeout

        if location:
            logger.debug(
                f"Geocoded '{address_string}' to ({location.latitude}, {location.longitude}) using User-Agent: {user_agent}"
            )
            return (location.latitude, location.longitude)
        else:
            logger.warning(f"Could not geocode address: {address_string} (Address not found by Nominatim)")
            return None

    except GeocoderTimedOut:
        logger.error(f"Geocoding timed out for address: {address_string}")
        return None
    except GeocoderServiceError as e:
        # Log specific service errors (e.g., API limits, server issues)
        logger.error(f"Geocoding service error for address '{address_string}': {e}")
        return None
    except Exception as e:
        # Catch any other unexpected exceptions during geocoding
        logger.exception(f"An unexpected error occurred during geocoding for address '{address_string}': {e}")
        return None


# --- Helper to Format Address from Pretix Order ---
def get_formatted_address_from_order(order) -> str | None:
    """
    Creates a formatted address string from a Pretix order's invoice address.

    Args:
        order: A Pretix `Order` object.

    Returns:
        A formatted address string suitable for geocoding, or None if no address.
    """
    # Ensure order and invoice_address exist
    if not order or not order.invoice_address:
        return None

    parts = []
    addr = order.invoice_address  # Shortcut

    # Add components in a likely useful order for geocoding
    if addr.street: parts.append(addr.street)
    if addr.city: parts.append(addr.city)
    if addr.zipcode: parts.append(addr.zipcode)
    if addr.state: parts.append(addr.state)
    # Use the full country name if possible, geocoders often prefer it
    if addr.country: parts.append(str(addr.country.name))

    # Only return an address if we have useful parts
    if not parts:
        return None

    # Join parts with commas. Geocoders are usually good at parsing this.
    full_address = ", ".join(filter(None, parts))  # filter(None,...) removes empty strings
    return full_address
