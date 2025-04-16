document.addEventListener('DOMContentLoaded', function () {
    console.log("Sales Map JS Loaded (Cluster Toggle & Heatmap Opts)");

    // --- L.Icon.Default setup ---
    // Explicitly set the path to Leaflet's default icon images
    try {
        delete L.Icon.Default.prototype._getIconUrl;
        L.Icon.Default.mergeOptions({
            iconRetinaUrl: '/static/leaflet/images/marker-icon-2x.png', // Path within your collected static files
            iconUrl: '/static/leaflet/images/marker-icon.png',         // Path within your collected static files
            shadowUrl: '/static/leaflet/images/marker-shadow.png',     // Path within your collected static files
            iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34],
            tooltipAnchor: [16, -28], shadowSize: [41, 41]
        });
        console.log("Set Leaflet default icon image paths explicitly.");
    } catch (e) {
        console.error("Error setting Leaflet default icon path:", e);
        // Fallback might be needed for very old Leaflet versions
        // L.Icon.Default.imagePath = '/static/leaflet/images/';
    }
    // --- End L.Icon.Default setup ---


    // --- Configuration ---
    const mapContainerId = 'sales-map-container';
    const statusOverlayId = 'map-status-overlay';
    const viewToggleButtonId = 'view-toggle-btn'; // Changed from toggleButtonId for clarity
    const clusterToggleButtonId = 'cluster-toggle-btn';
    const heatmapOptionsPanelId = 'heatmap-options-panel';
    const initialZoom = 5; // Start more zoomed out
    const defaultMapView = 'pins'; // Start with pins

    // --- Globals & State ---
    let map = null;
    let coordinateData = []; // Stores {lat, lon, tooltip, order_url}
    let pinLayer = null; // Holds L.markerClusterGroup OR L.layerGroup
    let heatmapLayer = null;
    let currentView = defaultMapView;
    let dataUrl = null;
    let isClusteringEnabled = true; // Default Cluster State: ON
    let heatmapOptions = { // Default Heatmap Options (state variable)
        radius: 25,
        blur: 15,
        maxZoom: 18,
        minOpacity: 0.2 // Example optional parameter
    };

    // --- DOM Elements ---
    const mapElement = document.getElementById(mapContainerId);
    const statusOverlay = document.getElementById(statusOverlayId);
    const viewToggleButton = document.getElementById(viewToggleButtonId);
    const clusterToggleButton = document.getElementById(clusterToggleButtonId);
    const heatmapOptionsPanel = document.getElementById(heatmapOptionsPanelId);
    // Heatmap control elements
    const heatmapRadiusInput = document.getElementById('heatmap-radius');
    const heatmapBlurInput = document.getElementById('heatmap-blur');
    const heatmapMaxZoomInput = document.getElementById('heatmap-maxZoom');
    const radiusValueSpan = document.getElementById('radius-value');
    const blurValueSpan = document.getElementById('blur-value');
    const maxZoomValueSpan = document.getElementById('maxzoom-value');

    // --- Status Update Helpers ---
    function updateStatus(message, isError = false) {
        if (statusOverlay) {
            const p = statusOverlay.querySelector('p');
            if (p) { p.textContent = message; p.className = isError ? 'text-danger' : ''; }
            statusOverlay.style.display = 'flex'; // Show overlay when status updates
        } else { console.warn("Status overlay element not found."); }
    }
    function hideStatus() {
        if (statusOverlay) { statusOverlay.style.display = 'none'; } // Hide overlay
    }
    // --- End Status Helpers ---


    // --- Initialization ---
    function initializeMap() {
        // Check required elements
        if (!mapElement) { console.error(`Map container #${mapContainerId} not found.`); return; }
        if (!statusOverlay) { console.warn("Status overlay element not found."); }
        // Check control elements (warn but continue if missing)
        if (!viewToggleButton) console.warn("View toggle button not found.");
        if (!clusterToggleButton) console.warn("Cluster toggle button not found.");
        if (!heatmapOptionsPanel) console.warn("Heatmap options panel not found.");
        if (!heatmapRadiusInput || !heatmapBlurInput || !heatmapMaxZoomInput) console.warn("Heatmap input elements missing.");

        // Get Data URL
        dataUrl = mapElement.dataset.dataUrl;
        if (!dataUrl) {
            updateStatus("Configuration Error: Missing data source URL.", true);
            return;
        }
        console.log(`Data URL found: ${dataUrl}`);
        updateStatus("Initializing map...");

        // Create Leaflet Map
        try {
            map = L.map(mapContainerId).setView([48.85, 2.35], initialZoom); // Centered somewhat on Europe
            console.log("L.map() called successfully.");

            // Add Base Tile Layer
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                 attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                 maxZoom: 18, // Standard max zoom
            }).on('load', function() { console.log('Base tiles loaded.'); }).addTo(map);
            console.log("Tile layer added successfully.");

            // Setup Controls (Event Listeners)
            if (viewToggleButton) setupViewToggleButton();
            if (clusterToggleButton) setupClusterToggleButton();
            setupHeatmapControls(); // Setup listeners even if panel hidden

            // Fetch data to populate layers
            fetchDataAndDraw();

        } catch (error) {
            console.error("ERROR during Leaflet initialization:", error);
            updateStatus(`Leaflet Init Failed: ${error.message}`, true);
        }
    }


    // --- Data Fetching & Initial Drawing ---
    function fetchDataAndDraw() {
        if (!dataUrl) return;
        console.log("Fetching coordinates from:", dataUrl);
        updateStatus("Loading ticket locations...");
        // Disable controls while loading
        if(viewToggleButton) viewToggleButton.disabled = true;
        if(clusterToggleButton) clusterToggleButton.disabled = true;
        disableHeatmapControls(true);

        fetch(dataUrl)
            .then(response => {
                 if (!response.ok) throw new Error(`HTTP error! Status: ${response.status} ${response.statusText}`);
                 return response.json();
             })
            .then(data => {
                if (data.error) throw new Error(`API Error: ${data.error}`);
                if (!data || !data.locations || !Array.isArray(data.locations)) {
                     console.warn("Invalid or empty data format received:", data);
                     updateStatus("No valid geocoded ticket locations found.", false);
                     coordinateData = []; hideStatus(); return;
                }
                if (data.locations.length === 0) {
                    console.log("No coordinate data received (empty list).");
                    updateStatus("No geocoded ticket locations found for this event.", false);
                    coordinateData = []; hideStatus(); return;
                }

                coordinateData = data.locations;
                console.log(`Received ${coordinateData.length} coordinates.`);

                // Enable controls now that we have data
                if(viewToggleButton) viewToggleButton.disabled = false;
                // Only enable cluster button if in pins view initially and data exists
                if(clusterToggleButton) clusterToggleButton.disabled = (currentView !== 'pins');
                // Only enable heatmap controls if data exists
                disableHeatmapControls(false);

                // Create both layers based on fetched data
                createAllLayers();
                // Display the default layer
                showCurrentView();
                // Adjust bounds to fit the data
                adjustMapBounds();

                hideStatus(); // Hide loading overlay

                // Force redraw after a short delay
                setTimeout(function () {
                    console.log("Forcing map.invalidateSize() after data load...");
                    const container = document.getElementById(mapContainerId);
                    if (map && container && container.offsetWidth > 0) {
                         map.invalidateSize();
                    } else {
                         console.warn(`Skipping invalidateSize. Map: ${!!map}, Container: ${!!container}, OffsetWidth: ${container ? container.offsetWidth : 'N/A'}`);
                    }
                }, 100);
            })
            .catch(error => {
                console.error('Error fetching or processing coordinate data:', error);
                updateStatus(`Error loading map data: ${error.message}. Please try again later.`, true);
                // Keep controls disabled on error
            });
    }


    // --- Layer Creation Functions ---
    function createAllLayers() {
        // Orchestrates creation of both layer types
        createPinLayer();
        createHeatmapLayer();
        console.log("Map layer instances created/updated.");
    }

    function createPinLayer() {
        // Creates/recreates the pin layer based on isClusteringEnabled state
        console.log(`Creating pin layer instance (Clustering: ${isClusteringEnabled})...`);
        pinLayer = null; // Clear previous instance
        if (coordinateData.length === 0) { console.warn("No coordinate data for pin layer."); return; }

        const markers = [];
        coordinateData.forEach((loc, index) => {
            try {
                if (loc.lat == null || loc.lon == null || isNaN(loc.lat) || isNaN(loc.lon)) return;
                const latLng = L.latLng(loc.lat, loc.lon);
                const marker = L.marker(latLng);
                if (loc.tooltip) marker.bindTooltip(loc.tooltip);
                if (loc.order_url) { marker.on('click', () => window.open(loc.order_url, '_blank')); }
                markers.push(marker);
            } catch (e) { console.error(`Error creating marker ${index}:`, e); }
        });

        if (markers.length === 0) { console.warn("No valid markers created for pin layer."); return; }

        if (isClusteringEnabled) {
            pinLayer = L.markerClusterGroup(); // Use clustering
            pinLayer.addLayers(markers);
            console.log("Marker cluster group created and populated.");
        } else {
            pinLayer = L.layerGroup(markers); // Use simple layer group
            console.log("Simple layer group created and populated.");
        }
    }

    function createHeatmapLayer() {
        // Creates/recreates the heatmap layer using current heatmapOptions
        console.log("Creating heatmap layer instance...");
        heatmapLayer = null; // Clear previous instance
        if (coordinateData.length === 0) { console.warn("No coordinate data for heatmap layer."); return; }

        try {
            const heatPoints = coordinateData.map(loc => {
                if (loc.lat != null && loc.lon != null && !isNaN(loc.lat) && !isNaN(loc.lon)) {
                    return [loc.lat, loc.lon, 1.0]; // Intensity 1.0
                } return null;
            }).filter(p => p !== null);

            if (heatPoints.length > 0) {
                heatmapLayer = L.heatLayer(heatPoints, heatmapOptions); // Use state variable
                console.log("Heatmap layer instance created with options:", heatmapOptions);
            } else { console.warn("No valid points for heatmap layer."); }
        } catch (e) { console.error("Error creating heatmap layer instance:", e); }
    }


    // --- Layer Update Functions ---
    function redrawPinLayer() {
        // Removes existing pin layer, calls createPinLayer, adds new one if current view is 'pins'
        if (!map) return;
        console.log("Redrawing pin layer...");
        if (pinLayer && map.hasLayer(pinLayer)) {
            map.removeLayer(pinLayer);
            console.log("Removed existing pin layer before redraw.");
        }
        pinLayer = null; // Ensure it's cleared
        createPinLayer(); // Recreate based on current clustering state
        if (currentView === 'pins' && pinLayer) {
             console.log("Adding newly created pin layer to map.");
             map.addLayer(pinLayer);
        }
    }

    function updateHeatmap() {
        // Updates options on the existing heatmap layer if it's present
        if (!map || !heatmapLayer) {
            console.warn("Cannot update heatmap: map or heatmap layer missing.");
            return;
        }
        console.log("Updating heatmap options:", heatmapOptions);
        try {
             // Use Leaflet.heat's setOptions method
             heatmapLayer.setOptions(heatmapOptions);
             console.log("Heatmap options updated.");
        } catch(e) {
             console.error("Error setting heatmap options:", e);
        }
    }


     // --- Adjust Map Bounds ---
    function adjustMapBounds() {
        // (Keep the working version from previous steps)
        if (!map || coordinateData.length === 0) return;
        try {
            let bounds = null;
            if (currentView === 'pins' && pinLayer && typeof pinLayer.getBounds === 'function') {
                 bounds = pinLayer.getBounds();
                 console.log("Attempting bounds from pin layer.");
            }
            if (!bounds || !bounds.isValid()) {
                console.log("Calculating bounds from raw coordinates.");
                const latLngs = coordinateData.map(loc => { /* ... filter valid ... */ return [loc.lat, loc.lon]; }).filter(p => p !== null);
                if (latLngs.length > 0) bounds = L.latLngBounds(latLngs);
            }
            if (bounds && bounds.isValid()) {
                console.log("Fitting map to bounds..."); map.fitBounds(bounds, { padding: [50, 50] }); console.log("Bounds fitted.");
            } else if (coordinateData.length === 1) {
                 console.log("Setting view for single coordinate.");
                 const singleCoord = coordinateData.find(loc => /* ... valid ... */);
                 if (singleCoord) map.setView([singleCoord.lat, singleCoord.lon], 13);
                 else console.warn("Could not find single valid coordinate.");
            } else { console.warn("Could not determine valid bounds."); }
        } catch (e) { console.error("Error fitting map bounds:", e); }
    }


    // --- Control Setup Functions ---
    function setupViewToggleButton() {
        updateViewToggleButtonText(); // Initial text
        viewToggleButton.addEventListener('click', () => {
            console.log("View toggle button clicked!");
            currentView = (currentView === 'pins') ? 'heatmap' : 'pins';
            showCurrentView(); // Update map display
            updateViewToggleButtonText(); // Update button text
            // Enable/disable cluster button based on view
            if (clusterToggleButton) clusterToggleButton.disabled = (currentView !== 'pins');
        });
        console.log("View toggle button listener setup complete.");
    }

    function setupClusterToggleButton() {
        updateClusterToggleButtonText(); // Initial text
        // Start disabled if not in pins view
        clusterToggleButton.disabled = (currentView !== 'pins');
        clusterToggleButton.addEventListener('click', () => {
            if (currentView !== 'pins') return; // Safety check
            console.log("Cluster toggle button clicked!");
            isClusteringEnabled = !isClusteringEnabled; // Toggle state
            redrawPinLayer(); // Recreate and potentially re-add the pin layer
            updateClusterToggleButtonText(); // Update button text
        });
        console.log("Cluster toggle button listener setup complete.");
    }

    function setupHeatmapControls() {
        // Check if all elements exist before adding listeners
        if (!heatmapRadiusInput || !heatmapBlurInput || !heatmapMaxZoomInput || !radiusValueSpan || !blurValueSpan || !maxZoomValueSpan) {
            console.error("One or more heatmap control elements not found. Cannot setup listeners.");
            return;
        }

        // Set initial display values from defaults
        radiusValueSpan.textContent = heatmapOptions.radius;
        heatmapRadiusInput.value = heatmapOptions.radius;
        blurValueSpan.textContent = heatmapOptions.blur;
        heatmapBlurInput.value = heatmapOptions.blur;
        maxZoomValueSpan.textContent = heatmapOptions.maxZoom;
        heatmapMaxZoomInput.value = heatmapOptions.maxZoom;

        // Add 'input' listeners for real-time updates
        heatmapRadiusInput.addEventListener('input', (e) => {
            const value = parseFloat(e.target.value);
            heatmapOptions.radius = value; // Update state
            radiusValueSpan.textContent = value; // Update display
            updateHeatmap(); // Apply change to map
        });
        heatmapBlurInput.addEventListener('input', (e) => {
             const value = parseFloat(e.target.value);
            heatmapOptions.blur = value; // Update state
            blurValueSpan.textContent = value; // Update display
            updateHeatmap(); // Apply change to map
        });
        heatmapMaxZoomInput.addEventListener('input', (e) => {
             const value = parseInt(e.target.value, 10);
            heatmapOptions.maxZoom = value; // Update state
            maxZoomValueSpan.textContent = value; // Update display
            updateHeatmap(); // Apply change to map
        });
        console.log("Heatmap control listeners setup complete.");
    }

     function disableHeatmapControls(disabled) {
         // Helper to enable/disable all heatmap inputs
         if (heatmapRadiusInput) heatmapRadiusInput.disabled = disabled;
         if (heatmapBlurInput) heatmapBlurInput.disabled = disabled;
         if (heatmapMaxZoomInput) heatmapMaxZoomInput.disabled = disabled;
     }


    // --- View Switching Logic ---
    function showCurrentView() {
        console.log(`Showing view: ${currentView}`);
        if (!map) { console.warn("Map not initialized."); return; }

        // Remove existing layers from map
        console.log("Removing existing layers (if present)...");
        if (pinLayer && map.hasLayer(pinLayer)) map.removeLayer(pinLayer);
        if (heatmapLayer && map.hasLayer(heatmapLayer)) map.removeLayer(heatmapLayer);

        // Add the selected layer and show/hide controls
        console.log(`Adding ${currentView} layer...`);
        let layerToAdd = null;
        if (currentView === 'pins') {
            layerToAdd = pinLayer;
            if(heatmapOptionsPanel) heatmapOptionsPanel.style.display = 'none';
            if(clusterToggleButton) clusterToggleButton.style.display = 'inline-block'; // Show cluster btn
            if(clusterToggleButton) clusterToggleButton.disabled = false; // Ensure enabled
        } else { // Heatmap view
            layerToAdd = heatmapLayer;
            if(heatmapOptionsPanel) heatmapOptionsPanel.style.display = 'block';
            if(clusterToggleButton) clusterToggleButton.style.display = 'none'; // Hide cluster btn
            if(clusterToggleButton) clusterToggleButton.disabled = true; // Ensure disabled
        }

        // Add the layer to the map if it exists
        if (layerToAdd) {
            try {
                 map.addLayer(layerToAdd);
                 console.log(`Added ${currentView} layer to map.`);
            } catch (e) {
                 console.error(`Error adding ${currentView} layer:`, e);
                 updateStatus(`Error displaying ${currentView} layer.`, true);
            }
        } else {
            // This happens if createLayer failed (e.g., no valid data)
            console.warn(`Cannot add layer for view "${currentView}": Layer instance missing.`);
            updateStatus(`No data available for ${currentView} view.`, false);
        }
    }


    // --- Button Text Update Functions ---
    function updateViewToggleButtonText() {
        if (!viewToggleButton) return;
        const nextViewText = (currentView === 'pins') ? 'Heatmap' : 'Pin';
        viewToggleButton.textContent = `Switch to ${nextViewText} View`;
        console.log(`View Toggle Button text updated to: ${viewToggleButton.textContent}`);
    }

    function updateClusterToggleButtonText() {
         if (!clusterToggleButton) return;
        clusterToggleButton.textContent = isClusteringEnabled ? 'Disable Clustering' : 'Enable Clustering';
        console.log(`Cluster Toggle Button text updated to: ${clusterToggleButton.textContent}`);
    }


    // --- Start Initialization ---
    initializeMap();

}); // End DOMContentLoaded