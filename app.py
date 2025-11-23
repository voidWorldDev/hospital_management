import os
import secrets
from datetime import datetime
from flask import (
    Flask, render_template, redirect, url_for, flash, request, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, login_required,
    logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from utils import can_schedule

# ------------------ Flask App Config ------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = secrets.token_hex(32)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///hospital.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Profile Picture Upload
UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2 MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

db = SQLAlchemy(app)

# ------------------ Login Manager ------------------
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


# ------------------ Helper: File Check ------------------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ------------------ Models (Embedded) ------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, doctor, patient
    profile_pic = db.Column(db.String(150), default='default.jpg')
    name = db.Column(db.String(100), nullable=False)

    doctor = db.relationship('DoctorProfile', backref='user', uselist=False)
    patient = db.relationship('PatientProfile', backref='user', uselist=False)


class DoctorProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    specialization = db.Column(db.String(100), nullable=False)
    availability = db.Column(db.Text)  # JSON string
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True)


class PatientProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    contact = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    dob = db.Column(db.Date, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True)


class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient_profile.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor_profile.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), default='Booked')

    patient = db.relationship('PatientProfile', backref='appointments')
    doctor = db.relationship('DoctorProfile', backref='appointments')


class Treatment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointment.id'), nullable=False)
    diagnosis = db.Column(db.Text)
    prescription = db.Column(db.Text)
    notes = db.Column(db.Text)

    appointment = db.relationship('Appointment', backref='treatment')


# ------------------ User Loader ------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ------------------ Routes ------------------

@app.route("/")
def index():
    return redirect(url_for("login"))


# ------------------ Login / Logout ------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash("Logged in successfully!", "success")
            if user.role == 'admin':
                return redirect(url_for("admin_dashboard"))
            elif user.role == 'doctor':
                return redirect(url_for("doctor_dashboard"))
            else:
                return redirect(url_for("patient_dashboard"))
        else:
            flash("Invalid username or password", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


# ------------------ Settings (Profile Pic, Name, Password) ------------------
@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    user = current_user

    if request.method == "POST":
        action = request.form.get("action")

        # Upload Profile Picture
        if action == "upload_pic":
            if 'profile_pic' not in request.files:
                flash("No file part", "danger")
                return redirect(request.url)
            file = request.files['profile_pic']
            if file.filename == '':
                flash("No file selected", "danger")
                return redirect(request.url)
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                base, ext = os.path.splitext(filename)
                filename = f"{user.id}_{base}{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

                if user.profile_pic != 'default.jpg':
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], user.profile_pic)
                    if os.path.exists(old_path):
                        os.remove(old_path)

                user.profile_pic = filename
                db.session.commit()
                flash("Profile picture updated!", "success")
                return redirect(url_for('settings'))

        # Update Name
        elif action == "update_name":
            new_name = request.form.get("name", "").strip()
            if not new_name:
                flash("Name cannot be empty", "danger")
            elif len(new_name) > 100:
                flash("Name too long", "danger")
            else:
                user.name = new_name
                db.session.commit()
                flash("Name updated!", "success")
            return redirect(url_for('settings'))

        # Update Password
        elif action == "update_password":
            old = request.form.get("old_password")
            new = request.form.get("new_password")
            confirm = request.form.get("confirm_password")

            if not check_password_hash(user.password_hash, old):
                flash("Current password is incorrect", "danger")
            elif new != confirm:
                flash("New passwords do not match", "danger")
            elif len(new) < 6:
                flash("Password must be at least 6 characters", "danger")
            else:
                user.password_hash = generate_password_hash(new)
                db.session.commit()
                flash("Password changed successfully!", "success")
            return redirect(url_for('settings'))

    return render_template("settings.html", user=user)


# ------------------ Admin Dashboard ------------------
@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    if current_user.role != "admin":
        abort(403)
    doctors = DoctorProfile.query.all()
    patients = PatientProfile.query.all()
    appointments = Appointment.query.all()
    return render_template(
        "admin_dashboard.html",
        doctors=doctors,
        patients=patients,
        appointments=appointments
    )


# ------------------ Manage Doctors ------------------
@app.route("/admin/doctor/manage")
@login_required
def manage_doctors():
    if current_user.role != "admin":
        abort(403)
    doctors = DoctorProfile.query.all()
    return render_template("manage_doctors.html", doctors=doctors)


@app.route("/admin/doctor/add", methods=["GET", "POST"])
@login_required
def add_doctor():
    if current_user.role != "admin":
        abort(403)
    if request.method == "POST":
        name = request.form["name"]
        username = request.form["username"]
        password = request.form["password"]
        specialization = request.form["specialization"]
        availability = request.form.get("availability", "{}")

        # Create User
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role='doctor',
            name=name,
            profile_pic='default.jpg'
        )
        db.session.add(user)
        db.session.flush()

        # Create Doctor Profile
        doctor = DoctorProfile(
            specialization=specialization,
            availability=availability,
            user_id=user.id
        )
        db.session.add(doctor)
        db.session.commit()
        flash("Doctor added successfully!", "success")
        return redirect(url_for("manage_doctors"))
    return render_template("add_doctor.html")


@app.route("/admin/doctor/edit/<int:doctor_id>", methods=["GET", "POST"])
@login_required
def edit_doctor(doctor_id):
    if current_user.role != "admin":
        abort(403)
    doctor = DoctorProfile.query.get_or_404(doctor_id)
    if request.method == "POST":
        doctor.user.name = request.form["name"]
        doctor.specialization = request.form["specialization"]
        doctor.availability = request.form.get("availability", "{}")
        db.session.commit()
        flash("Doctor updated!", "success")
        return redirect(url_for("manage_doctors"))
    return render_template("edit_doctor.html", doctor=doctor)


