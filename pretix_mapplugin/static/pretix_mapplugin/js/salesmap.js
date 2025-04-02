// Wait for the DOM to be fully loaded before running map code
document.addEventListener('DOMContentLoaded', function () {
    console.log("Sales Map JS Loaded");

    // --- Configuration ---
    const mapContainerId = 'sales-map-container';
    const toggleButtonId = 'view-toggle-btn';
    const initialZoom = 5; // Adjust as needed
    const defaultMapView = 'pins'; // Can be 'pins' or 'heatmap'
    const heatmapOptions = {
        radius: 25,
        blur: 15,
        maxZoom: 18,
        // gradient: { 0.4: 'blue', 0.65: 'lime', 1: 'red'} // Optional custom gradient
    };

    // --- Globals ---
    let map = null; // Leaflet map instance
    let allCoordinates = []; // To store fetched [lat, lon] pairs
    let pinLayer = null; // Layer for markers/clusters
    let heatmapLayer = null; // Layer for heatmap
    let currentView = defaultMapView; // Track current view state

    const mapElement = document.getElementById(mapContainerId);
    const toggleButton = document.getElementById(toggleButtonId);

    // --- Initialization ---
    function initializeMap() {
        if (!mapElement) {
            console.error(`Map container element #${mapContainerId} not found.`);
            return;
        }
         if (!toggleButton) {
            console.warn(`Toggle button #${toggleButtonId} not found.`);
            // Can continue without toggle if needed, or handle differently
        }

        console.log("Initializing Leaflet map...");

        // Center map initially (e.g., on Europe, adjust as needed)
        map = L.map(mapContainerId).setView([51.505, -0.09], initialZoom);

        // Add a base tile layer (OpenStreetMap)
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(map);

        // Setup toggle button listener if it exists
        if (toggleButton) {
             setupToggleButton();
        }

        // Fetch data and populate the map
        fetchCoordinateData();
    }

    // --- Data Fetching ---
    function fetchCoordinateData() {
        // Check if the data URL was correctly passed from the template
        if (typeof salesMapDataUrl === 'undefined' || !salesMapDataUrl) {
            console.error("Sales map data URL is not defined.");
            mapElement.innerHTML = '<p class="text-danger">Error: Could not load map data (configuration missing).</p>';
            return;
        }

        console.log("Fetching coordinates from:", salesMapDataUrl);
        mapElement.innerHTML = '<p>Loading ticket locations...</p>'; // Update status

        fetch(salesMapDataUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.error) {
                     throw new Error(`API Error: ${data.error}`);
                }
                if (!data.coordinates || data.coordinates.length === 0) {
                    console.log("No coordinate data received.");
                    mapElement.innerHTML = '<p>No geocoded ticket locations found for this event.</p>';
                    // Optionally disable toggle button if no data
                    if(toggleButton) toggleButton.disabled = true;
                    return; // Nothing to display
                }

                allCoordinates = data.coordinates;
                console.log(`Received ${allCoordinates.length} coordinates.`);
                mapElement.innerHTML = ''; // Clear loading message
                createMapLayers(); // Create layers now that we have data
                showCurrentView(); // Display the default view

                 // Adjust map bounds to fit markers if coordinates were found
                if (allCoordinates.length > 0) {
                    const bounds = L.latLngBounds(allCoordinates);
                    map.fitBounds(bounds, { padding: [50, 50] }); // Add padding
                }

            })
            .catch(error => {
                console.error('Error fetching or processing coordinate data:', error);
                mapElement.innerHTML = `<p class="text-danger">Error loading map data: ${error.message}. Please check logs or try again later.</p>`;
            });
    }

    // --- Layer Creation ---
    function createMapLayers() {
        if (!map || allCoordinates.length === 0) return;

        // 1. Create Pin Layer (using MarkerCluster)
        console.log("Creating pin layer (marker cluster)...");
        pinLayer = L.markerClusterGroup(); // Initialize cluster group
        allCoordinates.forEach(coord => {
            // Simple marker - add popups or tooltips if needed
            const marker = L.marker(new L.LatLng(coord[0], coord[1]));
            // Example popup: marker.bindPopup(`Lat: ${coord[0]}, Lon: ${coord[1]}`);
            pinLayer.addLayer(marker); // Add marker to the cluster group
        });

        // 2. Create Heatmap Layer
        console.log("Creating heatmap layer...");
        heatmapLayer = L.heatLayer(allCoordinates, heatmapOptions);

        console.log("Map layers created.");
    }

    // --- View Toggling ---
     function setupToggleButton() {
        updateButtonText(); // Set initial text
        toggleButton.addEventListener('click', () => {
            if (currentView === 'pins') {
                currentView = 'heatmap';
            } else {
                currentView = 'pins';
            }
            showCurrentView();
            updateButtonText();
        });
    }

    function showCurrentView() {
        if (!map) return;

        // Remove existing layers first
        if (pinLayer && map.hasLayer(pinLayer)) {
            map.removeLayer(pinLayer);
            console.log("Removed pin layer");
        }
        if (heatmapLayer && map.hasLayer(heatmapLayer)) {
            map.removeLayer(heatmapLayer);
            console.log("Removed heatmap layer");
        }

        // Add the selected layer
        if (currentView === 'pins' && pinLayer) {
            map.addLayer(pinLayer);
            console.log("Added pin layer");
        } else if (currentView === 'heatmap' && heatmapLayer) {
            map.addLayer(heatmapLayer);
            console.log("Added heatmap layer");
        }
    }

    function updateButtonText() {
         if (!toggleButton) return;
         if (currentView === 'pins') {
            toggleButton.textContent = 'Switch to Heatmap View';
        } else {
            toggleButton.textContent = 'Switch to Pin View';
        }
    }


    // --- Start ---
    initializeMap();

}); // End DOMContentLoaded