import logging
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import FieldDoesNotExist

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
        raise ImportError("Cannot find Pretix settings accessor.")

# --- Import necessary Pretix models ---
from pretix.base.models import Order, Event, Organizer

# --- Import your Geocode model and the task ---
from pretix_mapplugin.models import OrderGeocodeData
from pretix_mapplugin.tasks import geocode_order_task
# --- Import Default User-Agent ---
from pretix_mapplugin.geocoding import DEFAULT_NOMINATIM_USER_AGENT

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Scans paid orders and queues geocoding tasks for those missing geocode data.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--organizer', type=str, help='Slug of a specific organizer to process orders for.',
        )
        parser.add_argument(
            '--event', type=str, help='Slug of a specific event to process orders for. Requires --organizer.',
        )
        parser.add_argument(
            '--dry-run', action='store_true', help='Simulate the process without actually queuing tasks.',
        )
        parser.add_argument(
            '--force-recode', action='store_true',
            help='Queue geocoding even for orders that already have geocode data.',
        )

    def handle(self, *args, **options):
        organizer_slug = options['organizer']
        event_slug = options['event']
        dry_run = options['dry_run']
        force_recode = options['force_recode']

        if event_slug and not organizer_slug:
            raise CommandError("You must specify --organizer when using --event.")

        # --- Read User-Agent using Pretix Settings accessor ---
        user_agent = DEFAULT_NOMINATIM_USER_AGENT
        try:
            # Get settings holder instance
            gs = SettingsProxy()
            # Construct the setting key specific to plugins
            # Format might be 'plugin:plugin_name:setting_name' or just 'plugin_name_setting_name'
            # Check Pretix docs or experiment if needed. Assuming the former.
            setting_key = 'plugin:pretix_mapplugin:nominatim_user_agent'
            user_agent = gs.settings.get(setting_key, DEFAULT_NOMINATIM_USER_AGENT)

            if user_agent == DEFAULT_NOMINATIM_USER_AGENT:
                self.stdout.write(self.style.WARNING(
                    "Using default Nominatim User-Agent. Please set a specific "
                    f"'{setting_key}' in your pretix.cfg."
                ))
        except Exception as e:
            # Catch broad exception during settings access
            self.stderr.write(self.style.ERROR(f"Failed to read plugin settings: {e}. Using default User-Agent."))
            # Continue with default user_agent
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
        total_queued = 0
        total_skipped = 0
        total_processed_orders = 0

        # --- Iterate through organizers and activate scope ---
        for organizer in organizers_to_process:
            self.stdout.write(f"\n--- Processing Organizer: {organizer.name} ({organizer.slug}) ---")

            with scope(organizer=organizer):
                # --- Get orders ---
                orders_qs = Order.objects.filter(status=Order.STATUS_PAID)

                # --- Filter by event if specified ---
                if event_slug and organizer.slug == organizer_slug:
                    try:
                        event = Event.objects.get(slug=event_slug)
                        orders_qs = orders_qs.filter(event=event)
                        self.stdout.write(f"  Filtering orders for event: {event.name} ({event_slug})")
                    except Event.DoesNotExist:
                        self.stderr.write(self.style.WARNING(
                            f"  Event '{event_slug}' not found for this organizer. Skipping event filter."))
                        if organizer_slug and event_slug: continue

                # --- Filter orders needing geocoding ---
                relation_name = 'geocode_data'  # Ensure this matches your model
                if not force_recode:
                    try:
                        Order._meta.get_field(relation_name)  # Check existence
                        orders_to_process_qs = orders_qs.filter(**{f'{relation_name}__isnull': True})
                        self.stdout.write("  Selecting paid orders missing geocode data...")
                    except FieldDoesNotExist:
                        self.stderr.write(
                            self.style.ERROR(f"  Relation '{relation_name}' not found. Skipping organizer."))
                        continue
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"  Error checking relation: {e}. Skipping organizer."))
                        continue
                else:
                    orders_to_process_qs = orders_qs
                    self.stdout.write(self.style.WARNING("  Processing ALL selected paid orders (--force-recode)..."))

                # --- Process orders for this scope ---
                current_org_orders_count = orders_to_process_qs.count()
                all_checked_for_org = orders_qs.count()
                total_processed_orders += all_checked_for_org

                if current_org_orders_count == 0:
                    self.stdout.write(f"  No orders need geocoding ({all_checked_for_org} checked).")
                    continue

                self.stdout.write(
                    f"  Found {current_org_orders_count} order(s) to potentially geocode ({all_checked_for_org} checked).")
                org_queued = 0
                org_skipped = 0

                for order in orders_to_process_qs.iterator():
                    if dry_run:
                        self.stdout.write(
                            f"    [DRY RUN] Would queue Order: {order.code} (PK: {order.pk}) Event: {order.event.slug}")
                        org_queued += 1
                    else:
                        try:
                            # --- Pass user_agent to task ---
                            geocode_order_task.apply_async(
                                args=[order.pk],
                                kwargs={'nominatim_user_agent': user_agent}  # Pass as kwarg
                            )
                            org_queued += 1
                        except Exception as e:
                            self.stderr.write(self.style.ERROR(f"    ERROR queuing Order {order.code}: {e}"))
                            logger.exception(f"Failed to queue geocoding task via command for order {order.code}: {e}")
                            org_skipped += 1

                self.stdout.write(f"  Queued: {org_queued}, Skipped: {org_skipped} for this organizer.")
                total_queued += org_queued
                total_skipped += org_skipped
            # End scope

        # --- Final Report ---
        self.stdout.write("=" * 40)
        self.stdout.write("Overall Summary:")
        self.stdout.write(f"  Organizers processed: {len(organizers_to_process)}")
        self.stdout.write(f"  Total orders checked (paid): {total_processed_orders}")
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"[DRY RUN] Complete. Would have queued tasks for {total_queued} order(s)."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Complete. Queued tasks for {total_queued} order(s)."))
            if total_skipped > 0:
                self.stdout.write(
                    self.style.WARNING(f"Skipped {total_skipped} order(s) total due to errors during queueing."))
        self.stdout.write("=" * 40)
