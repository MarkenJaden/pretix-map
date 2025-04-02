// Wait for the DOM to be fully loaded before running map code
document.addEventListener('DOMContentLoaded', function () {
    console.log("Sales Map JS Loaded (FINAL TEST - INCLUDING TOGGLE)");

    L.Icon.Default.imagePath = '/static/leaflet/images/';
    console.log("Set Leaflet default imagePath to:", L.Icon.Default.imagePath);

    // --- Configuration ---
    const mapContainerId = 'sales-map-container';
    const toggleButtonId = 'view-toggle-btn'; // Re-enable button ID
    const initialZoom = 5;
    const defaultMapView = 'pins'; // Can be 'pins' or 'heatmap'
    const heatmapOptions = {
        radius: 25,
        blur: 15,
        maxZoom: 18,
        max: 1.0,
        minOpacity: 0.2
    };

    // --- Globals ---
    let map = null; // Leaflet map instance
    let allCoordinates = []; // To store fetched [lat, lon] pairs
    let pinLayer = null; // Layer for markers/clusters
    let heatmapLayer = null; // Layer for heatmap
    let currentView = defaultMapView; // Track current view state

    const mapElement = document.getElementById(mapContainerId);
    const toggleButton = document.getElementById(toggleButtonId); // Get the button element

    // --- Initialization ---
    function initializeMap() {
        if (!mapElement) {
            console.error(`Map container element #${mapContainerId} not found.`);
            return;
        }
        if (!toggleButton) {
            // Log a warning but don't necessarily stop if button is missing
            console.warn(`Toggle button #${toggleButtonId} not found.`);
        }

        console.log("Initializing Leaflet map...");
        try {
            map = L.map(mapContainerId).setView([48.85, 2.35], initialZoom);
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

            // Fetch data and populate the map layers (but don't add to map yet)
            fetchCoordinateData();

        } catch (error) {
            console.error("ERROR during Leaflet initialization:", error);
            mapElement.innerHTML = `<p class="text-danger">Leaflet Init Failed: ${error.message}</p>`;
        }
    }

    // --- Data Fetching ---
    function fetchCoordinateData() {
        if (typeof salesMapDataUrl === 'undefined' || !salesMapDataUrl) { /* ... error handling ... */
            return;
        }

        console.log("Fetching coordinates from:", salesMapDataUrl);
        // mapElement.innerHTML = '<p>Loading ticket locations...</p>'; // Optional loading message

        fetch(salesMapDataUrl)
            .then(response => { /* ... check response ... */
                return response.json();
            })
            .then(data => {
                if (data.error) { /* ... handle API error ... */
                    throw new Error(`API Error: ${data.error}`);
                }
                if (!data.coordinates || data.coordinates.length === 0) {
                    console.log("No coordinate data received.");
                    // mapElement.innerHTML = '<p>No geocoded ticket locations found for this event.</p>';
                    if (toggleButton) toggleButton.disabled = true; // Disable button if no data
                    return;
                }

                allCoordinates = data.coordinates;
                console.log(`Received ${allCoordinates.length} coordinates.`);
                console.log("Coordinate data:", JSON.stringify(allCoordinates));
                // mapElement.innerHTML = ''; // Clear loading message

                // --- Create layers (but don't add to map yet) ---
                createMapLayers(); // Call the layer creation function

                // --- Show the default view ---
                showCurrentView(); // Call function to add the correct layer initially

                // Adjust map bounds to fit markers if coordinates were found
                // Use pinLayer for bounds calculation if available
                if (allCoordinates.length > 0 && pinLayer) {
                    try {
                        console.log("Fitting bounds based on pin layer...");
                        const bounds = pinLayer.getBounds ? pinLayer.getBounds() : L.latLngBounds(allCoordinates); // Handle direct marker case if needed, prefer getBounds for cluster
                        if (bounds && bounds.isValid()) {
                            map.fitBounds(bounds, {padding: [50, 50]});
                            console.log("Bounds fitted.");
                        } else {
                            console.warn("Could not get valid bounds, falling back to setView.");
                            if (allCoordinates.length === 1) {
                                map.setView(allCoordinates[0], 13);
                            }
                        }
                    } catch (e) {
                        console.error("Error fitting bounds:", e);
                        if (allCoordinates.length === 1) {
                            map.setView(allCoordinates[0], 13);
                        }
                    }
                } else if (allCoordinates.length > 0) {
                    // Fallback if only heatmap exists or pinLayer has no getBounds
                    console.log("Fitting bounds based on raw coordinates...");
                    map.fitBounds(L.latLngBounds(allCoordinates), {padding: [50, 50]});
                }


                // Force redraw just in case
                setTimeout(function () {
                    console.log("Forcing map.invalidateSize() after data load...");
                    if (map) map.invalidateSize();
                }, 100);

            })
            .catch(error => {
                console.error('Error fetching or processing coordinate data:', error);
                mapElement.innerHTML = `<p class="text-danger">Error loading map data: ${error.message}. Please check logs or try again later.</p>`;
            });
    }

    // --- Layer Creation (Restored original structure) ---
    function createMapLayers() {
        if (!map || allCoordinates.length === 0) {
            console.log("Skipping layer creation (no map or data).");
            return;
        }

        // 1. Create Pin Layer (using MarkerCluster)
        console.log("Creating pin layer instance (marker cluster)...");
        pinLayer = L.markerClusterGroup(); // Initialize cluster group
        allCoordinates.forEach((coord, index) => {
            try {
                const latLng = new L.LatLng(coord[0], coord[1]);
                if (isNaN(latLng.lat) || isNaN(latLng.lng)) { /* ... skip invalid ... */
                    return;
                }
                const marker = L.marker(latLng);
                pinLayer.addLayer(marker);
            } catch (e) { /* ... error handling ... */
            }
        });
        console.log("Pin layer instance created.");


        // 2. Create Heatmap Layer
        console.log("Creating heatmap layer instance...");
        try {
            heatmapLayer = L.heatLayer(allCoordinates, heatmapOptions);
            console.log("Heatmap layer instance created.");
        } catch (e) {
            console.error("Error creating heatmap layer instance:", e);
            heatmapLayer = null; // Ensure it's null if creation failed
        }

        console.log("Map layer instances created.");
    }

    // --- View Toggling (Restored) ---
    function setupToggleButton() {
        updateButtonText(); // Set initial text
        toggleButton.addEventListener('click', () => {
            console.log("Toggle button clicked!");
            if (currentView === 'pins') {
                currentView = 'heatmap';
            } else {
                currentView = 'pins';
            }
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

        // --- IMPORTANT: Safely remove existing layers ---
        console.log("Removing existing layers (if present)...");
        if (pinLayer && map.hasLayer(pinLayer)) {
            map.removeLayer(pinLayer);
            console.log("Removed pin layer");
        } else {
            // console.log("Pin layer was not on map."); // Optional debug log
        }
        if (heatmapLayer && map.hasLayer(heatmapLayer)) {
            map.removeLayer(heatmapLayer);
            console.log("Removed heatmap layer");
        } else {
            // console.log("Heatmap layer was not on map."); // Optional debug log
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
                console.warn(`Cannot add layer for view "${currentView}": Layer instance might be missing or null.`);
            }
        } catch (e) {
            console.error(`Error adding ${currentView} layer:`, e);
        }
        // --- End adding ---
    }

    function updateButtonText() {
        if (!toggleButton) return;
        if (currentView === 'pins') {
            toggleButton.textContent = 'Switch to Heatmap View';
        } else {
            toggleButton.textContent = 'Switch to Pin View';
        }
        console.log(`Button text updated to: ${toggleButton.textContent}`);
    }


    // --- Start ---
    initializeMap();

}); // End DOMContentLoaded