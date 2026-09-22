// Create the map and center it on Doha
const map = L.map('map').setView([25.2854, 51.5310], 12);

// Add OpenStreetMap
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

//custome marker 

const customIcon = L.icon({
    iconUrl: 'https://cdn-icons-png.flaticon.com/512/684/684908.png',
    iconSize: [35, 35],
    iconAnchor: [17, 35],
    popupAnchor: [0, -35]
});

// Souq Waqif
L.marker([25.2867, 51.5333], { icon: customIcon })
    .addTo(map)
    .bindPopup(`
        <div class="popup-content">
            <h3>Souq Waqif</h3>
            <p>Traditional market with restaurants, shops, and evening activities.</p>
        </div>
    `);

// Doha Corniche
L.marker([25.3020, 51.5195], { icon: customIcon })
    .addTo(map)
    .bindPopup(`
        <div class="popup-content">
            <h3>Doha Corniche</h3>
            <p>A waterfront promenade with beautiful views of Doha at night.</p>
        </div>
    `);

// Katara Cultural Village
L.marker([25.3608, 51.5253], { icon: customIcon })
    .addTo(map)
    .bindPopup(`
        <div class="popup-content">
            <h3>Katara Cultural Village</h3>
            <p>A cultural destination with restaurants, events, art, and entertainment.</p>
        </div>
    `);