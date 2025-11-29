import os
import secrets
from datetime import datetime, timedelta
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

# ------------------ App Configuration ------------------
app = Flask(__name__)
app.config.update(
    SECRET_KEY=secrets.token_hex(32),
    SQLALCHEMY_DATABASE_URI="sqlite:///hospital.db",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,  # 2 MB
    UPLOAD_FOLDER=os.path.join('static', 'uploads')
)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ------------------ Models ------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, doctor, patient
    name = db.Column(db.String(100), nullable=False)
    profile_pic = db.Column(db.String(150), default='default.jpg')
    doctor = db.relationship('DoctorProfile', backref='user', uselist=False)
    patient = db.relationship('PatientProfile', backref='user', uselist=False)


class DoctorProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    specialization = db.Column(db.String(100), nullable=False)
    availability = db.Column(db.Text, default='{}')  # JSON string
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
    status = db.Column(db.String(20), default='pending')
    patient = db.relationship('PatientProfile', backref='appointments')
    doctor = db.relationship('DoctorProfile', backref='appointments')


class Treatment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointment.id'), nullable=False)
    diagnosis = db.Column(db.Text)
    prescription = db.Column(db.Text)
    notes = db.Column(db.Text)
    appointment = db.relationship('Appointment', backref='treatment', uselist=False)


# ------------------ User Loader & Context ------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.context_processor
def inject_user():
    return dict(current_user=current_user, now=datetime.now())


