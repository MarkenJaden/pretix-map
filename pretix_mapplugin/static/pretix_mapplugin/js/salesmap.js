document.addEventListener('DOMContentLoaded', function () {
    console.log("Sales Map JS Loaded (Cluster Toggle & Heatmap Opts)");

    // --- L.Icon.Default setup ---
    try {
        delete L.Icon.Default.prototype._getIconUrl;
        L.Icon.Default.mergeOptions({
            iconRetinaUrl: '/static/leaflet/images/marker-icon-2x.png',
            iconUrl: '/static/leaflet/images/marker-icon.png',
            shadowUrl: '/static/leaflet/images/marker-shadow.png',
            iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34],
            tooltipAnchor: [16, -28], shadowSize: [41, 41]
        });
        console.log("Set Leaflet default icon image paths explicitly.");
    } catch (e) {
        console.error("Error setting icon path:", e);
    }
    // --- End L.Icon.Default setup ---


    // --- Configuration ---
    const mapContainerId = 'sales-map-container';
    const statusOverlayId = 'map-status-overlay';
    const viewToggleButtonId = 'view-toggle-btn';
    const clusterToggleButtonId = 'cluster-toggle-btn';
    const heatmapOptionsPanelId = 'heatmap-options-panel';
    const initialZoom = 5;
    const defaultMapView = 'pins';

    // --- Globals & State ---
    let map = null;
    let coordinateData = [];
    let pinLayer = null;
    let heatmapLayer = null;
    let currentView = defaultMapView;
    let dataUrl = null;
    let isClusteringEnabled = true;
    let heatmapOptions = {
        radius: 25, blur: 15, maxZoom: 18, minOpacity: 0.2
    };

    // --- DOM Elements ---
    const mapElement = document.getElementById(mapContainerId);
    const statusOverlay = document.getElementById(statusOverlayId);
    const viewToggleButton = document.getElementById(viewToggleButtonId);
    const clusterToggleButton = document.getElementById(clusterToggleButtonId);
    const heatmapOptionsPanel = document.getElementById(heatmapOptionsPanelId);
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
            if (p) {
                p.textContent = message;
                p.className = isError ? 'text-danger' : '';
            }
            statusOverlay.style.display = 'flex';
        } else {
            console.warn("Status overlay element not found.");
        }
    }

    function hideStatus() {
        if (statusOverlay) {
            statusOverlay.style.display = 'none';
        }
    }

    // --- End Status Helpers ---


    // --- Initialization ---
    function initializeMap() {
        if (!mapElement) {
            console.error(`Map container #${mapContainerId} not found.`);
            return;
        }
        if (!statusOverlay) {
            console.warn("Status overlay element not found.");
        }
        if (!viewToggleButton) console.warn("View toggle button not found.");
        if (!clusterToggleButton) console.warn("Cluster toggle button not found.");
        if (!heatmapOptionsPanel) console.warn("Heatmap options panel not found.");
        if (!heatmapRadiusInput || !heatmapBlurInput || !heatmapMaxZoomInput) console.warn("Heatmap input elements missing.");

        dataUrl = mapElement.dataset.dataUrl;
        if (!dataUrl) {
            updateStatus("Configuration Error: Missing data source URL.", true);
            return;
        }
        console.log(`Data URL found: ${dataUrl}`);
        updateStatus("Initializing map...");

        try {
            map = L.map(mapContainerId).setView([48.85, 2.35], initialZoom);
            console.log("L.map() called successfully.");

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                maxZoom: 18,
            }).on('load', function () {
                console.log('Base tiles loaded.');
            }).addTo(map);
            console.log("Tile layer added successfully.");

            if (viewToggleButton) setupViewToggleButton();
            if (clusterToggleButton) setupClusterToggleButton();
            setupHeatmapControls();
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
        if (viewToggleButton) viewToggleButton.disabled = true;
        if (clusterToggleButton) clusterToggleButton.disabled = true;
        disableHeatmapControls(true);

        fetch(dataUrl)
            .then(response => {
                if (!response.ok) throw new Error(`HTTP error! Status: ${response.status} ${response.statusText}`);
                return response.json();
            })
            .then(data => {
                if (data.error) throw new Error(`API Error: ${data.error}`);
                if (!data || !data.locations || !Array.isArray(data.locations)) {
                    console.warn("Invalid data format:", data);
                    updateStatus("No valid locations found.", false);
                    coordinateData = [];
                    hideStatus();
                    return;
                }
                if (data.locations.length === 0) {
                    console.log("No locations received.");
                    updateStatus("No locations found for event.", false);
                    coordinateData = [];
                    hideStatus();
                    return;
                }

                coordinateData = data.locations;
                console.log(`Received ${coordinateData.length} coordinates.`);

                if (viewToggleButton) viewToggleButton.disabled = false;
                if (clusterToggleButton) clusterToggleButton.disabled = (currentView !== 'pins');
                disableHeatmapControls(false);

                createAllLayers();
                showCurrentView();
                adjustMapBounds();
                hideStatus();

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
                console.error('Error fetching/processing data:', error);
                updateStatus(`Error loading map data: ${error.message}.`, true);
            });
    }


    // --- Layer Creation Functions ---
    function createAllLayers() {
        createPinLayer();
        createHeatmapLayer();
        console.log("Layers created/updated.");
    }

    function createPinLayer() {
        console.log(`Creating pin layer (Clustering: ${isClusteringEnabled})...`);
        pinLayer = null;
        if (coordinateData.length === 0) {
            console.warn("No data for pin layer.");
            return;
        }
        const markers = [];
        coordinateData.forEach((loc, index) => {
            try {
                if (loc.lat == null || loc.lon == null || isNaN(loc.lat) || isNaN(loc.lon)) return;
                const marker = L.marker(L.latLng(loc.lat, loc.lon));
                if (loc.tooltip) marker.bindTooltip(loc.tooltip);
                if (loc.order_url) {
                    marker.on('click', () => window.open(loc.order_url, '_blank'));
                }
                markers.push(marker);
            } catch (e) {
                console.error(`Error creating marker ${index}:`, e);
            }
        });
        if (markers.length === 0) {
            console.warn("No valid markers created.");
            return;
        }
        if (isClusteringEnabled) {
            pinLayer = L.markerClusterGroup();
            pinLayer.addLayers(markers);
            console.log("Marker cluster populated.");
        } else {
            pinLayer = L.layerGroup(markers);
            console.log("Simple layer group populated.");
        }
    }

    function createHeatmapLayer() {
        console.log("Creating heatmap layer...");
        heatmapLayer = null;
        if (coordinateData.length === 0) {
            console.warn("No data for heatmap.");
            return;
        }
        try {
            const heatPoints = coordinateData.map(loc => {
                if (loc.lat != null && loc.lon != null && !isNaN(loc.lat) && !isNaN(loc.lon)) {
                    return [loc.lat, loc.lon, 1.0];
                }
                return null;
            }).filter(p => p !== null);
            if (heatPoints.length > 0) {
                heatmapLayer = L.heatLayer(heatPoints, heatmapOptions);
                console.log("Heatmap created:", heatmapOptions);
            } else {
                console.warn("No valid points for heatmap.");
            }
        } catch (e) {
            console.error("Error creating heatmap:", e);
        }
    }


    // --- Layer Update Functions ---
    function redrawPinLayer() {
        if (!map) return;
        console.log("Redrawing pin layer...");
        if (pinLayer && map.hasLayer(pinLayer)) map.removeLayer(pinLayer);
        pinLayer = null;
        createPinLayer();
        if (currentView === 'pins' && pinLayer) {
            console.log("Adding new pin layer.");
            map.addLayer(pinLayer);
        }
    }

    function updateHeatmap() {
        if (!map || !heatmapLayer) {
            console.warn("Cannot update heatmap.");
            return;
        }
        console.log("Updating heatmap opts:", heatmapOptions);
        try {
            heatmapLayer.setOptions(heatmapOptions);
            console.log("Heatmap opts updated.");
        } catch (e) {
            console.error("Error setting heatmap opts:", e);
        }
    }


    // --- Adjust Map Bounds (Corrected) ---
    function adjustMapBounds() {
        if (!map || coordinateData.length === 0) return;
        try {
            let bounds = null;
            if (currentView === 'pins' && pinLayer && typeof pinLayer.getBounds === 'function') {
                bounds = pinLayer.getBounds();
                console.log("Attempting bounds from pin layer.");
            }
            // Calculate from raw if pin layer bounds unavailable/invalid or if in heatmap view
            if (!bounds || !bounds.isValid()) {
                console.log("Calculating bounds from raw coordinates.");
                // Filter valid lat/lon pairs
                const latLngs = coordinateData
                    .map(loc => {
                        if (loc.lat != null && loc.lon != null && !isNaN(loc.lat) && !isNaN(loc.lon)) {
                            return [loc.lat, loc.lon];
                        }
                        return null;
                    })
                    .filter(p => p !== null);
                if (latLngs.length > 0) bounds = L.latLngBounds(latLngs);
            }

            // Apply bounds if valid
            if (bounds && bounds.isValid()) {
                console.log("Fitting map to bounds...");
                map.fitBounds(bounds, {padding: [50, 50]});
                console.log("Bounds fitted.");
                // Handle single point case
            } else if (coordinateData.filter(loc => loc.lat != null && loc.lon != null && !isNaN(loc.lat) && !isNaN(loc.lon)).length === 1) {
                console.log("Setting view for single coordinate.");
                // --- Corrected logic to find the single valid coordinate ---
                const singleCoord = coordinateData.find(loc => loc.lat != null && loc.lon != null && !isNaN(loc.lat) && !isNaN(loc.lon));
                // --- End Correction ---
                if (singleCoord) map.setView([singleCoord.lat, singleCoord.lon], 13);
                else console.warn("Could not find single valid coordinate to set view.");
                // Removed extra ')' here
            } else {
                console.warn("Could not determine valid bounds.");
            }
        } catch (e) {
            console.error("Error fitting map bounds:", e);
        }
    } // End adjustMapBounds function


    // --- Control Setup Functions ---
    function setupViewToggleButton() {
        updateViewToggleButtonText();
        viewToggleButton.addEventListener('click', () => {
            console.log("View toggle clicked!");
            currentView = (currentView === 'pins') ? 'heatmap' : 'pins';
            showCurrentView();
            updateViewToggleButtonText();
            if (clusterToggleButton) clusterToggleButton.disabled = (currentView !== 'pins');
        });
        console.log("View toggle listener setup.");
    }

    function setupClusterToggleButton() {
        updateClusterToggleButtonText();
        clusterToggleButton.disabled = (currentView !== 'pins');
        clusterToggleButton.addEventListener('click', () => {
            if (currentView !== 'pins') return;
            console.log("Cluster toggle clicked!");
            isClusteringEnabled = !isClusteringEnabled;
            redrawPinLayer();
            updateClusterToggleButtonText();
        });
        console.log("Cluster toggle listener setup.");
    }

    function setupHeatmapControls() {
        if (!heatmapRadiusInput || !heatmapBlurInput || !heatmapMaxZoomInput || !radiusValueSpan || !blurValueSpan || !maxZoomValueSpan) {
            console.error("Heatmap controls missing.");
            return;
        }
        radiusValueSpan.textContent = heatmapOptions.radius;
        heatmapRadiusInput.value = heatmapOptions.radius;
        blurValueSpan.textContent = heatmapOptions.blur;
        heatmapBlurInput.value = heatmapOptions.blur;
        maxZoomValueSpan.textContent = heatmapOptions.maxZoom;
        heatmapMaxZoomInput.value = heatmapOptions.maxZoom;
        heatmapRadiusInput.addEventListener('input', (e) => {
            const v = parseFloat(e.target.value);
            heatmapOptions.radius = v;
            radiusValueSpan.textContent = v;
            updateHeatmap();
        });
        heatmapBlurInput.addEventListener('input', (e) => {
            const v = parseFloat(e.target.value);
            heatmapOptions.blur = v;
            blurValueSpan.textContent = v;
            updateHeatmap();
        });
        heatmapMaxZoomInput.addEventListener('input', (e) => {
            const v = parseInt(e.target.value, 10);
            heatmapOptions.maxZoom = v;
            maxZoomValueSpan.textContent = v;
            updateHeatmap();
        });
        console.log("Heatmap control listeners setup.");
    }

    function disableHeatmapControls(disabled) {
        if (heatmapRadiusInput) heatmapRadiusInput.disabled = disabled;
        if (heatmapBlurInput) heatmapBlurInput.disabled = disabled;
        if (heatmapMaxZoomInput) heatmapMaxZoomInput.disabled = disabled;
    }


    // --- View Switching Logic ---
    function showCurrentView() {
        console.log(`Showing view: ${currentView}`);
        if (!map) {
            console.warn("Map not init.");
            return;
        }
        console.log("Removing layers...");
        if (pinLayer && map.hasLayer(pinLayer)) map.removeLayer(pinLayer);
        if (heatmapLayer && map.hasLayer(heatmapLayer)) map.removeLayer(heatmapLayer);
        console.log(`Adding ${currentView} layer...`);
        let layerToAdd = null;
        if (currentView === 'pins') {
            layerToAdd = pinLayer;
            if (heatmapOptionsPanel) heatmapOptionsPanel.style.display = 'none';
            if (clusterToggleButton) {
                clusterToggleButton.style.display = 'inline-block';
                clusterToggleButton.disabled = false;
            }
        } else {
            layerToAdd = heatmapLayer;
            if (heatmapOptionsPanel) heatmapOptionsPanel.style.display = 'block';
            if (clusterToggleButton) {
                clusterToggleButton.style.display = 'none';
                clusterToggleButton.disabled = true;
            }
        }
        if (layerToAdd) {
            try {
                map.addLayer(layerToAdd);
                console.log(`Added ${currentView} layer.`);
            } catch (e) {
                console.error(`Error adding ${currentView}:`, e);
                updateStatus(`Error display ${currentView}.`, true);
            }
        } else {
            console.warn(`Layer instance missing for ${currentView}.`);
            updateStatus(`No data for ${currentView}.`, false);
        }
    }


    // --- Button Text Update Functions ---
    function updateViewToggleButtonText() {
        if (!viewToggleButton) return;
        const next = (currentView === 'pins') ? 'Heatmap' : 'Pin';
        viewToggleButton.textContent = `Switch to ${next} View`;
        console.log(`View Btn text: ${viewToggleButton.textContent}`);
    }

    function updateClusterToggleButtonText() {
        if (!clusterToggleButton) return;
        clusterToggleButton.textContent = isClusteringEnabled ? 'Disable Clustering' : 'Enable Clustering';
        console.log(`Cluster Btn text: ${clusterToggleButton.textContent}`);
    }


    // --- Start Initialization ---
    initializeMap();

}); // End DOMContentLoaded