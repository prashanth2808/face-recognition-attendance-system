Face Recognition Attendance System

A web-based attendance system that uses real-time face recognition to register and track student attendance via a live camera feed.

Features:

Live Face Recognition: Embedded camera feed in the web UI for real-time detection.

Student Registration: Add new students with Name and Class; system generates face encodings.

Start/Stop Control: Easily start or stop attendance capture from the dashboard.

Attendance Logging: Attendance entries (Name, Class, Time, Status) saved to CSV or database.

Unknown Alerts: Flags unrecognized faces for later review.


Tech Stack:

Backend: Python 3.12+, Flask

Computer Vision: OpenCV (cv2.CAP_DSHOW on Windows)

Face Recognition: face_recognition

Data Storage: CSV / SQLite / any configured database

Frontend: HTML5, CSS3, JavaScript (Fetch API)
