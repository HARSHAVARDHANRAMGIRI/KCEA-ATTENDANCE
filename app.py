from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
from datetime import datetime, date
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = 'kcea-attendance-2024-secret-key'

# Database setup
def init_db():
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            college_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT,
            class_name TEXT,
            semester TEXT,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'student',
            photo_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Attendance table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            period INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            status TEXT DEFAULT 'present',
            subject TEXT,
            FOREIGN KEY (student_id) REFERENCES users (id)
        )
    ''')

    # Migration: ensure required columns exist for older databases
    cursor.execute("PRAGMA table_info(attendance)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'period' not in columns:
        cursor.execute("ALTER TABLE attendance ADD COLUMN period INTEGER")
    if 'subject' not in columns:
        cursor.execute("ALTER TABLE attendance ADD COLUMN subject TEXT")
    if 'timestamp' not in columns:
        cursor.execute("ALTER TABLE attendance ADD COLUMN timestamp TEXT")
    if 'status' not in columns:
        cursor.execute("ALTER TABLE attendance ADD COLUMN status TEXT DEFAULT 'present'")
    
    # Class periods table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS class_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_number INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            subject TEXT,
            is_lunch BOOLEAN DEFAULT FALSE
        )
    ''')
    
    # Clear existing periods and insert new 6-period schedule
    cursor.execute('DELETE FROM class_periods')
    periods = [
        (1, '10:00', '11:00', 'Period 1', False),
        (2, '11:00', '12:00', 'Period 2', False),
        (3, '12:00', '13:00', 'Period 3', False),
        (4, '13:00', '13:30', 'Lunch Break', True),
        (5, '13:30', '14:30', 'Period 4', False),
        (6, '14:30', '15:30', 'Period 5', False),
        (7, '15:30', '16:30', 'Period 6', False)
    ]
    cursor.executemany('INSERT INTO class_periods (period_number, start_time, end_time, subject, is_lunch) VALUES (?, ?, ?, ?, ?)', periods)
    
    # Create admin user if not exists
    cursor.execute('SELECT id FROM users WHERE email = ?', ('r.harsha0541@gmail.com',))
    if not cursor.fetchone():
        admin_password = generate_password_hash('admin123')
        cursor.execute('''
            INSERT INTO users (college_id, name, email, phone, class_name, semester, password_hash, role)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', ('ADMIN001', 'Harshavardhan Ramgiri', 'r.harsha0541@gmail.com', '9876543210', 'ADMIN', 'ADMIN', admin_password, 'admin'))
    
    # OTP table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS otps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            otp TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            used BOOLEAN DEFAULT FALSE
        )
    ''')
    
    conn.commit()
    conn.close()

# Email configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_ADDRESS = "kcea.attendance@gmail.com"  # Replace with actual email
EMAIL_PASSWORD = "your-app-password"  # Replace with actual app password

def send_otp_email(email, otp):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = email
        msg['Subject'] = "KCEA Attendance Portal - OTP Verification"
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #d32f2f; margin: 0;">KCEA Attendance Portal</h1>
                    <p style="color: #666; margin: 10px 0 0 0;">Kshatriya College of Engineering</p>
                </div>
                
                <h2 style="color: #333; text-align: center;">OTP Verification</h2>
                <p style="color: #666; font-size: 16px; line-height: 1.6;">
                    Your One-Time Password (OTP) for login is:
                </p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <span style="background-color: #d32f2f; color: white; padding: 15px 30px; font-size: 24px; font-weight: bold; border-radius: 5px; letter-spacing: 3px;">
                        {otp}
                    </span>
                </div>
                
                <p style="color: #666; font-size: 14px; text-align: center;">
                    This OTP is valid for 5 minutes. Do not share it with anyone.
                </p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                <p style="color: #999; font-size: 12px; text-align: center;">
                    © 2024 Kshatriya College of Engineering. All rights reserved.
                </p>
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(EMAIL_ADDRESS, email, text)
        server.quit()
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        roll_number = request.form['roll_number']
        password = request.form['password']
        
        # Check user credentials
        conn = sqlite3.connect('attendance.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE college_id = ?', (roll_number,))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user[7], password):  # user[7] is password_hash
            session['user_id'] = user[0]
            session['user_name'] = user[2]
            session['user_role'] = user[8]
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid roll number or password!', 'error')
    
    return render_template('login.html')

