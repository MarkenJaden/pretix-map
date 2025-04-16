from django.db import models
from pretix.base.models import LoggedModel, Order


class OrderGeocodeData(LoggedModel):  # Keep LoggedModel if you want audit logs
    """
    Stores the geocoded coordinates for a Pretix Order's invoice address.
    Allows null coordinates for failed geocoding attempts.
    """
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name='geocode_data',
        primary_key=True  # Keep this if you want order PK as primary key
    )
    latitude = models.FloatField(
        null=True,  # Allow NULL in the database if geocoding fails
        blank=True  # Allow blank in forms/admin (good practice with null=True)
    )
    longitude = models.FloatField(
        null=True,  # Allow NULL in the database if geocoding fails
        blank=True  # Allow blank in forms/admin
    )

    # Change to auto_now to update timestamp on every save (successful or null)
    last_geocoded_at = models.DateTimeField(
        auto_now=True,  # Set/Update timestamp every time the record is saved
        help_text="Timestamp when geocoding was last attempted/updated."
    )

    class Meta:
        verbose_name = "Order Geocode Data"
        verbose_name_plural = "Order Geocode Data"
        # Optional: Indexing coordinates can speed up map data queries if you have many entries
        # indexes = [
        #     models.Index(fields=['latitude', 'longitude']),
        # ]

    def __str__(self):
        # Provide more informative string representation
        if self.latitude is not None and self.longitude is not None:
            return f"Geocode for Order {self.order.code}: ({self.latitude:.4f}, {self.longitude:.4f})"
        else:
            # Indicate if it's pending (never attempted) or failed (null coords stored)
            # This requires knowing if the record exists but has nulls vs doesn't exist yet
            # The current __str__ assumes the record exists if called.
            return f"Geocode data for Order {self.order.code} (Coordinates: None)"
