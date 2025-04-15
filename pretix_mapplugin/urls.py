from django.urls import re_path

from .views import SalesMapDataView, SalesMapView  # Import your views

# Define the URL patterns for the event settings area
# These URLs will be prefixed with /control/event/<organizer>/<event>/
# based on how Pretix includes plugin URLs.
urlpatterns = [
    # URL for the API endpoint providing coordinate data
    re_path(
        r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/sales-map/data/',
        SalesMapDataView.as_view(),
        name="event.settings.salesmap.data",  # Unique name for URL reversing
    ),
    # URL for the HTML page displaying the map
    re_path(
        r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/sales-map/',
        SalesMapView.as_view(),
        name="event.settings.salesmap.show",  # Unique name for URL reversing
    ),
]