@app.route('/verify-otp/<email>', methods=['GET', 'POST'])
def verify_otp(email):
    if request.method == 'POST':
        otp = request.form['otp']
        
        conn = sqlite3.connect('attendance.db')
        cursor = conn.cursor()
        
        # Check OTP
        cursor.execute('''
            SELECT * FROM otps 
            WHERE email = ? AND otp = ? AND used = FALSE 
            AND datetime(created_at) > datetime('now', '-5 minutes')
            ORDER BY created_at DESC LIMIT 1
        ''', (email, otp))
        
        otp_record = cursor.fetchone()
        
        if otp_record:
            # Mark OTP as used
            cursor.execute('UPDATE otps SET used = TRUE WHERE id = ?', (otp_record[0],))
            
            # Get user
            cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
            user = cursor.fetchone()
            
            if user:
                session['user_id'] = user[0]
                session['user_name'] = user[2]
                session['user_role'] = user[8]
                conn.close()
                return redirect(url_for('dashboard'))
            else:
                flash('User not found. Please register first.', 'error')
                conn.close()
                return redirect(url_for('signup'))
        else:
            flash('Invalid or expired OTP.', 'error')
            conn.close()
    
    return render_template('verify_otp.html', email=email)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        college_id = request.form['college_id']
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        class_name = request.form['class_name']
        semester = request.form['semester']
        password = request.form['password']
        
        # Validate phone number
        if not phone.isdigit() or len(phone) != 10:
            flash('Phone number must be exactly 10 digits.', 'error')
            return render_template('signup.html')
        
        conn = sqlite3.connect('attendance.db')
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute('SELECT id FROM users WHERE email = ? OR college_id = ?', (email, college_id))
        if cursor.fetchone():
            flash('User already exists with this email or college ID.', 'error')
            conn.close()
            return render_template('signup.html')
        
        # Create user
        password_hash = generate_password_hash(password)
        cursor.execute('''
            INSERT INTO users (college_id, name, email, phone, class_name, semester, password_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (college_id, name, email, phone, class_name, semester, password_hash))
        
        conn.commit()
        conn.close()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('signup.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    # Get user info
    cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = cursor.fetchone()
    
    # Get attendance records
    cursor.execute('''
        SELECT date, timestamp, status FROM attendance 
        WHERE student_id = ? 
        ORDER BY date DESC, timestamp DESC 
        LIMIT 10
    ''', (session['user_id'],))
    attendance_records = cursor.fetchall()
    
    # Calculate attendance percentage
    cursor.execute('''
        SELECT COUNT(*) FROM attendance 
        WHERE student_id = ? AND status = 'present'
    ''', (session['user_id'],))
    present_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM attendance WHERE student_id = ?', (session['user_id'],))
    total_count = cursor.fetchone()[0]
    
    attendance_percentage = (present_count / total_count * 100) if total_count > 0 else 0
    
    conn.close()
    
    return render_template('dashboard.html', 
                         user=user, 
                         attendance_records=attendance_records,
                         attendance_percentage=round(attendance_percentage, 1))

@app.route('/mark-attendance', methods=['POST'])
def mark_attendance():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    data = request.get_json()
    period = data.get('period', 1)
    subject = data.get('subject', '')
    
    today = date.today().isoformat()
    now = datetime.now().strftime('%H:%M:%S')
    current_time = datetime.now().strftime('%H:%M')
    
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    # Get current period info
    cursor.execute('SELECT * FROM class_periods WHERE period_number = ?', (period,))
    period_info = cursor.fetchone()
    
    if not period_info:
        conn.close()
        return jsonify({'success': False, 'message': 'Invalid period'})
    
    # Check if it's lunch time
    if bool(period_info[5]):  # is_lunch column index 5
        conn.close()
        return jsonify({'success': False, 'message': 'Cannot mark attendance during lunch break'})
    
    # Check if attendance already marked for this period today
    cursor.execute('SELECT id FROM attendance WHERE student_id = ? AND date = ? AND period = ?', 
                   (session['user_id'], today, period))
    if cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': f'Attendance already marked for Period {period} today'})
    
    # Check if it's within class time (allow 5 minutes grace period)
    start_time = period_info[2]  # start_time
    end_time = period_info[3]    # end_time
    
    if current_time < start_time:
        conn.close()
        return jsonify({'success': False, 'message': f'Class starts at {start_time}. Please wait.'})
    
    if current_time > end_time:
        conn.close()
        return jsonify({'success': False, 'message': f'Class ended at {end_time}. Too late to mark attendance.'})
    
    # Mark attendance
    cursor.execute('''
        INSERT INTO attendance (student_id, date, period, timestamp, status, subject)
        VALUES (?, ?, ?, ?, 'present', ?)
    ''', (session['user_id'], today, period, now, subject))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': f'Attendance marked for Period {period} successfully'})

@app.route('/api/current-period')
def get_current_period():
    current_time = datetime.now().strftime('%H:%M')
    
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    # Get all periods
    cursor.execute('SELECT * FROM class_periods ORDER BY period_number')
    periods = cursor.fetchall()
    conn.close()
    
    current_period = None
    for period in periods:
        if period[2] <= current_time <= period[3]:  # start_time <= current <= end_time
            current_period = {
                'period_number': period[1],
                'start_time': period[2],
                'end_time': period[3],
                'subject': period[4],
                'is_lunch': bool(period[5])
            }
            break
    
    return jsonify({
        'current_period': current_period,
        'current_time': current_time,
        'all_periods': [{
            'period_number': p[1],
            'start_time': p[2],
            'end_time': p[3],
            'subject': p[4],
            'is_lunch': bool(p[5])
        } for p in periods]
    })

@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    # Check if user is admin
    cursor.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],))
    user_role = cursor.fetchone()
    
    if not user_role or user_role[0] != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('dashboard'))
    
    # Get all users
    cursor.execute('SELECT id, college_id, name, email, phone, class_name, semester, role, created_at FROM users ORDER BY created_at DESC')
    all_users = cursor.fetchall()
    
    # Get attendance statistics
    cursor.execute('SELECT COUNT(*) FROM attendance')
    total_attendance = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE role = "student"')
    total_students = cursor.fetchone()[0]
    
    # Get recent attendance
    cursor.execute('''
        SELECT u.name, u.college_id, a.date, a.period, a.timestamp, a.subject
        FROM attendance a
        JOIN users u ON a.student_id = u.id
        ORDER BY a.timestamp DESC
        LIMIT 20
    ''')
    recent_attendance = cursor.fetchall()
    
    conn.close()
    
    return render_template('admin_dashboard.html', 
                         users=all_users, 
                         total_students=total_students,
                         total_attendance=total_attendance,
                         recent_attendance=recent_attendance)

@app.route('/admin/users')
def admin_users():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()
    
    # Check if user is admin
    cursor.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],))
    user_role = cursor.fetchone()
    
    if not user_role or user_role[0] != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('dashboard'))
    
    # Get all users with attendance count
    cursor.execute('''
        SELECT u.id, u.college_id, u.name, u.email, u.phone, u.class_name, u.semester, u.role, u.created_at,
               COUNT(a.id) as attendance_count
        FROM users u
        LEFT JOIN attendance a ON u.id = a.student_id
        GROUP BY u.id
        ORDER BY u.created_at DESC
    ''')
    users = cursor.fetchall()
    
    conn.close()
    
    return render_template('admin_users.html', users=users)

@app.route('/admin/attendance')
def admin_attendance_by_class():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()

    # Check admin
    cursor.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],))
    role_row = cursor.fetchone()
    if not role_row or role_row[0] != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('dashboard'))

    # Class filter
    selected_class = request.args.get('class')

    # Distinct classes
    cursor.execute("SELECT DISTINCT class_name FROM users WHERE role='student' AND class_name IS NOT NULL ORDER BY class_name")
    classes = [row[0] for row in cursor.fetchall()]

    # Build query
    params = []
    base_query = '''
        SELECT u.id, u.name, u.college_id, u.class_name, u.semester,
               COALESCE(SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END), 0) AS present_count,
               COUNT(a.id) AS total_count
        FROM users u
        LEFT JOIN attendance a ON a.student_id = u.id
        WHERE u.role = 'student'
    '''
    if selected_class:
        base_query += ' AND u.class_name = ?'
        params.append(selected_class)
    base_query += ' GROUP BY u.id ORDER BY u.class_name, u.name'

    cursor.execute(base_query, params)
    rows = cursor.fetchall()

    # Compute percentage in Python for clarity
    summaries = []
    for r in rows:
        present = r[5]
        total = r[6]
        percent = round((present / total * 100), 1) if total else 0.0
        summaries.append({
            'id': r[0], 'name': r[1], 'college_id': r[2], 'class_name': r[3], 'semester': r[4],
            'present': present, 'total': total, 'percent': percent
        })

    conn.close()
    return render_template('admin_attendance.html', classes=classes, selected_class=selected_class, summaries=summaries)

@app.route('/admin/reset-password', methods=['POST'])
def admin_reset_password():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    conn = sqlite3.connect('attendance.db')
    cursor = conn.cursor()

    # Check admin
    cursor.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],))
    role_row = cursor.fetchone()
    if not role_row or role_row[0] != 'admin':
        conn.close()
        return jsonify({'success': False, 'message': 'Access denied'})

    data = request.get_json() or {}
    college_id = data.get('college_id')
    if not college_id:
        conn.close()
        return jsonify({'success': False, 'message': 'college_id is required'})

    # Find user
    cursor.execute('SELECT id, email FROM users WHERE college_id = ?', (college_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})

    # Generate new password
    new_password = secrets.token_hex(4)  # 8 hex chars
    new_hash = generate_password_hash(new_password)
    cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_hash, user[0]))
    conn.commit()
    conn.close()

    # In production, email the password. Here we return it to the admin for immediate use.
    return jsonify({'success': True, 'message': 'Password reset', 'new_password': new_password})



@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# Ensure DB is initialized even when running under Gunicorn
try:
    init_db()
except Exception as e:
    print(f"DB init error: {e}")

if __name__ == '__main__':
    app.run(debug=True)
