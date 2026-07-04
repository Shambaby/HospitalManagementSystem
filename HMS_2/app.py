from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = 'Shambhavi123'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

#Create a folder for whenever the user uploads a prescription or report
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

#Create subfolder for reports
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'reports'), exist_ok=True)

#Create subfolder for prescriptions
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'prescriptions'), exist_ok=True)
ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

#Initializing DB
def init_db():
    conn = sqlite3.connect('hospital.db')
    c = conn.cursor()
    
    #Users Table: purpose is authentication of a new/old user while signing up or logging in
    c.execute('''CREATE TABLE IF NOT EXISTS Users (
        User_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Username TEXT UNIQUE NOT NULL,
        Password TEXT NOT NULL,
        Role TEXT NOT NULL CHECK(Role IN ('admin', 'doctor', 'patient')),
        Reference_ID INTEGER
    )''')
    
    #Employees Table: purpose is to keep salary, department, etc. all details about all employees
    c.execute('''CREATE TABLE IF NOT EXISTS Employees (
        Employee_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Department_ID INTEGER,
        Designation TEXT,
        Full_Name TEXT NOT NULL,
        Salary REAL,
        DOB DATE,
        Gender TEXT CHECK(Gender IN ('M', 'F')),
        Phone_Number TEXT
    )''')
    
    #Doctors Table: will be used when showing users the list of available doctors while booking appointment
    c.execute('''CREATE TABLE IF NOT EXISTS Doctors (
        Doctor_ID INTEGER PRIMARY KEY,
        Specialization TEXT,
        Years_of_Experience INTEGER,
        Consultation_Fee REAL,
        FOREIGN KEY (Doctor_ID) REFERENCES Employees(Employee_ID)
    )''')
    
    #Patients table: to keep track of patients
    c.execute('''CREATE TABLE IF NOT EXISTS Patients (
        Patient_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Full_Name TEXT NOT NULL,
        Phone_Number TEXT,
        DOB DATE,
        Gender TEXT CHECK(Gender IN ('M', 'F')),
        Address TEXT
    )''')
    
    #Slots Table: to show the user the available slots for every doctor
    c.execute('''CREATE TABLE IF NOT EXISTS Slots (
        Slot_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Doctor_ID INTEGER,
        Time TEXT,
        Date DATE,
        is_booked INTEGER DEFAULT 0,
        FOREIGN KEY (Doctor_ID) REFERENCES Doctors(Doctor_ID)
    )''')
    
    #Appointments Table: to store all appointments
    c.execute('''CREATE TABLE IF NOT EXISTS Appointments (
        Appointment_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Patient_ID INTEGER,
        Doctor_ID INTEGER,
        Date DATE,
        Slot_ID INTEGER,
        is_booked INTEGER DEFAULT 1,
        Status TEXT DEFAULT 'scheduled' CHECK(Status IN ('scheduled', 'completed', 'cancelled')),
        FOREIGN KEY (Patient_ID) REFERENCES Patients(Patient_ID),
        FOREIGN KEY (Doctor_ID) REFERENCES Doctors(Doctor_ID),
        FOREIGN KEY (Slot_ID) REFERENCES Slots(Slot_ID)
    )''')
    
    #Diagnoses Table: to store all diagnoses, and to show a user their report
    c.execute('''CREATE TABLE IF NOT EXISTS Diagnoses (
        Diagnosis_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Patient_ID INTEGER,
        Doctor_ID INTEGER,
        Appointment_ID INTEGER,
        Diagnosis TEXT,
        Prescription_Path TEXT,
        Report_Path TEXT,
        Date DATE,
        FOREIGN KEY (Patient_ID) REFERENCES Patients(Patient_ID),
        FOREIGN KEY (Doctor_ID) REFERENCES Doctors(Doctor_ID),
        FOREIGN KEY (Appointment_ID) REFERENCES Appointments(Appointment_ID)
    )''')
    
    #Payments Table
    c.execute('''CREATE TABLE IF NOT EXISTS Payments (
        Payment_ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Appointment_ID INTEGER,
        Patient_ID INTEGER,
        Payment_Amount REAL,
        Payment_Date DATE,
        FOREIGN KEY (Appointment_ID) REFERENCES Appointments(Appointment_ID),
        FOREIGN KEY (Patient_ID) REFERENCES Patients(Patient_ID)
    )''')
    
    #Create default admin user, to initially login
    c.execute("SELECT * FROM Users WHERE Username='admin'")
    if not c.fetchone():
        admin_password = generate_password_hash('admin123')
        c.execute("INSERT INTO Users (Username, Password, Role, Reference_ID) VALUES (?, ?, ?, ?)",
                  ('admin', admin_password, 'admin', 0))
    
    #Create time slots (9AM- 11PM)
    time_slots = []
    for hour in range(9, 23):
        start = f"{hour:02d}:00"
        end = f"{(hour+1):02d}:00"
        time_slots.append(f"{start}-{end}")
    
    conn.commit()
    conn.close()

   #Login required decorator
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

