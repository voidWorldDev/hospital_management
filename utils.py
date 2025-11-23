from models import Appointment
import json
from datetime import datetime


def prevent_double_booking(doctor_id, appt_date, appt_time):
    existing = Appointment.query.filter_by(
        doctor_id=doctor_id, date=appt_date, time=appt_time
    ).first()
    return existing is not None


def doctor_is_available(doctor_profile, appt_date, appt_time):
    try:
        avail = json.loads(doctor_profile.availability or "{}")
        weekday = appt_date.strftime("%a").lower()[:3]  # e.g. 'mon'
        slots = avail.get(weekday, [])
        tstr = appt_time.strftime("%H:%M")
        return tstr in slots
    except (ValueError, TypeError, json.JSONDecodeError):
        return doctor_profile.is_active


def can_schedule(doctor_profile, appt_date, appt_time):
    """Check both availability and double-booking before scheduling."""
    if not doctor_is_available(doctor_profile, appt_date, appt_time):
        return False
    if prevent_double_booking(doctor_profile.id, appt_date, appt_time):
        return False
    return True
