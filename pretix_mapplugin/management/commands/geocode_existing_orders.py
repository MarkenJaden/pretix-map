import logging
import time  # Import time for sleep
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist
from django.db import transaction

# --- Import Pretix Global Settings accessor ---
from django_scopes import scope

# Check if Pretix version uses AbstractSettingsHolder or GlobalSettingsObject
# Adjust import based on Pretix version if needed. Assume AbstractSettingsHolder for newer Pretix.
try:
    from pretix.base.settings import GlobalSettingsObject as SettingsProxy
except ImportError:
    try:
        # Older pretix might use this pattern
        from pretix.base.services.config import load_config


        class SettingsProxy:
            def __init__(self):
                self.settings = load_config()
    except ImportError:
        # Fallback or raise error if neither is found
        logger.error("Could not determine Pretix settings accessor for management command.")


        # This will likely cause the command to fail later, but allows it to start
        class SettingsProxy:
            def __init__(self): self.settings = {}  # Empty dict to avoid errors later

# --- Import necessary Pretix models ---
from pretix.base.models import Order, Event, Organizer

# --- Import your Geocode model and geocoding functions ---
from pretix_mapplugin.models import OrderGeocodeData
# --- Import geocoding functions directly, NOT the task ---
from pretix_mapplugin.geocoding import (
    geocode_address,
    get_formatted_address_from_order,
    DEFAULT_NOMINATIM_USER_AGENT
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = ('Scans paid orders and geocodes addresses for those missing geocode data directly '
            'within the command, respecting Nominatim rate limits (approx 1 req/sec). '
            'This can take a long time for many orders.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--organizer', type=str, help='Slug of a specific organizer to process orders for.',
        )
        parser.add_argument(
            '--event', type=str, help='Slug of a specific event to process orders for. Requires --organizer.',
        )
        parser.add_argument(
            '--dry-run', action='store_true', help='Simulate without geocoding or saving.',
        )
        parser.add_argument(
            '--force-recode', action='store_true',
            help='Geocode even for orders that already have geocode data.',
        )
        parser.add_argument(
            '--delay', type=float, default=1.1,
            help='Delay in seconds between geocoding requests (default: 1.1 to be safe). Set to 0 to disable.'
        )

    def handle(self, *args, **options):
        organizer_slug = options['organizer']
        event_slug = options['event']
        dry_run = options['dry_run']
        force_recode = options['force_recode']
        delay = options['delay']

        if delay < 1.0 and delay != 0:  # Allow disabling delay with 0
            self.stdout.write(self.style.WARNING(
                f"Delay is {delay}s, which is less than 1 second. This may violate Nominatim usage policy."))
        elif delay == 0:
            self.stdout.write(
                self.style.WARNING("Delay is disabled (--delay 0). Ensure you comply with geocoding service terms."))

        if event_slug and not organizer_slug:
            raise CommandError("You must specify --organizer when using --event.")

        # --- Read User-Agent using Pretix Settings accessor ---
        user_agent = DEFAULT_NOMINATIM_USER_AGENT
        try:
            gs = SettingsProxy()
            setting_key = 'plugin:pretix_mapplugin:nominatim_user_agent'
            # Use .get() which is safer for dictionaries possibly returned by load_config
            user_agent = getattr(gs, 'settings', {}).get(setting_key, DEFAULT_NOMINATIM_USER_AGENT)

            if user_agent == DEFAULT_NOMINATIM_USER_AGENT:
                self.stdout.write(self.style.WARNING(
                    "Using default Nominatim User-Agent. Please set a specific "
                    f"'{setting_key}' in your pretix.cfg."
                ))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to read plugin settings: {e}. Using default User-Agent."))
        # --- End Read User-Agent ---

        # --- Determine which organizers to process ---
        organizers_to_process = []
        if organizer_slug:
            try:
                organizer = Organizer.objects.get(slug=organizer_slug)
                organizers_to_process.append(organizer)
                self.stdout.write(f"Processing specified organizer: {organizer.name} ({organizer_slug})")
            except Organizer.DoesNotExist:
                raise CommandError(f"Organizer with slug '{organizer_slug}' not found.")
        else:
            organizers_to_process = list(Organizer.objects.all())
            self.stdout.write(f"Processing all {len(organizers_to_process)} organizers...")

        # --- Initialize counters ---
        total_processed_count = 0  # Orders actually attempted (had address or forced)
        total_geocoded_success = 0
        total_geocode_failed = 0  # Geocoder returned None
        total_skipped_no_address = 0
        total_skipped_db_error = 0
        total_checked_count = 0  # All orders matching initial filter

        # --- Iterate through organizers ---
        for organizer in organizers_to_process:
            self.stdout.write(f"\n--- Processing Organizer: {organizer.name} ({organizer.slug}) ---")
            # current_organizer_pk = organizer.pk # No longer needed for task

            with scope(organizer=organizer):
                # --- Get orders ---
                orders_qs = Order.objects.filter(status=Order.STATUS_PAID).select_related(
                    'invoice_address', 'event'
                )

                # --- Filter by event ---
                if event_slug and organizer.slug == organizer_slug:
                    try:
                        event = Event.objects.get(slug=event_slug)
                        orders_qs = orders_qs.filter(event=event)
                        self.stdout.write(f"  Filtering for event: {event.name} ({event_slug})")
                    except Event.DoesNotExist:
                        self.stderr.write(
                            self.style.WARNING(f"  Event '{event_slug}' not found. Skipping event filter."))
                        if organizer_slug and event_slug: continue

                # --- Determine which orders to process ---
                relation_name = 'geocode_data'  # Check model
                orders_to_geocode_list = []
                current_checked_count = orders_qs.count()  # Count before filtering for geocode status
                total_checked_count += current_checked_count

                if force_recode:
                    orders_to_geocode_list = list(orders_qs)
                    self.stdout.write(self.style.WARNING(
                        f"  Will process all {len(orders_to_geocode_list)} orders (--force-recode)..."))
                else:
                    try:
                        Order._meta.get_field(relation_name)
                        existing_pks = set(OrderGeocodeData.objects.filter(
                            order__in=orders_qs
                        ).values_list('order_id', flat=True))
                        orders_to_geocode_list = list(orders_qs.exclude(pk__in=existing_pks))
                        self.stdout.write(
                            f"  Found {len(orders_to_geocode_list)} orders missing geocode data (out of {current_checked_count} checked).")
                    except FieldDoesNotExist:
                        self.stderr.write(
                            self.style.ERROR(f"  Relation '{relation_name}' not found. Skipping organizer."))
                        continue
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"  Error checking relation: {e}. Skipping organizer."))
                        continue

                if not orders_to_geocode_list:
                    self.stdout.write("  No orders require geocoding for this selection.")
                    continue

                # --- Process Orders Sequentially ---
                count_this_org = 0
                org_geocoded = 0
                org_failed = 0
                org_skipped_no_addr = 0
                org_skipped_db = 0

                for i, order in enumerate(orders_to_geocode_list):
                    count_this_org += 1
                    self.stdout.write(
                        f"  Processing order {count_this_org}/{len(orders_to_geocode_list)}: {order.code} ...",
                        ending="")

                    address_str = get_formatted_address_from_order(order)
                    if not address_str:
                        self.stdout.write(self.style.WARNING(" No address. Skipping."))
                        total_skipped_no_address += 1
                        org_skipped_no_addr += 1
                        # Save null coords to prevent re-processing if not forcing
                        if not dry_run and not force_recode:
                            try:
                                with transaction.atomic():
                                    OrderGeocodeData.objects.update_or_create(order=order, defaults={'latitude': None,
                                                                                                     'longitude': None})
                            except Exception as db_err:
                                self.stdout.write(self.style.ERROR(f" FAILED (DB Error saving null: {db_err})"))
                                logger.exception(
                                    f"Failed to save null geocode data via command for order {order.code}: {db_err}")
                                total_skipped_db_error += 1
                                org_skipped_db += 1
                        continue  # Move to next order

                    # Only increment this if we actually attempt geocoding
                    total_processed_count += 1

                    if dry_run:
                        self.stdout.write(self.style.SUCCESS(" [DRY RUN] Would geocode."))
                        org_geocoded += 1  # Simulate success for dry run count
                    else:
                        # --- Perform Geocoding Directly ---
                        coordinates = geocode_address(address_str, nominatim_user_agent=user_agent)

                        # --- Save Result ---
                        try:
                            with transaction.atomic():
                                obj, created = OrderGeocodeData.objects.update_or_create(
                                    order=order,
                                    defaults={'latitude': coordinates[0] if coordinates else None,
                                              'longitude': coordinates[1] if coordinates else None}
                                )
                            if coordinates:
                                self.stdout.write(
                                    self.style.SUCCESS(f" OK ({coordinates[0]:.4f}, {coordinates[1]:.4f})"))
                                org_geocoded += 1
                            else:
                                self.stdout.write(self.style.WARNING(" FAILED (Geocode returned None)"))
                                org_failed += 1
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f" FAILED (DB Error: {e})"))
                            logger.exception(f"Failed to save geocode data via command for order {order.code}: {e}")
                            org_skipped_db += 1  # Count DB errors separately

                        # --- Apply Delay ---
                        if delay > 0 and i < len(
                                orders_to_geocode_list) - 1:  # Don't sleep after the last one or if delay is 0
                            time.sleep(delay)

                # Add org counts to totals
                total_geocoded_success += org_geocoded
                total_geocode_failed += org_failed
                total_skipped_db_error += org_skipped_db

                self.stdout.write(f"  Finished Organizer: Succeeded: {org_geocoded}, Failed Geocode: {org_failed}, "
                                  f"Skipped (No Addr): {org_skipped_no_addr}, Skipped (DB Err): {org_skipped_db}.")
            # End scope

        # --- Final Overall Report ---
        self.stdout.write("=" * 40)
        self.stdout.write("Overall Geocoding Summary:")
        self.stdout.write(f"  Organizers processed: {len(organizers_to_process)}")
        self.stdout.write(f"  Total Orders Checked (paid, matching filters): {total_checked_count}")
        self.stdout.write(f"  Total Orders Attempted (had address or forced): {total_processed_count}")
        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"[DRY RUN] Complete. Would have attempted geocoding for {total_processed_count} orders "
                f"(+ {total_skipped_no_address} skipped due to no address)."))
        else:
            self.stdout.write(self.style.SUCCESS(f"  Successfully Geocoded & Saved: {total_geocoded_success}"))
            self.stdout.write(self.style.WARNING(f"  Geocoding Failed (None returned): {total_geocode_failed}"))
            self.stdout.write(f"  Skipped (No Address): {total_skipped_no_address}")
            if total_skipped_db_error > 0:
                self.stdout.write(self.style.ERROR(f"  Skipped (DB Save Error): {total_skipped_db_error} (check logs)"))
        self.stdout.write("=" * 40)
