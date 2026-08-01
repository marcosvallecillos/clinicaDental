from fastapi import APIRouter, Depends, HTTPException, Request, Form, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import os

from src.db import get_db
from src.models import Patient, Appointment, Conversation, ClinicSetting, AdminUser
from src.bot_engine import ChatbotEngine
from src.twilio_whatsapp import process_whatsapp_webhook, send_direct_whatsapp_message

router = APIRouter(prefix="/api")

# Instancia del motor
pdfs_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pdfs")
bot_engine = ChatbotEngine(pdfs_path)

# ==================== SCHEMAS PYDANTIC ====================
class PatientUpdateSchema(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None
    triage_level: Optional[str] = None
    notes: Optional[str] = None

class AppointmentCreateSchema(BaseModel):
    patient_id: int
    appointment_date: str # YYYY-MM-DD HH:MM
    service_type: str
    doctor_name: Optional[str] = "Por asignar"
    notes: Optional[str] = None

class AppointmentUpdateSchema(BaseModel):
    status: Optional[str] = None
    appointment_date: Optional[str] = None
    service_type: Optional[str] = None
    doctor_name: Optional[str] = None
    notes: Optional[str] = None

class AdminSendMessageSchema(BaseModel):
    patient_id: int
    message: str

class ClinicSettingUpdateSchema(BaseModel):
    settings: Dict[str, str]

# ==================== WEBHOOK TWILIO WHATSAPP ====================
@router.post("/webhooks/twilio")
async def twilio_whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """Webhook que recibe mensajes de WhatsApp desde Twilio."""
    form_data = await request.form()
    dict_data = dict(form_data)
    twiml_response = process_whatsapp_webhook(db, bot_engine, dict_data)
    return Response(content=twiml_response, media_type="text/xml")

# ==================== DASHBOARD STATS ====================
@router.get("/dashboard/stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    total_leads = db.query(Patient).count()
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = datetime.combine(date.today(), datetime.max.time())
    
    appointments_today = db.query(Appointment).filter(
        Appointment.appointment_date >= today_start,
        Appointment.appointment_date <= today_end
    ).count()

    pending_appointments = db.query(Appointment).filter(Appointment.status == "pending").count()
    total_messages = db.query(Conversation).count()
    
    red_urgencies = db.query(Patient).filter(Patient.triage_level == "RED").count()
    yellow_urgencies = db.query(Patient).filter(Patient.triage_level == "YELLOW").count()

    telegram_leads = db.query(Patient).filter(Patient.platform == "telegram").count()
    whatsapp_leads = db.query(Patient).filter(Patient.platform == "whatsapp").count()

    # Citas recientes
    recent_appts = db.query(Appointment).order_by(Appointment.created_at.desc()).limit(5).all()
    recent_appts_data = []
    for a in recent_appts:
        patient = db.query(Patient).filter(Patient.id == a.patient_id).first()
        recent_appts_data.append({
            "id": a.id,
            "patient_name": patient.full_name if patient else "Desconocido",
            "phone": patient.phone if patient else "-",
            "platform": patient.platform if patient else "-",
            "service_type": a.service_type,
            "appointment_date": a.appointment_date.strftime("%Y-%m-%d %H:%M"),
            "status": a.status
        })

    return {
        "total_leads": total_leads,
        "appointments_today": appointments_today,
        "pending_appointments": pending_appointments,
        "total_messages": total_messages,
        "red_urgencies": red_urgencies,
        "yellow_urgencies": yellow_urgencies,
        "telegram_leads": telegram_leads,
        "whatsapp_leads": whatsapp_leads,
        "recent_appointments": recent_appts_data
    }

# ==================== GESTIÓN DE PACIENTES / LEADS ====================
@router.get("/patients")
def list_patients(
    search: Optional[str] = None,
    platform: Optional[str] = None,
    status: Optional[str] = None,
    triage: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Patient)
    if search:
        query = query.filter(
            (Patient.full_name.ilike(f"%{search}%")) |
            (Patient.phone.ilike(f"%{search}%")) |
            (Patient.email.ilike(f"%{search}%"))
        )
    if platform:
        query = query.filter(Patient.platform == platform)
    if status:
        query = query.filter(Patient.status == status)
    if triage:
        query = query.filter(Patient.triage_level == triage)

    patients = query.order_by(Patient.updated_at.desc()).all()
    res = []
    for p in patients:
        res.append({
            "id": p.id,
            "full_name": p.full_name,
            "phone": p.phone or "Sin teléfono",
            "email": p.email or "Sin email",
            "platform": p.platform,
            "platform_id": p.platform_id,
            "status": p.status,
            "triage_level": p.triage_level,
            "notes": p.notes,
            "created_at": p.created_at.strftime("%Y-%m-%d %H:%M"),
            "updated_at": p.updated_at.strftime("%Y-%m-%d %H:%M")
        })
    return res

@router.put("/patients/{patient_id}")
def update_patient(patient_id: int, data: PatientUpdateSchema, db: Session = Depends(get_db)):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    if data.full_name is not None: p.full_name = data.full_name
    if data.phone is not None: p.phone = data.phone
    if data.email is not None: p.email = data.email
    if data.status is not None: p.status = data.status
    if data.triage_level is not None: p.triage_level = data.triage_level
    if data.notes is not None: p.notes = data.notes

    db.commit()
    return {"message": "Paciente actualizado correctamente", "patient_id": patient_id}

@router.delete("/patients/{patient_id}")
def delete_patient(patient_id: int, db: Session = Depends(get_db)):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    db.delete(p)
    db.commit()
    return {"message": "Paciente eliminado"}

# ==================== GESTIÓN DE CITAS ====================
@router.get("/appointments")
def list_appointments(db: Session = Depends(get_db)):
    appts = db.query(Appointment).order_by(Appointment.appointment_date.asc()).all()
    res = []
    for a in appts:
        p = db.query(Patient).filter(Patient.id == a.patient_id).first()
        res.append({
            "id": a.id,
            "patient_id": a.patient_id,
            "patient_name": p.full_name if p else "Desconocido",
            "patient_phone": p.phone if p else "-",
            "platform": p.platform if p else "-",
            "appointment_date": a.appointment_date.strftime("%Y-%m-%d %H:%M"),
            "service_type": a.service_type,
            "doctor_name": a.doctor_name,
            "status": a.status,
            "notes": a.notes
        })
    return res

@router.post("/appointments")
def create_appointment(data: AppointmentCreateSchema, db: Session = Depends(get_db)):
    p = db.query(Patient).filter(Patient.id == data.patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    try:
        dt = datetime.strptime(data.appointment_date, "%Y-%m-%d %H:%M")
    except ValueError:
        try:
            dt = datetime.strptime(data.appointment_date, "%Y-%m-%dT%H:%M")
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de fecha inválido. Usar YYYY-MM-DD HH:MM")

    appt = Appointment(
        patient_id=data.patient_id,
        appointment_date=dt,
        service_type=data.service_type,
        doctor_name=data.doctor_name or "Por asignar",
        status="pending",
        notes=data.notes
    )
    db.add(appt)
    p.status = "scheduled"
    db.commit()

    return {"message": "Cita creada con éxito", "appointment_id": appt.id}

@router.put("/appointments/{appointment_id}")
def update_appointment(appointment_id: int, data: AppointmentUpdateSchema, db: Session = Depends(get_db)):
    a = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    if data.status: a.status = data.status
    if data.service_type: a.service_type = data.service_type
    if data.doctor_name: a.doctor_name = data.doctor_name
    if data.notes: a.notes = data.notes
    if data.appointment_date:
        try:
            a.appointment_date = datetime.strptime(data.appointment_date, "%Y-%m-%d %H:%M")
        except:
            pass

    db.commit()
    return {"message": "Cita actualizada correctamente"}

@router.delete("/appointments/{appointment_id}")
def delete_appointment(appointment_id: int, db: Session = Depends(get_db)):
    a = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    db.delete(a)
    db.commit()
    return {"message": "Cita eliminada"}

# ==================== MONITOR DE CONVERSACIONES ====================
@router.get("/conversations/patient/{patient_id}")
def get_patient_conversations(patient_id: int, db: Session = Depends(get_db)):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    convs = db.query(Conversation).filter(Conversation.patient_id == patient_id).order_by(Conversation.timestamp.asc()).all()
    res = []
    for c in convs:
        res.append({
            "id": c.id,
            "sender": c.sender,
            "message": c.message,
            "triage_code": c.triage_code,
            "timestamp": c.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        })

    return {
        "patient": {
            "id": p.id,
            "full_name": p.full_name,
            "phone": p.phone,
            "platform": p.platform,
            "platform_id": p.platform_id,
            "triage_level": p.triage_level
        },
        "conversations": res
    }

@router.post("/conversations/send")
def admin_send_message(data: AdminSendMessageSchema, db: Session = Depends(get_db)):
    """Permite al Administrador intervención humana directa escribiendo al paciente."""
    p = db.query(Patient).filter(Patient.id == data.patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    # Registrar mensaje del admin
    bot_engine.record_message(db, p.id, p.platform, "admin", data.message)

    sent = False
    if p.platform == "whatsapp":
        sent = send_direct_whatsapp_message(p.platform_id, data.message)
    elif p.platform == "telegram":
        # Enviar via Telegram Bot API si está disponible
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if token and token != "TU_TELEGRAM_BOT_TOKEN_AQUI":
            try:
                import requests
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                resp = requests.post(url, json={"chat_id": p.platform_id, "text": f"💬 *[Mensaje de la Clínica]*:\n{data.message}", "parse_mode": "Markdown"})
                sent = resp.status_code == 200
            except Exception as e:
                print(f"Error enviando Telegram desde Admin: {e}")

    return {"message": "Mensaje enviado y registrado en el historial", "delivered": sent}

# ==================== CONFIGURACIÓN Y CONOCIMIENTO ====================
@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    settings = db.query(ClinicSetting).all()
    return {s.setting_key: s.setting_value for s in settings}

@router.post("/settings")
def save_settings(data: ClinicSettingUpdateSchema, db: Session = Depends(get_db)):
    for key, val in data.settings.items():
        existing = db.query(ClinicSetting).filter(ClinicSetting.setting_key == key).first()
        if existing:
            existing.setting_value = val
        else:
            db.add(ClinicSetting(setting_key=key, setting_value=val))
    db.commit()
    return {"message": "Configuración guardada correctamente"}

@router.get("/knowledge/files")
def get_knowledge_files():
    summary = bot_engine.loader.get_summary()
    return summary
