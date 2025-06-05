const video = document.getElementById('video');
const startCameraButton = document.getElementById('start-camera');
const stopCameraButton = document.getElementById('stop-camera');
const loginButton = document.getElementById('login');
const logoutButton = document.getElementById('logout');
const nameSpan = document.getElementById('name');
const classSpan = document.getElementById('class');
const statusSpan = document.getElementById('status');
const previousStatusSpan = document.getElementById('previous-status');
const messageParagraph = document.getElementById('message');
let stream = null;
let recognitionInterval = null;

async function startCamera() {
    try {
        stream = await navigator.mediaDevices.getUserMedia({ video: true });
        video.srcObject = stream;
        startCameraButton.classList.add('hidden');
        stopCameraButton.classList.remove('hidden');
        loginButton.disabled = false;
        logoutButton.disabled = false;
        startRecognition();
    } catch (error) {
        console.error('Error accessing camera:', error);
        alert('Could not access the camera. Please check permissions.');
    }
}

function stopCamera() {
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
        video.srcObject = null;
        stream = null;
    }
    startCameraButton.classList.remove('hidden');
    stopCameraButton.classList.add('hidden');
    loginButton.disabled = true;
    logoutButton.disabled = true;
    clearInterval(recognitionInterval);
    nameSpan.textContent = 'N/A';
    classSpan.textContent = 'N/A';
    statusSpan.textContent = 'N/A';
    previousStatusSpan.textContent = 'N/A';
    messageParagraph.textContent = 'Waiting for recognition...';
}

function startRecognition() {
    recognitionInterval = setInterval(async () => {
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const context = canvas.getContext('2d');
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        const imageData = canvas.toDataURL('image/jpeg');

        try {
            const response = await fetch('/check_identity', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image: imageData })
            });
            const data = await response.json();

            nameSpan.textContent = data.name;
            classSpan.textContent = data.class;
            statusSpan.textContent = data.status;
            previousStatusSpan.textContent = data.previous_status;
            messageParagraph.textContent = data.message || 'No message available.';
        } catch (error) {
            console.error('Error during face recognition:', error);
        }
    }, 2000);
}

async function handleAttendance(action) {
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext('2d');
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const imageData = canvas.toDataURL('image/jpeg');

    try {
        const response = await fetch('/attendance', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image: imageData, action })
        });
        const data = await response.json();

        nameSpan.textContent = data.name;
        classSpan.textContent = data.class;
        statusSpan.textContent = data.status;
        messageParagraph.textContent = data.message || 'Action completed.';
    } catch (error) {
        console.error(`Error during ${action}:`, error);
        alert(`Failed to ${action}. Please try again.`);
    }
}

startCameraButton.addEventListener('click', startCamera);
stopCameraButton.addEventListener('click', stopCamera);
loginButton.addEventListener('click', () => handleAttendance('login'));
logoutButton.addEventListener('click', () => handleAttendance('logout'));

// Check session on page load
window.addEventListener('load', async () => {
    try {
        const response = await fetch('/check_session');
        const data = await response.json();
        if (data.isLoggedIn) {
            nameSpan.textContent = data.name;
            classSpan.textContent = data.class;
            statusSpan.textContent = 'logged_in';
        }
    } catch (error) {
        console.error('Error checking session:', error);
    }
});