// Create the map and center it on Doha
const map = L.map('map').setView([25.2854, 51.5310], 12);

// Add OpenStreetMap
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

// Custom marker
const customIcon = L.icon({
    iconUrl: 'https://cdn-icons-png.flaticon.com/512/684/684908.png',
    iconSize: [35, 35],
    iconAnchor: [17, 35],
    popupAnchor: [0, -35]
});

// Build popup elements as text so database content cannot inject HTML.
function popupFor(location) {
    const content = document.createElement('div');
    content.className = 'popup-content';
    const title = document.createElement('h3');
    title.textContent = location.name;
    const description = document.createElement('p');
    description.textContent = location.description;
    content.append(title, description);
    return content;
}

async function loadLocations() {
    try {
        const response = await fetch('/api/locations');
        if (!response.ok) throw new Error(`API returned ${response.status}`);
        const locations = await response.json();

        locations.forEach(location => {
            L.marker([location.latitude, location.longitude], { icon: customIcon })
                .addTo(map)
                .bindPopup(popupFor(location));
        });
    } catch (error) {
        console.error('Could not load map locations:', error);
        const message = document.createElement('p');
        message.setAttribute('role', 'alert');
        message.textContent = 'Locations could not load. Please refresh the page.';
        document.querySelector('#map').after(message);
    }
}

loadLocations();