# ------------------ Auth Routes (unchanged) ------------------
@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    # ... your existing register code (unchanged) ...
    # (I kept it exactly as you had it)
    if current_user.is_authenticated:
        return redirect(url_for(f"{current_user.role}_dashboard"))
    if request.method == "POST":
        name = request.form["name"].strip()
        username = request.form["username"].strip().lower()
        password = request.form["password"]
        role = request.form["role"]
        if role not in ["patient", "doctor"]:
            flash("Invalid role selected.", "danger")
            return redirect(url_for("register"))
        if User.query.filter_by(username=username).first():
            flash("Username already taken.", "danger")
            return redirect(url_for("register"))
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for("register"))
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role=role,
            name=name
        )
        db.session.add(user)
        db.session.flush()
        if role == "doctor":
            specialization = request.form.get("specialization", "").strip()
            if not specialization:
                flash("Specialization is required for doctors.", "danger")
                db.session.rollback()
                return redirect(url_for("register"))
            db.session.add(DoctorProfile(specialization=specialization, user_id=user.id))
        else:
            email = request.form["email"].strip()
            if PatientProfile.query.filter_by(email=email).first():
                flash("Email already registered.", "danger")
                db.session.rollback()
                return redirect(url_for("register"))
            try:
                dob = datetime.strptime(request.form["dob"], "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid date of birth.", "danger")
                db.session.rollback()
                return redirect(url_for("register"))
            db.session.add(PatientProfile(
                email=email,
                contact=request.form["contact"],
                address=request.form["address"],
                dob=dob,
                user_id=user.id
            ))
        db.session.commit()
        login_user(user)
        flash(f"Welcome, {name}! Account created successfully.", "success")
        return redirect(url_for(f"{role}_dashboard"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(f"{current_user.role}_dashboard"))
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()
        if user and check_password_hash(user.password_hash, request.form["password"]):
            login_user(user)
            flash("Logged in successfully!", "success")
            return redirect(url_for(f"{user.role}_dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


# ------------------ Settings (unchanged) ------------------
@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    # ... your existing settings code (unchanged) ...
    # (kept exactly as you wrote it)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "upload_pic" and 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                name_part, ext = os.path.splitext(filename)
                filename = f"{current_user.id}_{name_part}{ext}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                if current_user.profile_pic != 'default.jpg':
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], current_user.profile_pic)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                current_user.profile_pic = filename
                db.session.commit()
                flash("Profile picture updated!", "success")
        elif action == "update_name":
            new_name = request.form.get("name", "").strip()
            if new_name and len(new_name) <= 100:
                current_user.name = new_name
                db.session.commit()
                flash("Name updated!", "success")
            else:
                flash("Invalid name.", "danger")
        elif action == "update_password":
            old = request.form.get("old_password")
            new = request.form.get("new_password")
            confirm = request.form.get("confirm_password")
            if not check_password_hash(current_user.password_hash, old):
                flash("Current password incorrect.", "danger")
            elif new != confirm:
                flash("New passwords do not match.", "danger")
            elif len(new) < 6:
                flash("Password too short.", "danger")
            else:
                current_user.password_hash = generate_password_hash(new)
                db.session.commit()
                flash("Password changed successfully!", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html")
@app.route("/admin/appointment/edit/<int:appt_id>", methods=["GET", "POST"])
@login_required
def update_appointment(appt_id):
    if current_user.role != "admin":
        abort(403)
    
    appt = Appointment.query.get_or_404(appt_id)
    
    if request.method == "POST":
        try:
            new_date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
            new_time = datetime.strptime(request.form["time"], "%H:%M").time()
            new_status = request.form["status"]
            doctor_id = int(request.form["doctor_id"])
            patient_id = int(request.form["patient_id"])
        except (ValueError, KeyError):
            flash("Invalid form data.", "danger")
            return redirect(url_for("update_appointment", appt_id=appt_id))
        
        # Optional: check slot availability if date/time changed
        if (new_date != appt.date or new_time != appt.time or doctor_id != appt.doctor_id):
            conflict = Appointment.query.filter(
                Appointment.doctor_id == doctor_id,
                Appointment.date == new_date,
                Appointment.time == new_time,
                Appointment.id != appt_id  # exclude current appointment
            ).first()
            if conflict:
                flash("This time slot is already booked for the selected doctor.", "danger")
                return redirect(url_for("update_appointment", appt_id=appt_id))
        
        # Update fields
        appt.date = new_date
        appt.time = new_time
        appt.status = new_status
        appt.doctor_id = doctor_id
        appt.patient_id = patient_id
        
        db.session.commit()
        flash("Appointment updated successfully!", "success")
        return redirect(url_for("manage_appointments"))
    
    # GET request → show form
    doctors = DoctorProfile.query.all()
    patients = PatientProfile.query.all()
    return render_template(
        "edit_appointment.html",
        appt=appt,
        doctors=doctors,
        patients=patients
    )
@app.route("/admin/appointment/delete/<int:appt_id>")
@login_required
def delete_appointment(appt_id):
    if current_user.role != "admin":
        abort(403)
    
    appt = Appointment.query.get_or_404(appt_id)
    db.session.delete(appt)
    db.session.commit()
    flash("Appointment deleted.", "success")
    return redirect(url_for("manage_appointments"))
@app.route("/admin/delete_patient/<int:patient_id>")
@login_required
def delete_patient(patient_id):
    if current_user.role != "admin":
        abort(403)
    
    patient = PatientProfile.query.get_or_404(patient_id)
    user = patient.user
    
    # Optional: delete associated appointments?
    # Appointment.query.filter_by(patient_id=patient.id).delete()
    
    db.session.delete(patient)
    db.session.delete(user)
    db.session.commit()
    
    flash("Patient deleted successfully!", "success")
    return redirect(url_for("manage_patients"))
@app.route("/admin/patient/edit/<int:patient_id>", methods=["GET", "POST"])
@login_required
def edit_patient(patient_id):
    if current_user.role != "admin":
        abort(403)
    
    patient = PatientProfile.query.get_or_404(patient_id)
    
    if request.method == "POST":
        # Update User info
        patient.user.name = request.form["name"]
        patient.user.username = request.form["username"]
        
        # Optional: allow password change
        new_password = request.form.get("password")
        if new_password and len(new_password) >= 6:
            patient.user.password_hash = generate_password_hash(new_password)
        
        # Update PatientProfile fields
        patient.email = request.form["email"]
        patient.contact = request.form["contact"]
        patient.address = request.form["address"]
        try:
            patient.dob = datetime.strptime(request.form["dob"], "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date format.", "danger")
            return redirect(url_for("edit_patient", patient_id=patient_id))
        
        db.session.commit()
        flash("Patient updated successfully!", "success")
        return redirect(url_for("manage_patients"))
    
    return render_template("edit_patient.html", patient=patient)

@app.route("/doctor/dashboard")
@login_required
def doctor_dashboard():
    if current_user.role != "doctor":
        abort(403)
    appointments = Appointment.query.filter_by(doctor_id=current_user.doctor.id).all()
    return render_template("doctor_dashboard.html", appointments=appointments)

@app.route("/patient/dashboard", methods=["GET", "POST"])
@login_required
def patient_dashboard():
    # ... your existing patient dashboard (unchanged) ...
    if current_user.role != "patient":
        abort(403)
    appointments = Appointment.query.filter_by(patient_id=current_user.patient.id)\
        .order_by(Appointment.date, Appointment.time).all()
    doctors = DoctorProfile.query.all()
    tomorrow = (datetime.today() + timedelta(days=1)).date()
    if request.method == "POST":
        try:
            appt_date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
            appt_time = datetime.strptime(request.form["time"], "%H:%M").time()
            doctor_id = int(request.form["doctor_id"])
        except (ValueError, KeyError):
            flash("Invalid input.", "danger")
            return redirect(url_for("patient_dashboard"))
        if appt_date < datetime.today().date():
            flash("Cannot book past dates.", "danger")
        elif Appointment.query.filter_by(doctor_id=doctor_id, date=appt_date, time=appt_time).first():
            flash("This slot is already booked.", "danger")
        else:
            db.session.add(Appointment(
                patient_id=current_user.patient.id,
                doctor_id=doctor_id,
                date=appt_date,
                time=appt_time,
                status="pending"
            ))
            db.session.commit()
            flash("Appointment requested! Awaiting confirmation.", "success")
        return redirect(url_for("patient_dashboard"))
    return render_template(
        "patient_dashboard.html",
        appointments=appointments,
        doctors=doctors,
        tomorrow=tomorrow
    )
# ------------------ Dashboards (unchanged) ------------------
@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    if current_user.role != "admin":
        abort(403)
    return render_template(
        "admin_dashboard.html",
        doctors=DoctorProfile.query.all(),
        patients=PatientProfile.query.all(),
        appointments=Appointment.query.all()
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


# ------------------ Run App ------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username="admin").first():
            admin = User(
                username="admin",
                password_hash=generate_password_hash("admin123"),
                role="admin",
                name="Administrator"
            )
            db.session.add(admin)
            db.session.commit()
            print("Default admin created → username: admin | password: admin123")
    app.run(debug=True)