#Helper fn to get database connection
def get_db():
    conn = sqlite3.connect('hospital.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db()
        user = conn.execute('SELECT * FROM Users WHERE Username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['Password'], password):
            session['user_id'] = user['User_ID']
            session['username'] = user['Username']
            session['role'] = user['Role']
            session['reference_id'] = user['Reference_ID']
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        full_name = request.form['full_name']
        phone = request.form['phone']
        dob = request.form['dob']
        gender = request.form['gender']
        address = request.form['address']
        
        conn = get_db()
        
        #Check if username exists
        existing = conn.execute('SELECT * FROM Users WHERE Username = ?', (username,)).fetchone()
        if existing:
            flash('Username already exists', 'danger')
            return redirect(url_for('register'))
        
        #Create patient record
        conn.execute('INSERT INTO Patients (Full_Name, Phone_Number, DOB, Gender, Address) VALUES (?, ?, ?, ?, ?)',
                     (full_name, phone, dob, gender, address))
        patient_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        
        #Create user account
        hashed_password = generate_password_hash(password)
        conn.execute('INSERT INTO Users (Username, Password, Role, Reference_ID) VALUES (?, ?, ?, ?)',
                     (username, hashed_password, 'patient', patient_id))
        
        conn.commit()
        conn.close()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required()
def dashboard():
    role = session.get('role')
    if role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif role == 'doctor':
        return redirect(url_for('doctor_dashboard'))
    elif role == 'patient':
        return redirect(url_for('patient_dashboard'))

#ADMIN ROUTES
@app.route('/admin/dashboard')
@login_required('admin')
def admin_dashboard():
    conn = get_db()
    
    total_doctors = conn.execute('SELECT COUNT(*) as count FROM Doctors').fetchone()['count']
    total_patients = conn.execute('SELECT COUNT(*) as count FROM Patients').fetchone()['count']
    total_appointments = conn.execute('SELECT COUNT(*) as count FROM Appointments WHERE Status="scheduled"').fetchone()['count']
    
    conn.close()
    
    return render_template('admin/dashboard.html', 
                           total_doctors=total_doctors,
                           total_patients=total_patients,
                           total_appointments=total_appointments)

@app.route('/admin/doctors')
@login_required('admin')
def admin_doctors():
    conn = get_db()
    doctors = conn.execute('''
        SELECT d.Doctor_ID, e.Full_Name, e.Department_ID, d.Specialization, 
               d.Years_of_Experience, d.Consultation_Fee, e.Phone_Number
        FROM Doctors d
        JOIN Employees e ON d.Doctor_ID = e.Employee_ID
    ''').fetchall()
    conn.close()
    
    return render_template('admin/doctors.html', doctors=doctors)

@app.route('/admin/doctor/add', methods=['GET', 'POST'])
@login_required('admin')
def admin_add_doctor():
    if request.method == 'POST':
        full_name = request.form['full_name']
        department = request.form['department']
        designation = 'Doctor'
        specialization = request.form['specialization']
        experience = request.form['experience']
        fee = request.form['fee']
        salary = request.form['salary']
        dob = request.form['dob']
        gender = request.form['gender']
        phone = request.form['phone']
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db()
        
        #Check if username exists
        existing = conn.execute('SELECT * FROM Users WHERE Username = ?', (username,)).fetchone()
        if existing:
            flash('Username already exists', 'danger')
            return redirect(url_for('admin_add_doctor'))
        
        #Create employee record
        conn.execute('''INSERT INTO Employees 
                        (Department_ID, Designation, Full_Name, Salary, DOB, Gender, Phone_Number)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                     (department, designation, full_name, salary, dob, gender, phone))
        employee_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        
        #Create doctor record
        conn.execute('''INSERT INTO Doctors 
                        (Doctor_ID, Specialization, Years_of_Experience, Consultation_Fee)
                        VALUES (?, ?, ?, ?)''',
                     (employee_id, specialization, experience, fee))
        
        #Create user account
        hashed_password = generate_password_hash(password)
        conn.execute('INSERT INTO Users (Username, Password, Role, Reference_ID) VALUES (?, ?, ?, ?)',
                     (username, hashed_password, 'doctor', employee_id))
        
        #Create slots for next 30 days
        time_slots = []
        for hour in range(9, 23):
            time_slots.append(f"{hour:02d}:00-{(hour+1):02d}:00")
        
        for day_offset in range(30):
            date = (datetime.now() + timedelta(days=day_offset)).strftime('%Y-%m-%d')
            for time_slot in time_slots:
                conn.execute('INSERT INTO Slots (Doctor_ID, Time, Date, is_booked) VALUES (?, ?, ?, ?)',
                             (employee_id, time_slot, date, 0))
        
        conn.commit()
        conn.close()
        
        flash('Doctor added successfully!', 'success')
        return redirect(url_for('admin_doctors'))
    
    return render_template('admin/add_doctor.html')

@app.route('/admin/doctor/edit/<int:doctor_id>', methods=['GET', 'POST'])
@login_required('admin')
def admin_edit_doctor(doctor_id):
    conn = get_db()
    
    if request.method == 'POST':
        full_name = request.form['full_name']
        department = request.form['department']
        specialization = request.form['specialization']
        experience = request.form['experience']
        fee = request.form['fee']
        salary = request.form['salary']
        phone = request.form['phone']
        
        conn.execute('''UPDATE Employees 
                        SET Department_ID=?, Full_Name=?, Salary=?, Phone_Number=?
                        WHERE Employee_ID=?''',
                     (department, full_name, salary, phone, doctor_id))
        
        conn.execute('''UPDATE Doctors 
                        SET Specialization=?, Years_of_Experience=?, Consultation_Fee=?
                        WHERE Doctor_ID=?''',
                     (specialization, experience, fee, doctor_id))
        
        conn.commit()
        conn.close()
        
        flash('Doctor updated successfully!', 'success')
        return redirect(url_for('admin_doctors'))
    
    doctor = conn.execute('''
        SELECT d.Doctor_ID, e.Full_Name, e.Department_ID, d.Specialization, 
               d.Years_of_Experience, d.Consultation_Fee, e.Phone_Number, e.Salary
        FROM Doctors d
        JOIN Employees e ON d.Doctor_ID = e.Employee_ID
        WHERE d.Doctor_ID = ?
    ''', (doctor_id,)).fetchone()
    
    conn.close()
    
    return render_template('admin/edit_doctor.html', doctor=doctor)

@app.route('/admin/doctor/delete/<int:doctor_id>')
@login_required('admin')
def admin_delete_doctor(doctor_id):
    conn = get_db()
    conn.execute('DELETE FROM Users WHERE Reference_ID = ? AND Role = "doctor"', (doctor_id,))
    conn.execute('DELETE FROM Slots WHERE Doctor_ID = ?', (doctor_id,))
    conn.execute('DELETE FROM Doctors WHERE Doctor_ID = ?', (doctor_id,))
    conn.execute('DELETE FROM Employees WHERE Employee_ID = ?', (doctor_id,))
    conn.commit()
    conn.close()
    
    flash('Doctor deleted successfully!', 'success')
    return redirect(url_for('admin_doctors'))

@app.route('/admin/appointments')
@login_required('admin')
def admin_appointments():
    conn = get_db()
    appointments = conn.execute('''
        SELECT a.Appointment_ID, p.Full_Name as Patient_Name, e.Full_Name as Doctor_Name,
               d.Specialization, a.Date, s.Time, a.Status
        FROM Appointments a
        JOIN Patients p ON a.Patient_ID = p.Patient_ID
        JOIN Doctors d ON a.Doctor_ID = d.Doctor_ID
        JOIN Employees e ON d.Doctor_ID = e.Employee_ID
        JOIN Slots s ON a.Slot_ID = s.Slot_ID
        ORDER BY a.Date DESC, s.Time DESC
    ''').fetchall()
    conn.close()
    
    return render_template('admin/appointments.html', appointments=appointments)

@app.route('/admin/search', methods=['GET', 'POST'])
@login_required('admin')
def admin_search():
    results = {'patients': [], 'doctors': []}
    
    if request.method == 'POST':
        search_type = request.form['search_type']
        search_term = request.form['search_term']
        
        conn = get_db()
        
        if search_type == 'patient':
            results['patients'] = conn.execute('''
                SELECT Patient_ID, Full_Name, Phone_Number
                FROM Patients
                WHERE Full_Name LIKE ?
            ''', (f'%{search_term}%',)).fetchall()
        
        elif search_type == 'doctor':
            results['doctors'] = conn.execute('''
                SELECT d.Doctor_ID, e.Full_Name, d.Specialization, e.Phone_Number
                FROM Doctors d
                JOIN Employees e ON d.Doctor_ID = e.Employee_ID
                WHERE e.Full_Name LIKE ? OR d.Specialization LIKE ?
            ''', (f'%{search_term}%', f'%{search_term}%')).fetchall()
        
        conn.close()
    
    return render_template('admin/search.html', results=results)

#Routes for everything doctor will access
@app.route('/doctor/dashboard')
@login_required('doctor')
def doctor_dashboard():
    doctor_id = session.get('reference_id')
    conn = get_db()
    
    appointments = conn.execute('''
        SELECT a.Appointment_ID, p.Full_Name as Patient_Name, p.Patient_ID,
               a.Date, s.Time, a.Status
        FROM Appointments a
        JOIN Patients p ON a.Patient_ID = p.Patient_ID
        JOIN Slots s ON a.Slot_ID = s.Slot_ID
        WHERE a.Doctor_ID = ? AND a.Status = "scheduled"
        ORDER BY a.Date, s.Time
    ''', (doctor_id,)).fetchall()
    
    conn.close()
    
    return render_template('doctor/dashboard.html', appointments=appointments)
#appointments viewed by doctor
@app.route('/doctor/appointments')
@login_required('doctor')
def doctor_appointments():
    doctor_id = session.get('reference_id')
    conn = get_db()
    
    appointments = conn.execute('''
        SELECT a.Appointment_ID, p.Full_Name as Patient_Name, p.Patient_ID,
               a.Date, s.Time, a.Status
        FROM Appointments a
        JOIN Patients p ON a.Patient_ID = p.Patient_ID
        JOIN Slots s ON a.Slot_ID = s.Slot_ID
        WHERE a.Doctor_ID = ?
        ORDER BY a.Date DESC, s.Time DESC
    ''', (doctor_id,)).fetchall()
    
    conn.close()
    
    return render_template('doctor/appointments.html', appointments=appointments)

@app.route('/doctor/complete_appointment/<int:appointment_id>', methods=['GET', 'POST'])
@login_required('doctor')
def doctor_complete_appointment(appointment_id):
    doctor_id = session.get('reference_id')
    conn = get_db()
    
    if request.method == 'POST':
        diagnosis = request.form['diagnosis']
        prescription_file = request.files.get('prescription')
        report_file = request.files.get('report')
        
        prescription_path = None
        report_path = None
        
        if prescription_file and allowed_file(prescription_file.filename):
            filename = secure_filename(f"prescription_{appointment_id}_{prescription_file.filename}")
            prescription_path = os.path.join('prescriptions', filename)
            prescription_file.save(os.path.join(app.config['UPLOAD_FOLDER'], prescription_path))
        
        if report_file and allowed_file(report_file.filename):
            filename = secure_filename(f"report_{appointment_id}_{report_file.filename}")
            report_path = os.path.join('reports', filename)
            report_file.save(os.path.join(app.config['UPLOAD_FOLDER'], report_path))
        
        appointment = conn.execute('SELECT Patient_ID, Slot_ID FROM Appointments WHERE Appointment_ID = ?', 
                                    (appointment_id,)).fetchone()
        
        conn.execute('''INSERT INTO Diagnoses 
                        (Patient_ID, Doctor_ID, Appointment_ID, Diagnosis, Prescription_Path, Report_Path, Date)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                     (appointment['Patient_ID'], doctor_id, appointment_id, diagnosis, 
                      prescription_path, report_path, datetime.now().strftime('%Y-%m-%d')))
        
        conn.execute('UPDATE Appointments SET Status = "completed", is_booked = 0 WHERE Appointment_ID = ?', 
                     (appointment_id,))
        conn.execute('UPDATE Slots SET is_booked = 0 WHERE Slot_ID = ?', (appointment['Slot_ID'],))
        
        conn.commit()
        conn.close()
        
        flash('Appointment completed successfully!', 'success')
        return redirect(url_for('doctor_appointments'))
    
    appointment = conn.execute('''
        SELECT a.Appointment_ID, p.Full_Name as Patient_Name, p.Patient_ID,
               a.Date, s.Time
        FROM Appointments a
        JOIN Patients p ON a.Patient_ID = p.Patient_ID
        JOIN Slots s ON a.Slot_ID = s.Slot_ID
        WHERE a.Appointment_ID = ? AND a.Doctor_ID = ?
    ''', (appointment_id, doctor_id)).fetchone()
    
    conn.close()
    
    return render_template('doctor/complete_appointment.html', appointment=appointment)
#patient history viewed by doctor
@app.route('/doctor/patient_history/<int:patient_id>')
@login_required('doctor')
def doctor_patient_history(patient_id):
    conn = get_db()
    
    patient = conn.execute('SELECT * FROM Patients WHERE Patient_ID = ?', (patient_id,)).fetchone()
    
    history = conn.execute('''
        SELECT d.Diagnosis, d.Date, e.Full_Name as Doctor_Name, doc.Specialization,
               d.Prescription_Path, d.Report_Path
        FROM Diagnoses d
        JOIN Doctors doc ON d.Doctor_ID = doc.Doctor_ID
        JOIN Employees e ON doc.Doctor_ID = e.Employee_ID
        WHERE d.Patient_ID = ?
        ORDER BY d.Date DESC
    ''', (patient_id,)).fetchall()
    
    conn.close()
    
    return render_template('doctor/patient_history.html', patient=patient, history=history)

#routes for patient's access
@app.route('/patient/dashboard')
@login_required('patient')
def patient_dashboard():
    patient_id = session.get('reference_id')
    conn = get_db()
    
    patient = conn.execute('SELECT * FROM Patients WHERE Patient_ID = ?', (patient_id,)).fetchone()
    
    upcoming_appointments = conn.execute('''
        SELECT a.Appointment_ID, e.Full_Name as Doctor_Name, d.Specialization,
               a.Date, s.Time, a.Status
        FROM Appointments a
        JOIN Doctors d ON a.Doctor_ID = d.Doctor_ID
        JOIN Employees e ON d.Doctor_ID = e.Employee_ID
        JOIN Slots s ON a.Slot_ID = s.Slot_ID
        WHERE a.Patient_ID = ? AND a.Status = "scheduled"
        ORDER BY a.Date, s.Time
        LIMIT 5
    ''', (patient_id,)).fetchall()
    
    conn.close()
    
    return render_template('patient/dashboard.html', patient=patient, appointments=upcoming_appointments)

@app.route('/patient/search_doctors', methods=['GET', 'POST'])
@login_required('patient')
def patient_search_doctors():
    doctors = []
    
    if request.method == 'POST':
        specialization = request.form.get('specialization', '')
        
        conn = get_db()
        
        if specialization:
            doctors = conn.execute('''
                SELECT d.Doctor_ID, e.Full_Name, d.Specialization, 
                       d.Years_of_Experience, d.Consultation_Fee
                FROM Doctors d
                JOIN Employees e ON d.Doctor_ID = e.Employee_ID
                WHERE d.Specialization LIKE ?
            ''', (f'%{specialization}%',)).fetchall()
        else:
            doctors = conn.execute('''
                SELECT d.Doctor_ID, e.Full_Name, d.Specialization, 
                       d.Years_of_Experience, d.Consultation_Fee
                FROM Doctors d
                JOIN Employees e ON d.Doctor_ID = e.Employee_ID
            ''').fetchall()
        
        conn.close()
    
    return render_template('patient/search_doctors.html', doctors=doctors)

@app.route('/patient/book_appointment/<int:doctor_id>', methods=['GET', 'POST'])
@login_required('patient')
def patient_book_appointment(doctor_id):
    patient_id = session.get('reference_id')
    conn = get_db()
    
    if request.method == 'POST':
        slot_id = request.form['slot_id']
        
        #check if slot is available
        slot = conn.execute('SELECT * FROM Slots WHERE Slot_ID = ? AND is_booked = 0', (slot_id,)).fetchone()
        
        if not slot:
            flash('This slot is no longer available. Please choose another slot.', 'warning')
            return redirect(url_for('patient_book_appointment', doctor_id=doctor_id))
        
        #add appointment
        conn.execute('''INSERT INTO Appointments 
                        (Patient_ID, Doctor_ID, Date, Slot_ID, is_booked, Status)
                        VALUES (?, ?, ?, ?, 1, "scheduled")''',
                     (patient_id, doctor_id, slot['Date'], slot_id))
        
        appointment_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        
        #update slot
        conn.execute('UPDATE Slots SET is_booked = 1 WHERE Slot_ID = ?', (slot_id,))
        
        #create payment record
        doctor = conn.execute('SELECT Consultation_Fee FROM Doctors WHERE Doctor_ID = ?', (doctor_id,)).fetchone()
        conn.execute('''INSERT INTO Payments 
                        (Appointment_ID, Patient_ID, Payment_Amount, Payment_Date)
                        VALUES (?, ?, ?, ?)''',
                     (appointment_id, patient_id, doctor['Consultation_Fee'], datetime.now().strftime('%Y-%m-%d')))
        
        conn.commit()
        conn.close()
        
        flash('Appointment booked successfully!', 'success')
        return redirect(url_for('patient_appointments'))
    
    #Get doctors info
    doctor = conn.execute('''
        SELECT d.Doctor_ID, e.Full_Name, d.Specialization, d.Consultation_Fee
        FROM Doctors d
        JOIN Employees e ON d.Doctor_ID = e.Employee_ID
        WHERE d.Doctor_ID = ?
    ''', (doctor_id,)).fetchone()
    
    #Get available slots for next 7 days
    today = datetime.now().strftime('%Y-%m-%d')
    end_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
    
    available_slots = conn.execute('''
        SELECT Slot_ID, Date, Time
        FROM Slots
        WHERE Doctor_ID = ? AND Date BETWEEN ? AND ? AND is_booked = 0
        ORDER BY Date, Time
    ''', (doctor_id, today, end_date)).fetchall()
    
    conn.close()
    
    return render_template('patient/book_appointment.html', doctor=doctor, slots=available_slots)

@app.route('/patient/appointments')
@login_required('patient')
def patient_appointments():
    patient_id = session.get('reference_id')
    conn = get_db()
    
    appointments = conn.execute('''
        SELECT a.Appointment_ID, e.Full_Name as Doctor_Name, d.Specialization,
               a.Date, s.Time, a.Status, d.Consultation_Fee
        FROM Appointments a
        JOIN Doctors d ON a.Doctor_ID = d.Doctor_ID
        JOIN Employees e ON d.Doctor_ID = e.Employee_ID
        JOIN Slots s ON a.Slot_ID = s.Slot_ID
        WHERE a.Patient_ID = ?
        ORDER BY a.Date DESC, s.Time DESC
    ''', (patient_id,)).fetchall()
    
    conn.close()
    
    return render_template('patient/appointments.html', appointments=appointments)

@app.route('/patient/cancel_appointment/<int:appointment_id>')
@login_required('patient')
def patient_cancel_appointment(appointment_id):
    patient_id = session.get('reference_id')
    conn = get_db()
    
    appointment = conn.execute('SELECT Slot_ID FROM Appointments WHERE Appointment_ID = ? AND Patient_ID = ?', 
                                (appointment_id, patient_id)).fetchone()
    
    if appointment:
        conn.execute('UPDATE Appointments SET Status = "cancelled", is_booked = 0 WHERE Appointment_ID = ?', 
                     (appointment_id,))
        conn.execute('UPDATE Slots SET is_booked = 0 WHERE Slot_ID = ?', (appointment['Slot_ID'],))
        conn.commit()
        flash('Appointment cancelled successfully!', 'success')
    else:
        flash('Appointment not found.', 'danger')
    
    conn.close()
    
    return redirect(url_for('patient_appointments'))

@app.route('/patient/medical_history')
@login_required('patient')
def patient_medical_history():
    patient_id = session.get('reference_id')
    conn = get_db()
    
    history = conn.execute('''
        SELECT d.Diagnosis, d.Date, e.Full_Name as Doctor_Name, doc.Specialization,
               d.Prescription_Path, d.Report_Path
        FROM Diagnoses d
        JOIN Doctors doc ON d.Doctor_ID = doc.Doctor_ID
        JOIN Employees e ON doc.Doctor_ID = e.Employee_ID
        WHERE d.Patient_ID = ?
        ORDER BY d.Date DESC
    ''', (patient_id,)).fetchall()
    
    conn.close()
    
    return render_template('patient/medical_history.html', history=history)

@app.route('/patient/profile', methods=['GET', 'POST'])
@login_required('patient')
def patient_profile():
    patient_id = session.get('reference_id')
    conn = get_db()
    
    if request.method == 'POST':
        full_name = request.form['full_name']
        phone = request.form['phone']
        address = request.form['address']
        
        conn.execute('''UPDATE Patients 
                        SET Full_Name=?, Phone_Number=?, Address=?
                        WHERE Patient_ID=?''',
                     (full_name, phone, address, patient_id))
        conn.commit()
        flash('Profile updated successfully!', 'success')
    
    patient = conn.execute('SELECT * FROM Patients WHERE Patient_ID = ?', (patient_id,)).fetchone()
    conn.close()
    
    return render_template('patient/profile.html', patient=patient)

@app.route('/uploads/<path:filename>')
@login_required()
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)