import logging
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import FieldDoesNotExist

# Import scope activation helpers
from django_scopes import scope

# Import necessary Pretix models
from pretix.base.models import Order, Event, Organizer

# Import your Geocode model and the task
from pretix_mapplugin.models import OrderGeocodeData
from pretix_mapplugin.tasks import geocode_order_task

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Scans paid orders and queues geocoding tasks for those missing geocode data.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--organizer',
            type=str,
            help='Slug of a specific organizer to process orders for.',
        )
        parser.add_argument(
            '--event',
            type=str,
            help='Slug of a specific event to process orders for. Requires --organizer.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate the process without actually queuing tasks.',
        )
        parser.add_argument(
            '--force-recode',
            action='store_true',
            help='Queue geocoding even for orders that already have geocode data.',
        )

    def handle(self, *args, **options):
        organizer_slug = options['organizer']
        event_slug = options['event']
        dry_run = options['dry_run']
        force_recode = options['force_recode']

        if event_slug and not organizer_slug:
            raise CommandError("You must specify --organizer when using --event.")

        # --- Determine which organizers to process ---
        organizers_to_process = []
        if organizer_slug:
            try:
                # Fetch specific organizer (outside scope)
                organizer = Organizer.objects.get(slug=organizer_slug)
                organizers_to_process.append(organizer)
                self.stdout.write(f"Processing specified organizer: {organizer.name} ({organizer_slug})")
            except Organizer.DoesNotExist:
                raise CommandError(f"Organizer with slug '{organizer_slug}' not found.")
        else:
            # Fetch all organizers (outside scope)
            organizers_to_process = list(Organizer.objects.all())
            self.stdout.write(f"Processing all {len(organizers_to_process)} organizers...")

        # --- Initialize counters ---
        total_queued = 0
        total_skipped = 0
        total_processed_orders = 0  # Track how many orders were checked

        # --- Iterate through organizers and activate scope ---
        for organizer in organizers_to_process:
            self.stdout.write(f"\n--- Processing Organizer: {organizer.name} ({organizer.slug}) ---")

            # --- Activate scope for this organizer ---
            with scope(organizer=organizer):
                # --- Now perform queries WITHIN the scope ---

                # Start with paid orders FOR THIS ORGANIZER
                orders_qs = Order.objects.filter(status=Order.STATUS_PAID)

                # Filter by specific Event if requested
                if event_slug and organizer.slug == organizer_slug:  # Ensure we only filter for the specified org
                    try:
                        # Event query is now safe within organizer scope
                        event = Event.objects.get(slug=event_slug)  # No need for organizer filter here
                        orders_qs = orders_qs.filter(event=event)
                        self.stdout.write(f"  Filtering orders for event: {event.name} ({event_slug})")
                    except Event.DoesNotExist:
                        # Don't raise CommandError, just report and skip event for this organizer
                        self.stderr.write(self.style.WARNING(
                            f"  Event '{event_slug}' not found for this organizer. Skipping event filter."))
                        # If only this event was requested for this organizer, skip to next organizer
                        if organizer_slug and event_slug:
                            continue

                # Filter orders needing geocoding (within scope)
                if not force_recode:
                    try:
                        # Check relation name - REPLACE 'geocode_data' if yours is different
                        relation_name = 'geocode_data'  # Change if necessary
                        Order._meta.get_field(relation_name)
                        orders_to_process_qs = orders_qs.filter(**{f'{relation_name}__isnull': True})
                        self.stdout.write("  Selecting paid orders missing geocode data...")
                    except FieldDoesNotExist:
                        self.stderr.write(self.style.ERROR(
                            f"  Could not find reverse relation '{relation_name}' on Order model. Check OrderGeocodeData model. Skipping organizer."))
                        continue  # Skip this organizer if relation is wrong
                    except Exception as e:
                        self.stderr.write(
                            self.style.ERROR(f"  Unexpected error checking relation: {e}. Skipping organizer."))
                        continue
                else:
                    orders_to_process_qs = orders_qs
                    self.stdout.write(self.style.WARNING(
                        "  Processing ALL selected paid orders for this organizer (--force-recode)..."))

                # Get count within scope
                current_org_orders_count = orders_to_process_qs.count()
                total_processed_orders += orders_qs.count()  # Count all checked orders for this org

                if current_org_orders_count == 0:
                    self.stdout.write("  No orders need geocoding for this organizer/event.")
                    continue  # Skip to next organizer

                self.stdout.write(f"  Found {current_org_orders_count} order(s) to potentially geocode.")
                org_queued = 0
                org_skipped = 0

                # Iterate and queue (within scope)
                for order in orders_to_process_qs.iterator():
                    if dry_run:
                        self.stdout.write(
                            f"    [DRY RUN] Would queue Order: {order.code} (PK: {order.pk}) Event: {order.event.slug}")
                        org_queued += 1
                    else:
                        try:
                            geocode_order_task.apply_async(args=[order.pk])
                            # Be slightly less verbose inside the loop
                            # self.stdout.write(f"    Queued Order: {order.code} (PK: {order.pk})")
                            org_queued += 1
                        except Exception as e:
                            self.stderr.write(self.style.ERROR(f"    ERROR queuing Order {order.code}: {e}"))
                            logger.exception(f"Failed to queue geocoding task via command for order {order.code}: {e}")
                            org_skipped += 1

                self.stdout.write(f"  Queued: {org_queued}, Skipped: {org_skipped} for this organizer.")
                total_queued += org_queued
                total_skipped += org_skipped

            # Scope for 'organizer' is automatically deactivated here by 'with' statement

        # --- Final Report ---
        self.stdout.write("=" * 40)
        self.stdout.write("Overall Summary:")
        self.stdout.write(f"  Organizers processed: {len(organizers_to_process)}")
        self.stdout.write(f"  Total orders checked (paid): {total_processed_orders}")  # Report total checked
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"[DRY RUN] Complete. Would have queued tasks for {total_queued} order(s)."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Complete. Queued tasks for {total_queued} order(s)."))
            if total_skipped > 0:
                self.stdout.write(
                    self.style.WARNING(f"Skipped {total_skipped} order(s) total due to errors during queueing."))
        self.stdout.write("=" * 40)
