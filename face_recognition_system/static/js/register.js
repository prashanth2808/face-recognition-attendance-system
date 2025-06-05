navigator.mediaDevices.getUserMedia({ video: true })
    .then(stream => {
        const video = document.getElementById('video');
        video.srcObject = stream;
    })
    .catch(err => console.error('Error accessing webcam:', err));

    document.addEventListener('DOMContentLoaded', () => {
        const video = document.getElementById('video');
        const canvas = document.getElementById('canvas');
    
        // Request webcam access
        navigator.mediaDevices.getUserMedia({ video: true })
            .then(stream => {
                video.srcObject = stream;
                video.play().catch(err => console.error('Error playing video:', err));
            })
            .catch(err => {
                console.error('Error accessing webcam:', err);
                alert('Failed to access webcam. Please check permissions or ensure a camera is connected.');
            });
    
        document.getElementById('registerForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            canvas.getContext('2d').drawImage(video, 0, 0);
    
            const formData = new FormData();
            formData.append('name', document.getElementById('name').value);
            formData.append('class', document.getElementById('class').value);
            formData.append('image', canvas.toDataURL('image/jpeg'));
    
            try {
                const response = await fetch('/register', {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();
                document.getElementById('message').textContent = result.message || result.error;
            } catch (error) {
                document.getElementById('message').textContent = 'Error registering student';
            }
        });
    });