@app.route("/admin/delete_doctor/<int:doctor_id>")
@login_required
def delete_doctor(doctor_id):
    if current_user.role != "admin":
        abort(403)
    doctor = DoctorProfile.query.get_or_404(doctor_id)
    user = doctor.user
    db.session.delete(doctor)
    db.session.delete(user)
    db.session.commit()
    flash("Doctor deleted!", "success")
    return redirect(url_for("manage_doctors"))


# ------------------ Manage Patients ------------------
@app.route("/admin/patients")
@login_required
def manage_patients():
    if current_user.role != "admin":
        abort(403)
    patients = PatientProfile.query.all()
    return render_template("manage_patients.html", patients=patients)


@app.route("/admin/patients/add", methods=["GET", "POST"])
@login_required
def add_patient():
    if current_user.role != "admin":
        abort(403)
    if request.method == "POST":
        name = request.form["name"]
        username = request.form["username"]
        password = request.form["password"]
        email = request.form["email"]
        contact = request.form["contact"]
        address = request.form["address"]
        dob_str = request.form["dob"]
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()

        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role='patient',
            name=name,
            profile_pic='default.jpg'
        )
        db.session.add(user)
        db.session.flush()

        patient = PatientProfile(
            email=email, contact=contact, address=address, dob=dob, user_id=user.id
        )
        db.session.add(patient)
        db.session.commit()
        flash("Patient added!", "success")
        return redirect(url_for("manage_patients"))
    return render_template("add_patient.html")


# ------------------ Manage Appointments ------------------
@app.route("/admin/manage_appointments")
@login_required
def manage_appointments():
    if current_user.role != "admin":
        abort(403)
    appointments = Appointment.query.all()
    doctors = DoctorProfile.query.all()
    patients = PatientProfile.query.all()
    return render_template(
        "manage_appointments.html",
        appointments=appointments, doctors=doctors, patients=patients
    )


@app.route("/admin/add_appointment", methods=["POST"])
@login_required
def add_appointment():
    if current_user.role != "admin":
        abort(403)
    doctor_id = request.form["doctor_id"]
    patient_id = request.form["patient_id"]
    date_str = request.form["date"]
    time_str = request.form["time"]

    appt_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    appt_time = datetime.strptime(time_str, "%H:%M").time()

    doctor = DoctorProfile.query.get(doctor_id)
    if not can_schedule(doctor, appt_date, appt_time):
        flash("Slot not available or already booked!", "danger")
        return redirect(url_for("manage_appointments"))

    appt = Appointment(
        doctor_id=doctor_id, patient_id=patient_id,
        date=appt_date, time=appt_time
    )
    db.session.add(appt)
    db.session.commit()
    flash("Appointment booked!", "success")
    return redirect(url_for("manage_appointments"))


# ------------------ Doctor Dashboard ------------------
@app.route("/doctor/dashboard")
@login_required
def doctor_dashboard():
    if current_user.role != "doctor":
        abort(403)
    doctor = current_user.doctor
    appointments = Appointment.query.filter_by(doctor_id=doctor.id).all()
    return render_template("doctor_dashboard.html", appointments=appointments, doctor=doctor)


@app.route("/doctor/complete/<int:appt_id>", methods=["GET", "POST"])
@login_required
def complete_appointment(appt_id):
    if current_user.role != "doctor":
        abort(403)
    appt = Appointment.query.get_or_404(appt_id)
    if appt.doctor_id != current_user.doctor.id:
        abort(403)

    if request.method == "POST":
        diagnosis = request.form["diagnosis"]
        prescription = request.form["prescription"]
        notes = request.form.get("notes", "")

        treatment = Treatment(
            appointment_id=appt.id,
            diagnosis=diagnosis,
            prescription=prescription,
            notes=notes
        )
        appt.status = "Completed"
        db.session.add(treatment)
        db.session.commit()
        flash("Treatment recorded!", "success")
        return redirect(url_for("doctor_dashboard"))

    return render_template("treatment_form.html", appt=appt)


# ------------------ Patient Dashboard ------------------
@app.route("/patient/dashboard")
@login_required
def patient_dashboard():
    if current_user.role != "patient":
        abort(403)
    patient = current_user.patient
    appointments = Appointment.query.filter_by(patient_id=patient.id).all()
    return render_template("patient_dashboard.html", appointments=appointments)


@app.route("/book_appointment", methods=["GET", "POST"])
@login_required
def book_appointment():
    if current_user.role != "patient":
        abort(403)
    doctors = DoctorProfile.query.all()
    if request.method == "POST":
        doctor_id = request.form["doctor_id"]
        date_str = request.form["date"]
        time_str = request.form["time"]

        appt_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        appt_time = datetime.strptime(time_str, "%H:%M").time()

        doctor = DoctorProfile.query.get(doctor_id)
        if not can_schedule(doctor, appt_date, appt_time):
            flash("Slot not available!", "danger")
            return redirect(url_for("book_appointment"))

        appt = Appointment(
            doctor_id=doctor_id,
            patient_id=current_user.patient.id,
            date=appt_date,
            time=appt_time
        )
        db.session.add(appt)
        db.session.commit()
        flash("Appointment booked!", "success")
        return redirect(url_for("patient_dashboard"))

    return render_template("book_appointment.html", doctors=doctors)


# ------------------ Run App ------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        # Create default admin
        if not User.query.filter_by(username="admin").first():
            admin = User(
                username="admin",
                password_hash=generate_password_hash("admin@123"),
                role="admin",
                name="Administrator",
                profile_pic="default.jpg"
            )
            db.session.add(admin)
            db.session.commit()
            print("Default admin created: username=admin, password=admin123")

    app.run(debug=True)
