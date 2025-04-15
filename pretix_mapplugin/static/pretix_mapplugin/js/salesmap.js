// Wait for the DOM to be fully loaded before running map code
document.addEventListener('DOMContentLoaded', function () {
    console.log("Sales Map JS Loaded (FINAL TEST - INCLUDING TOGGLE)");

    // --- Configuration ---
    const mapContainerId = 'sales-map-container';
    const statusOverlayId = 'map-status-overlay';
    const toggleButtonId = 'view-toggle-btn';
    const initialZoom = 5;
    const defaultMapView = 'pins'; // Can be 'pins' or 'heatmap'
    const heatmapOptions = {
        radius: 25,
        blur: 15,
        maxZoom: 18,
        // max: 1.0, // Let leaflet-heat calculate max based on data density
        minOpacity: 0.2
    };

    // --- Globals ---
    let map = null; // Leaflet map instance
    let coordinateData = []; // To store fetched [{lat: Y, lon: X, tooltip: Z}, ...] objects
    let pinLayer = null; // Layer for markers/clusters
    let heatmapLayer = null; // Layer for heatmap
    let currentView = defaultMapView; // Track current view state
    let dataUrl = null; // To store the API endpoint URL

    const mapElement = document.getElementById(mapContainerId);
    const statusOverlay = document.getElementById(statusOverlayId);
    const toggleButton = document.getElementById(toggleButtonId);

    // --- Helper to update status overlay ---
    function updateStatus(message, isError = false) {
        if (statusOverlay) {
            const p = statusOverlay.querySelector('p');
            if (p) {
                p.textContent = message;
                p.className = isError ? 'text-danger' : ''; // Apply error class if needed
            }
            statusOverlay.style.display = 'flex'; // Make sure it's visible
        } else {
            console.warn("Status overlay element not found.");
        }
    }

    // --- Helper to hide status overlay ---
    function hideStatus() {
        if (statusOverlay) {
            statusOverlay.style.display = 'none'; // Hide the overlay
        }
    }

    // --- Initialization ---
    function initializeMap() {
        console.log("Initializing Leaflet map...");

        if (!mapElement) {
            console.error(`Map container element #${mapContainerId} not found.`);
            return; // Stop initialization if container is missing
        }
        if (!statusOverlay) {
            console.warn("Status overlay not found");
        }
        if (!toggleButton) {
            // Log a warning but don't necessarily stop if button is missing
            console.warn(`Toggle button #${toggleButtonId} not found.`);
        }

        // --- Get the data URL from the container's data attribute ---
        dataUrl = mapElement.dataset.dataUrl;
        if (!dataUrl) {
            console.error("Data URL not found in container's data-data-url attribute! Cannot fetch data.");
            updateStatus("Configuration Error: Missing data source URL.", true);
            return; // Stop initialization if data URL is missing
        }
        console.log(`Data URL found: ${dataUrl}`);
        // --- End data URL retrieval ---

        // Set Leaflet default image path (if needed, depends on static file setup)
        L.Icon.Default.imagePath = '/static/leaflet/images/'; // Ensure this path is correct
        console.log("Set Leaflet default imagePath to:", L.Icon.Default.imagePath);

        console.log("Initializing Leaflet map...");
        updateStatus("Initializing map...");
        try {
            map = L.map(mapContainerId).setView([48.85, 2.35], initialZoom); // Default center
            console.log("L.map() called successfully.");

            console.log("Adding Tile Layer...");
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            }).addTo(map);
            console.log("Tile layer added successfully.");

            // Setup toggle button listener if it exists
            if (toggleButton) {
                setupToggleButton(); // Call setup function
            } else {
                console.log("Toggle button not found, skipping listener setup.");
            }

            // Fetch data and populate the map layers
            fetchCoordinateData();

        } catch (error) {
            console.error("ERROR during Leaflet initialization:", error);
            updateStatus(`Leaflet Init Failed: ${error.message}`, true);
        }
    }

    // --- Data Fetching ---
    function fetchCoordinateData() {
        // dataUrl should be set during initialization
        if (!dataUrl) {
            console.error("Cannot fetch data: dataUrl is not set.");
            return;
        }

        console.log("Fetching coordinates from:", dataUrl);
        updateStatus("Loading ticket locations..."); // Update status

        fetch(dataUrl)
            .then(response => {
                if (!response.ok) {
                    // Throw an error with status text to be caught below
                    throw new Error(`HTTP error! Status: ${response.status} ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.error) { // Check for application-level errors from the backend
                    throw new Error(`API Error: ${data.error}`);
                }
                // --- Adjust check for the new data structure ---
                if (!data || !data.locations || !Array.isArray(data.locations)) {
                    console.warn("Invalid or empty data format received:", data);
                    updateStatus("No valid geocoded ticket locations found.", false); // Inform user
                    if (toggleButton) toggleButton.disabled = true; // Disable button if no data
                    coordinateData = []; // Ensure it's empty
                    return; // Stop processing if data is missing/invalid
                }
                if (data.locations.length === 0) {
                    console.log("No coordinate data received (empty list).");
                    updateStatus("No geocoded ticket locations found for this event.", false);
                    if (toggleButton) toggleButton.disabled = true;
                    coordinateData = [];
                    return;
                }
                // --- End structure check ---

                coordinateData = data.locations; // Store the [{lat: Y, lon: X, tooltip: Z}, ...] array
                console.log(`Received ${coordinateData.length} coordinates.`);

                // --- Create layers (but don't add to map yet) ---
                createMapLayers();

                // --- Show the default view ---
                showCurrentView();

                // Adjust map bounds to fit markers if coordinates were found
                adjustMapBounds();

                // Enable button if it was disabled and we got data
                if (toggleButton) toggleButton.disabled = false;
                hideStatus();

                // Force redraw just in case (sometimes needed after dynamic content/bounds changes)
                setTimeout(function () {
                    console.log("Forcing map.invalidateSize() after data load...");
                    console.log("Map container element just before invalidateSize:", document.getElementById(mapContainerId)); // Check if it exists here
                    if (map && document.getElementById(mapContainerId)) { // Add check before calling
                        map.invalidateSize();
                    } else {
                        console.warn("Skipping invalidateSize because map or container is missing.");
                    }
                }, 100);

            })
            .catch(error => {
                console.error('Error fetching or processing coordinate data:', error);
                console.log("Map container element during fetch error:", document.getElementById(mapContainerId)); // Check if it exists here
                updateStatus(`Error loading map data: ${error.message}. Please try again later.`, true); // Show error in overlay
                if (toggleButton) toggleButton.disabled = true;
            });
    }

    // --- Layer Creation ---
    function createMapLayers() {
        if (!map || coordinateData.length === 0) {
            console.log("Skipping layer creation (no map or data).");
            return;
        }

        // 1. Create Pin Layer (using MarkerCluster)
        console.log("Creating pin layer instance (marker cluster)...");
        pinLayer = L.markerClusterGroup(); // Initialize cluster group
        coordinateData.forEach((loc, index) => { // loc is now {lat, lon, tooltip, order_url}
            try {
                if (loc.lat == null || loc.lon == null) { /* ... skip invalid ... */
                    return;
                }
                const latLng = L.latLng(loc.lat, loc.lon);
                if (isNaN(latLng.lat) || isNaN(latLng.lng)) { /* ... skip invalid ... */
                    return;
                }

                const marker = L.marker(latLng);

                // --- Use the enhanced tooltip from backend ---
                // Leaflet tooltips handle HTML content by default
                if (loc.tooltip) {
                    marker.bindTooltip(loc.tooltip);
                }
                // --- End Tooltip ---

                // --- Add Click Listener to open order URL ---
                if (loc.order_url) { // Only add listener if URL was successfully generated
                    marker.on('click', function () {
                        console.log(`Marker clicked, opening URL: ${loc.order_url}`);
                        // Open in a new tab, which is usually better for control panel links
                        window.open(loc.order_url, '_blank');
                        // If you prefer opening in the same tab:
                        // window.location.href = loc.order_url;
                    });
                } else {
                    // Log if URL is missing for a marker, maybe backend issue
                    console.warn(`Order URL missing for coordinate index ${index}, click disabled for this marker.`);
                }
                // --- End Click Listener ---

                pinLayer.addLayer(marker); // Add marker to cluster group

            } catch (e) {
                console.error(`Error creating marker for coordinate ${index}:`, loc, e);
            }
        });
        console.log("Pin layer instance created with markers (incl. tooltips and clicks).");


        // 2. Create Heatmap Layer (No changes needed here)
        console.log("Creating heatmap layer instance...");
        try {
            const heatPoints = coordinateData.map(loc => {
                if (loc.lat != null && loc.lon != null && !isNaN(loc.lat) && !isNaN(loc.lon)) {
                    return [loc.lat, loc.lon, 1.0];
                }
                return null;
            }).filter(p => p !== null);

            if (heatPoints.length > 0) {
                heatmapLayer = L.heatLayer(heatPoints, heatmapOptions);
                console.log("Heatmap layer instance created.");
            } else { /* ... handle no valid points ... */
                heatmapLayer = null;
            }
        } catch (e) { /* ... error handling ... */
            heatmapLayer = null;
        }

        console.log("Map layer instances created/updated.");
    }

    // --- Adjust Map Bounds ---
    function adjustMapBounds() {
        if (!map || coordinateData.length === 0) return;

        try {
            let bounds = null;
            // Prefer using marker cluster bounds if available and valid
            if (pinLayer && typeof pinLayer.getBounds === 'function') {
                bounds = pinLayer.getBounds();
                console.log("Attempting to get bounds from pin layer (marker cluster).");
            }

            // If no valid bounds from cluster, or only heatmap exists, calculate from raw data
            if (!bounds || !bounds.isValid()) {
                console.log("Pin layer bounds invalid or unavailable, calculating bounds from raw coordinates.");
                const latLngs = coordinateData
                    .map(loc => {
                        if (loc.lat != null && loc.lon != null && !isNaN(loc.lat) && !isNaN(loc.lon)) {
                            return [loc.lat, loc.lon];
                        }
                        return null;
                    })
                    .filter(p => p !== null);

                if (latLngs.length > 0) {
                    bounds = L.latLngBounds(latLngs);
                }
            }

            // Fit map to bounds if valid bounds were found
            if (bounds && bounds.isValid()) {
                console.log("Fitting map to calculated bounds...");
                map.fitBounds(bounds, {padding: [50, 50]}); // Add padding
                console.log("Bounds fitted.");
            } else if (coordinateData.length === 1) {
                // Special case for a single point
                console.log("Only one valid coordinate, setting view directly.");
                const singleCoord = coordinateData.find(loc => loc.lat != null && loc.lon != null && !isNaN(loc.lat) && !isNaN(loc.lon));
                if (singleCoord) {
                    map.setView([singleCoord.lat, singleCoord.lon], 13); // Zoom level 13 for single point
                } else {
                    console.warn("Could not find the single valid coordinate to set view.");
                }
            } else {
                console.warn("Could not determine valid bounds to fit the map.");
            }
        } catch (e) {
            console.error("Error fitting map bounds:", e);
        }
    }

    // --- View Toggling ---
    function setupToggleButton() {
        updateButtonText(); // Set initial text
        toggleButton.addEventListener('click', () => {
            console.log("Toggle button clicked!");
            currentView = (currentView === 'pins') ? 'heatmap' : 'pins';
            showCurrentView(); // Update the map layers
            updateButtonText(); // Update the button text
        });
        console.log("Toggle button listener setup complete.");
    }

    function showCurrentView() {
        console.log(`Showing view: ${currentView}`);
        if (!map) {
            console.warn("Map not initialized, cannot show view.");
            return;
        }

        // --- Safely remove existing layers ---
        console.log("Removing existing layers (if present)...");
        if (pinLayer && map.hasLayer(pinLayer)) {
            map.removeLayer(pinLayer);
            console.log("Removed pin layer");
        }
        if (heatmapLayer && map.hasLayer(heatmapLayer)) {
            map.removeLayer(heatmapLayer);
            console.log("Removed heatmap layer");
        }
        // --- End removal ---

        // --- Add the selected layer ---
        console.log(`Adding ${currentView} layer...`);
        try {
            if (currentView === 'pins' && pinLayer) {
                map.addLayer(pinLayer);
                console.log("Added pin layer to map.");
            } else if (currentView === 'heatmap' && heatmapLayer) {
                map.addLayer(heatmapLayer);
                console.log("Added heatmap layer to map.");
            } else {
                console.warn(`Cannot add layer for view "${currentView}": Corresponding layer instance is missing or null.`);
                // Maybe display a message if no layers could be shown?
                mapElement.innerHTML += '<p style="position: absolute; top: 10px; left: 50px; background: yellow; padding: 5px; z-index: 1000;">No data to display for this view.</p>';
                setTimeout(() => { // Clear message after a few seconds
                    const msgElement = mapElement.querySelector('p[style*="yellow"]');
                    if (msgElement) msgElement.remove();
                }, 3000);
            }
        } catch (e) {
            console.error(`Error adding ${currentView} layer:`, e);
        }
        // --- End adding ---
    }

    function updateButtonText() {
        if (!toggleButton) return;
        const nextViewText = (currentView === 'pins') ? 'Heatmap' : 'Pin';
        toggleButton.textContent = `Switch to ${nextViewText} View`;
        console.log(`Button text updated to: ${toggleButton.textContent}`);
    }

    // --- Start ---
    initializeMap();

}); // End DOMContentLoaded