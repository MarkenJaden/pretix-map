from django.db import models
from pretix.base.models import Order, LoggedModel

class OrderGeocodeData(LoggedModel):
    """
    Stores the geocoded coordinates for a Pretix Order's invoice address.
    """
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE, # Delete geocode data if order is deleted
        related_name='geocode_data', # Allows accessing this from order: order.geocode_data
        primary_key=True # Use the order's PK as this model's PK for efficiency
    )
    latitude = models.FloatField()
    longitude = models.FloatField()
    geocoded_timestamp = models.DateTimeField(
        auto_now_add=True # Automatically set when this record is created
    )

    class Meta:
        # Optional: Define how instances are named in logs/admin
        verbose_name = "Order Geocode Data"
        verbose_name_plural = "Order Geocode Data"

    def __str__(self):
        return f"Geocode data for Order {self.order.code}"