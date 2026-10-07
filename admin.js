const form = document.querySelector('#location-form');
const statusMessage = document.querySelector('#status');
const saveButton = document.querySelector('#save');
const cancelButton = document.querySelector('#cancel');
let editingId = null;

function resetForm() {
    editingId = null;
    form.reset();
    document.querySelector('#form-title').textContent = 'Add a location';
    cancelButton.hidden = true;
}

async function loadLocations() {
    const response = await fetch('/api/locations');
    if (!response.ok) throw new Error('Could not load saved locations.');
    const locations = await response.json();
    const container = document.querySelector('#locations');
    container.replaceChildren();
    locations.forEach(location => {
        const card = document.createElement('article');
        const title = document.createElement('h3');
        title.textContent = location.name;
        const description = document.createElement('p');
        description.textContent = location.description;
        const coordinates = document.createElement('p');
        coordinates.textContent = `Latitude: ${location.latitude}, longitude: ${location.longitude}`;
        const edit = document.createElement('button');
        edit.type = 'button';
        edit.textContent = 'Edit';
        edit.setAttribute('aria-label', `Edit ${location.name}`);
        edit.addEventListener('click', () => {
            editingId = location.id;
            for (const field of ['name', 'description', 'latitude', 'longitude']) {
                form.elements[field].value = location[field];
            }
            document.querySelector('#form-title').textContent = `Edit ${location.name}`;
            cancelButton.hidden = false;
            statusMessage.textContent = '';
            form.elements.name.focus();
        });
        card.append(title, description, coordinates, edit);
        container.append(card);
    });
}

cancelButton.addEventListener('click', resetForm);
form.addEventListener('submit', async event => {
    event.preventDefault();
    saveButton.disabled = true;
    statusMessage.textContent = 'Saving…';
    const data = Object.fromEntries(new FormData(form));
    data.latitude = Number(data.latitude);
    data.longitude = Number(data.longitude);
    let saved = false;
    try {
        const response = await fetch(editingId === null ? '/api/locations' : `/api/locations/${editingId}`, {
            method: editingId === null ? 'POST' : 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Could not save location.');
        saved = true;
        resetForm();
        await loadLocations();
        statusMessage.textContent = 'Location saved. Open or refresh the map to see the change.';
    } catch (error) {
        statusMessage.textContent = saved ? 'Location saved, but the list could not refresh. Reload this page.' : error.message;
    } finally {
        saveButton.disabled = false;
    }
});
loadLocations().catch(error => { statusMessage.textContent = error.message; });
