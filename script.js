// Create the map and center it on Doha
const map = L.map('map').setView([25.2854, 51.5310], 12);

// Add OpenStreetMap
L.tileLayer(
    'https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png?key=cb1_4dl2_1_5eeee814f8b39698d1cd6f4b',
    {
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
        maxZoom: 20
    }
).addTo(map);

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

    // Show one description: prefer the story summary when available.
    const story = location.stories?.[0];
    const description = document.createElement('p');
    description.textContent = story?.summary?.trim() || location.description;
    content.append(title, description);

    // Each marker shows the latest prediction saved for its location.
    const crowd = document.createElement('p');
    const status = location.crowd_status;
    if (status) {
        const label = status.source === 'test' ? 'Test prediction' : 'Crowd prediction';
        crowd.textContent = `${label}: ${status.prediction} (${status.total_score}/8)`;
    } else {
        crowd.textContent = 'No crowd prediction yet.';
    }
    

    // Show multimedia for this location, if available.
    if (story) {
        // Display the thumbnail image.
        if (story.thumbnail_path) {
            const image = document.createElement('img');
            image.src = story.thumbnail_path;
            image.alt = location.name;
            image.style.width = '220px';
            image.style.maxWidth = '100%';
            content.append(image);
        }

        // Display a link to the video.
        if (story.video_url) {
            const video = document.createElement('p');
            const link = document.createElement('a');
            link.href = story.video_url;
            link.textContent = 'Watch Video';
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            video.append(link);
            content.append(video);
        }

        // Display a link to the audio.
        if (story.audio_url) {
            const audio = document.createElement('p');
            const link = document.createElement('a');
            link.href = story.audio_url;
            link.textContent = 'Listen to Audio';
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            audio.append(link);
            content.append(audio);
        }   
    }
    content.append(crowd);
    
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
