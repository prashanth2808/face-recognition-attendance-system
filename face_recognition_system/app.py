from flask import Flask, render_template, request, jsonify, send_file
import cv2
import face_recognition
import numpy as np
import sqlite3
import os
from datetime import datetime
import base64
from io import BytesIO
from PIL import Image
import time

app = Flask(__name__)
UPLOAD_FOLDER = 'static/uploads/faces'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Dictionary to track the last time each student's attendance was recorded
last_attendance_time = {}

# Define the datetimeformat filter
def datetimeformat(value):
    if not value or not isinstance(value, str):
        return 'N/A'
    try:
        dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        return dt.strftime('%m/%d/%Y %I:%M %p')
    except ValueError:
        try:
            dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f')
            return dt.strftime('%m/%d/%Y %I:%M %p')
        except ValueError:
            return 'Invalid Date'

# Register the filter with Flask's Jinja environment
app.jinja_env.filters['datetimeformat'] = datetimeformat

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Check if the attendance table exists and update its schema
    c.execute(''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='attendance' ''')
    table_exists = c.fetchone()[0]

    if table_exists:
        # Check if the old columns (timestamp) exist and migrate to new schema (logged_in_time, logged_out_time)
        c.execute('PRAGMA table_info(attendance)')
        columns = [info[1] for info in c.fetchall()]
        if 'timestamp' in columns:
            # Rename the existing attendance table
            c.execute('ALTER TABLE attendance RENAME TO attendance_old')
            # Create the new attendance table with logged_in_time and logged_out_time
            c.execute('''CREATE TABLE attendance 
                         (id INTEGER PRIMARY KEY, student_id INTEGER, name TEXT, class TEXT, 
                          logged_in_time TEXT, logged_out_time TEXT, status TEXT,
                          FOREIGN KEY (student_id) REFERENCES students(id))''')
            # Migrate data from the old table to the new table (logged_out_time will be NULL for existing records)
            c.execute('''INSERT INTO attendance (id, student_id, name, class, logged_in_time, status)
                         SELECT id, student_id, name, class, timestamp, status FROM attendance_old''')
            # Drop the old table
            c.execute('DROP TABLE attendance_old')
            conn.commit()

    # Create tables if they don't exist
    c.execute('''CREATE TABLE IF NOT EXISTS students 
                 (id INTEGER PRIMARY KEY, name TEXT, class TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS face_encodings 
                 (id INTEGER PRIMARY KEY, student_id INTEGER, face_encoding BLOB, 
                  FOREIGN KEY (student_id) REFERENCES students(id))''')
    if not table_exists:  # Only create attendance table if it wasn't migrated
        c.execute('''CREATE TABLE IF NOT EXISTS attendance 
                     (id INTEGER PRIMARY KEY, student_id INTEGER, name TEXT, class TEXT, 
                      logged_in_time TEXT, logged_out_time TEXT, status TEXT,
                      FOREIGN KEY (student_id) REFERENCES students(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS login_sessions 
                 (id INTEGER PRIMARY KEY, student_id INTEGER, login_time TEXT, logout_time TEXT, class_duration INTEGER,
                  FOREIGN KEY (student_id) REFERENCES students(id))''')
    # Drop the break_records table if it exists
    c.execute('''DROP TABLE IF EXISTS break_records''')

    # Clean up login_sessions to ensure at most one open session per student
    c.execute('''SELECT student_id, id, login_time FROM login_sessions 
                 WHERE logout_time IS NULL 
                 ORDER BY login_time DESC''')
    sessions = c.fetchall()
    seen_students = set()
    for student_id, session_id, login_time in sessions:
        if student_id in seen_students:
            # Mark older sessions as closed (set logout_time to login_time)
            c.execute('UPDATE login_sessions SET logout_time = ? WHERE id = ?',
                      (login_time, session_id))
        else:
            seen_students.add(student_id)

    # Validate timestamps in login_sessions
    c.execute('''UPDATE login_sessions 
                 SET login_time = NULL 
                 WHERE login_time NOT LIKE '____-__-__ __:__:__' ''')
    c.execute('''UPDATE login_sessions 
                 SET logout_time = NULL 
                 WHERE logout_time NOT LIKE '____-__-__ __:__:__' ''')

    conn.commit()
    conn.close()

init_db()

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        student_class = request.form['class']
        image_data = request.form['image'].split(',')[1]
        image = Image.open(BytesIO(base64.b64decode(image_data)))
        image_np = np.array(image)

        image_np = cv2.convertScaleAbs(image_np, alpha=1.2, beta=20)
        face_encodings = face_recognition.face_encodings(image_np)
        if not face_encodings:
            return jsonify({'error': 'No face detected'}), 400

        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute('INSERT INTO students (name, class) VALUES (?, ?)', (name, student_class))
        student_id = c.lastrowid
        c.execute('INSERT INTO face_encodings (student_id, face_encoding) VALUES (?, ?)',
                  (student_id, face_encodings[0].tobytes()))
        conn.commit()
        print(f"Registered student: {name}, ID: {student_id}, Class: {student_class}")  # Debug log
        conn.close()

        image_path = os.path.join(UPLOAD_FOLDER, f'{student_id}.jpg')
        image.save(image_path)

        return jsonify({'message': 'Student registered successfully'})

    return render_template('register.html')

@app.route('/attendance', methods=['GET', 'POST'])
def attendance():
    global last_attendance_time

    if request.method == 'POST':
        # Parse the JSON payload
        data = request.get_json()
        if not data or 'image' not in data or 'action' not in data:
            return jsonify({'name': 'N/A', 'class': 'N/A', 'status': 'N/A', 'message': 'Invalid request'}), 400

        image_data = data['image'].split(',')[1]
        action = data['action']
        image = Image.open(BytesIO(base64.b64decode(image_data)))
        image_np = np.array(image)

        image_np = cv2.convertScaleAbs(image_np, alpha=1.2, beta=20)
        face_encodings = face_recognition.face_encodings(image_np)
        if not face_encodings:
            return jsonify({'name': 'Unknown Student', 'class': 'N/A', 'status': 'N/A', 'message': 'No face detected'})

        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute('SELECT s.id, s.name, s.class, f.face_encoding FROM students s '
                 'JOIN face_encodings f ON s.id = f.student_id')
        students = c.fetchall()

        best_match = None
        min_distance = float('inf')
        tolerance = 0.45

        for student in students:
            student_id, name, student_class, encoding = student
            known_encoding = np.frombuffer(encoding)
            distances = face_recognition.face_distance([known_encoding], face_encodings[0])
            distance = distances[0]
            if distance < min_distance and distance < tolerance:
                min_distance = distance
                best_match = (student_id, name, student_class)

        if not best_match:
            conn.close()
            return jsonify({'name': 'Unknown Student', 'class': 'N/A', 'status': 'N/A', 'message': 'Unknown student'})

        student_id, name, student_class = best_match
        current_time = datetime.now()
        timestamp = current_time.strftime('%Y-%m-%d %H:%M:%S')

        # Cooldown check
        current_time_seconds = time.time()
        last_recorded = last_attendance_time.get(student_id, 0)
        if current_time_seconds - last_recorded < 10:
            conn.close()
            return jsonify({'name': name, 'class': student_class, 'status': 'N/A', 'message': 'Please wait before taking attendance again'})

        # Check last login session
        c.execute('SELECT login_time, logout_time, class_duration FROM login_sessions '
                  'WHERE student_id = ? ORDER BY login_time DESC LIMIT 1', (student_id,))
        last_session = c.fetchone()

        # Determine the expected action based on session state
        is_currently_logged_in = last_session and not last_session[1]

        if action == 'login' and is_currently_logged_in:
            conn.close()
            return jsonify({'name': name, 'class': student_class, 'status': 'logged_in', 'message': 'Already logged in'})
        elif action == 'logout' and not is_currently_logged_in:
            conn.close()
            return jsonify({'name': name, 'class': student_class, 'status': 'logged_out', 'message': 'Already logged out'})

        # Normal login/logout logic
        if action == 'login':
            c.execute('INSERT INTO login_sessions (student_id, login_time, class_duration) VALUES (?, ?, ?)',
                      (student_id, timestamp, 0))
            c.execute('INSERT INTO attendance (student_id, name, class, logged_in_time, logged_out_time, status) VALUES (?, ?, ?, ?, ?, ?)',
                      (student_id, name, student_class, timestamp, None, 'logged_in'))
            last_attendance_time[student_id] = current_time_seconds
            conn.commit()
            print(f"Login recorded for student_id {student_id}: login_time={timestamp}")  # Debug log
            # Verify the insertion
            c.execute('SELECT * FROM login_sessions WHERE student_id = ? ORDER BY login_time DESC LIMIT 1', (student_id,))
            latest_session = c.fetchone()
            print(f"Latest login session for student_id {student_id}: {latest_session}")  # Debug log
            conn.close()
            return jsonify({'name': name, 'class': student_class, 'status': 'logged_in', 'message': 'Logged in'})
        else:  # action == 'logout'
            login_time = datetime.strptime(last_session[0], '%Y-%m-%d %H:%M:%S')
            time_diff = (current_time - login_time).total_seconds()
            if time_diff < 30:
                conn.close()
                return jsonify({'name': name, 'class': student_class, 'status': 'logged_in', 'message': 'Cannot logout within 30 seconds'})
            class_duration = last_session[2] or 0
            session_duration = int(time_diff)
            class_duration += session_duration
            c.execute('UPDATE login_sessions SET logout_time = ?, class_duration = ? WHERE student_id = ? AND logout_time IS NULL',
                      (timestamp, class_duration, student_id))
            c.execute('INSERT INTO attendance (student_id, name, class, logged_in_time, logged_out_time, status) VALUES (?, ?, ?, ?, ?, ?)',
                      (student_id, name, student_class, None, timestamp, 'logged_out'))
            last_attendance_time[student_id] = current_time_seconds
            conn.commit()
            print(f"Logout recorded for student_id {student_id}: logout_time={timestamp}, class_duration={class_duration}")  # Debug log
            # Verify the update
            c.execute('SELECT * FROM login_sessions WHERE student_id = ? ORDER BY login_time DESC LIMIT 1', (student_id,))
            latest_session = c.fetchone()
            print(f"Latest session after logout for student_id {student_id}: {latest_session}")  # Debug log
            conn.close()
            return jsonify({'name': name, 'class': student_class, 'status': 'logged_out', 'message': 'Logged out'})

    return render_template('attendance.html')

@app.route('/check_session', methods=['GET'])
def check_session():
    # For simplicity, this assumes a single user; in a real app, use authentication to identify the user
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT s.id, s.name, s.class, l.login_time, l.logout_time FROM login_sessions l '
              'JOIN students s ON l.student_id = s.id '
              'ORDER BY l.login_time DESC LIMIT 1')
    last_session = c.fetchone()
    conn.close()

    if last_session and not last_session[4]:  # logout_time is NULL
        student_id, name, student_class, login_time, logout_time = last_session
        return jsonify({'isLoggedIn': True, 'name': name, 'class': student_class})
    return jsonify({'isLoggedIn': False, 'name': 'N/A', 'class': 'N/A'})

@app.route('/check_identity', methods=['POST'])
def check_identity():
    data = request.get_json()
    if not data or 'image' not in data:
        return jsonify({'name': 'N/A', 'class': 'N/A', 'status': 'N/A', 'previous_status': 'N/A', 'message': 'Invalid request'}), 400

    image_data = data['image'].split(',')[1]
    image = Image.open(BytesIO(base64.b64decode(image_data)))
    image_np = np.array(image)

    image_np = cv2.convertScaleAbs(image_np, alpha=1.2, beta=20)
    face_encodings = face_recognition.face_encodings(image_np)
    if not face_encodings:
        return jsonify({'name': 'Unknown Student', 'class': 'N/A', 'status': 'N/A', 'previous_status': 'N/A', 'message': 'No face detected'})

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT s.id, s.name, s.class, f.face_encoding FROM students s '
              'JOIN face_encodings f ON s.id = f.student_id')
    students = c.fetchall()

    best_match = None
    min_distance = float('inf')
    tolerance = 0.45

    for student in students:
        student_id, name, student_class, encoding = student
        known_encoding = np.frombuffer(encoding)
        distances = face_recognition.face_distance([known_encoding], face_encodings[0])
        distance = distances[0]
        if distance < min_distance and distance < tolerance:
            min_distance = distance
            best_match = (student_id, name, student_class)

    if not best_match:
        conn.close()
        return jsonify({'name': 'Unknown Student', 'class': 'N/A', 'status': 'N/A', 'previous_status': 'N/A', 'message': 'Unknown student'})

    student_id, name, student_class = best_match

    # Check the student's login status
    c.execute('SELECT login_time, logout_time FROM login_sessions '
              'WHERE student_id = ? ORDER BY login_time DESC LIMIT 1', (student_id,))
    last_session = c.fetchone()

    is_currently_logged_in = last_session and not last_session[1]
    status = 'logged_in' if is_currently_logged_in else 'logged_out'
    previous_status = 'Logged In' if is_currently_logged_in else 'Logged Out'

    # Generate the personalized message based on previous_status
    if previous_status == 'Logged In':
        message = f"Hi {name}, Previously You had logged in, if you are willing to logout please click on logout."
    else:  # previous_status == 'Logged Out'
        message = f"Hi {name}, Previously You had logged out, if you are willing to login please click on login."

    conn.close()
    return jsonify({
        'name': name,
        'class': student_class,
        'status': status,
        'previous_status': previous_status,
        'message': message
    })

@app.route('/database')
def database():
    try:
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        # Fetch students with their most recent login and logout times
        try:
            c.execute('''SELECT s.id, s.name, s.class, 
                                (SELECT MAX(l1.login_time) FROM login_sessions l1 WHERE l1.student_id = s.id) as last_login,
                                (SELECT MAX(l2.logout_time) FROM login_sessions l2 WHERE l2.student_id = s.id) as last_logout
                         FROM students s
                         GROUP BY s.id, s.name, s.class''')
            students_with_logins = c.fetchall()
            print("Students with Logins and Logouts:", students_with_logins)  # Debug log
        except sqlite3.Error as e:
            print(f"Error fetching students_with_logins: {e}")
            students_with_logins = []

        # Fetch attendance records
        try:
            c.execute('''SELECT student_id, name, class, logged_in_time, logged_out_time, status 
                         FROM attendance 
                         ORDER BY id DESC''')
            attendance_records = c.fetchall()
            print("Attendance Records:", attendance_records)  # Debug log
        except sqlite3.Error as e:
            print(f"Error fetching attendance_records: {e}")
            attendance_records = []

        # Additional debug: Fetch all login_sessions to verify data
        try:
            c.execute('SELECT * FROM login_sessions ORDER BY login_time DESC')
            all_sessions = c.fetchall()
            print("All login_sessions records:", all_sessions)  # Debug log
        except sqlite3.Error as e:
            print(f"Error fetching login_sessions: {e}")

        conn.close()
        return render_template('database.html', students_with_logins=students_with_logins, attendance_records=attendance_records)
    except Exception as e:
        print(f"Error in /database route: {e}")
        return "An error occurred while loading the database page. Please check the server logs.", 500

@app.route('/delete_student/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    try:
        conn = sqlite3.connect('database.db')
        c = conn.cursor()

        # Delete associated records from related tables
        c.execute('DELETE FROM face_encodings WHERE student_id = ?', (student_id,))
        c.execute('DELETE FROM login_sessions WHERE student_id = ?', (student_id,))
        c.execute('DELETE FROM attendance WHERE student_id = ?', (student_id,))
        # Delete the student from the students table
        c.execute('DELETE FROM students WHERE id = ?', (student_id,))

        conn.commit()
        conn.close()

        # Delete the student's face image file
        image_path = os.path.join(UPLOAD_FOLDER, f'{student_id}.jpg')
        if os.path.exists(image_path):
            os.remove(image_path)

        return jsonify({'message': 'Student deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/video_feed')
def video_feed():
    return send_file('static/uploads/temp.jpg')

if __name__ == '__main__':
    app.run(debug=True)