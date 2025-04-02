import logging
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from time import sleep

# Configure logging for your plugin
logger = logging.getLogger(__name__)

# --- Geocoding Function ---

def geocode_address(address_string: str) -> tuple[float, float] | None:
    """
    Tries to geocode a given address string using Nominatim.

    Args:
        address_string: A single string representing the address.

    Returns:
        A tuple (latitude, longitude) if successful, otherwise None.
    """
    # IMPORTANT: Set a unique user_agent. Replace 'YourPretixPluginSalesMapper/1.0'
    # with something specific to your plugin and email.
    # See Nominatim Usage Policy: https://operations.osmfoundation.org/policies/nominatim/
    geolocator = Nominatim(user_agent="PretixSalesMapperPlugin/1.0 (contact@example.com)") # CHANGE THIS

    try:
        # Nominatim prefers a single query string.
        # Adding a delay between requests is polite and often required.
        # Geopy's Nominatim adapter might handle some delays, but being explicit can help.
        sleep(1) # Add a 1-second delay to respect Nominatim's usage policy (1 req/sec)

        location = geolocator.geocode(address_string, timeout=10) # 10-second timeout

        if location:
            logger.debug(f"Geocoded '{address_string}' to ({location.latitude}, {location.longitude})")
            return (location.latitude, location.longitude)
        else:
            logger.warning(f"Could not geocode address: {address_string} (Address not found)")
            return None

    except GeocoderTimedOut:
        logger.error(f"Geocoding timed out for address: {address_string}")
        return None
    except GeocoderServiceError as e:
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
    if not order.invoice_address:
        return None

    parts = []
    # Add components in a likely order for geocoding
    # Adjust based on how your customers typically enter addresses
    if order.invoice_address.street:
        parts.append(order.invoice_address.street)
    if order.invoice_address.city:
        parts.append(order.invoice_address.city)
    if order.invoice_address.zipcode:
         parts.append(order.invoice_address.zipcode)
    # State/Province might be useful depending on the country
    if order.invoice_address.state:
         parts.append(order.invoice_address.state)
    if order.invoice_address.country:
        # Use the full country name if possible, geocoders often prefer it
        parts.append(str(order.invoice_address.country.name)) # Access the country name

    if not parts:
        return None

    # Join parts with commas. Geocoders are usually good at parsing this.
    full_address = ", ".join(filter(None, parts)) # filter(None,...) removes empty strings
    return full_address


# --- Example Usage (Conceptual - Integrate this logic into your tasks/views) ---

def process_order_for_geocoding(order):
    """Conceptual function showing how to use the geocoding."""
    address_str = get_formatted_address_from_order(order)
    if not address_str:
        logger.info(f"Order {order.code} has no invoice address to geocode.")
        return None

    coordinates = geocode_address(address_str)

    if coordinates:
        latitude, longitude = coordinates
        # **NEXT STEP (Part of Step 4): Store these coordinates!**
        # E.g., save_coordinates_for_order(order.pk, latitude, longitude)
        logger.info(f"Successfully geocoded Order {order.code}: ({latitude}, {longitude})")
        return coordinates
    else:
        # Handle failed geocoding (e.g., log it, maybe retry later)
        logger.warning(f"Failed to geocode Order {order.code} with address: {address_str}")
        return None