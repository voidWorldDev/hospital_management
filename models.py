# models.py
from extensions import db
from flask_login import UserMixin
from datetime import date
import os
from werkzeug.utils import secure_filename

# ------------------------------------------------------------------
#  USER – now holds profile picture, full name and hashed password
# ------------------------------------------------------------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)   # hashed
    role = db.Column(db.String(20), nullable=False)            # admin, doctor, patient
    profile_pic = db.Column(db.String(150), default='default.jpg')
    name = db.Column(db.String(100), nullable=False)           # display name

    # relationships
    doctor = db.relationship('DoctorProfile', backref='user', uselist=False)
    patient = db.relationship('PatientProfile', backref='user', uselist=False)


# ------------------------------------------------------------------
#  DOCTOR PROFILE
# ------------------------------------------------------------------
class DoctorProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    specialization = db.Column(db.String(100), nullable=False)
    availability = db.Column(db.Text)          # JSON string or separate table
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True)


# ------------------------------------------------------------------
#  PATIENT PROFILE
# ------------------------------------------------------------------
class PatientProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    contact = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    dob = db.Column(db.Date, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True)


# ------------------------------------------------------------------
#  APPOINTMENT & TREATMENT (unchanged – only for context)
# ------------------------------------------------------------------
class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient_profile.id'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor_profile.id'))
    date = db.Column(db.Date)
    time = db.Column(db.Time)
    status = db.Column(db.String(20), default='Booked')


class Treatment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointment.id'))
    diagnosis = db.Column(db.Text)
    prescription = db.Column(db.Text)
    notes = db.Column(db.Text)
