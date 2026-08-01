from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import enum

Base = declarative_base()

class PlatformEnum(str, enum.Enum):
    telegram = "telegram"
    whatsapp = "whatsapp"

class PatientStatusEnum(str, enum.Enum):
    new = "new"
    contacted = "contacted"
    scheduled = "scheduled"
    converted = "converted"
    lost = "lost"

class TriageLevelEnum(str, enum.Enum):
    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"

class AppointmentStatusEnum(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    completed = "completed"
    cancelled = "cancelled"

class SenderEnum(str, enum.Enum):
    user = "user"
    bot = "bot"
    admin = "admin"

class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    full_name = Column(String(150), nullable=True)
    phone = Column(String(50), nullable=True, index=True)
    email = Column(String(100), nullable=True)
    platform = Column(String(20), default="telegram", nullable=False)
    platform_id = Column(String(100), unique=True, nullable=False, index=True)
    status = Column(String(20), default="new", index=True)
    triage_level = Column(String(20), default="GREEN")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    appointments = relationship("Appointment", back_populates="patient", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="patient", cascade="all, delete-orphan")

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    appointment_date = Column(DateTime, nullable=False, index=True)
    service_type = Column(String(100), default="Revisión General")
    doctor_name = Column(String(100), default="Por asignar")
    status = Column(String(20), default="pending", index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="appointments")

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(String(20), nullable=False)
    sender = Column(String(20), nullable=False) # 'user', 'bot', 'admin'
    message = Column(Text, nullable=False)
    triage_code = Column(String(20), nullable=True)
    intent_detected = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    patient = relationship("Patient", back_populates="conversations")

class ClinicSetting(Base):
    __tablename__ = "clinic_settings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    setting_key = Column(String(100), unique=True, nullable=False)
    setting_value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    role = Column(String(20), default="admin")
    created_at = Column(DateTime, default=datetime.utcnow)
