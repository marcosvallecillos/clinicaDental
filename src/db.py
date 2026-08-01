import os
import hashlib
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from src.models import Base, ClinicSetting, AdminUser

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./clinica_local.db")

# Si la conexión principal a MySQL falla durante desarrollo, usamos SQLite de respaldo para evitar bloqueos
try:
    if "mysql" in DATABASE_URL:
        engine = create_engine(
            DATABASE_URL,
            pool_recycle=3600,
            pool_pre_ping=True
        )
    else:
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
except Exception as e:
    print(f"⚠️ Error conectando a MySQL ({e}). Usando SQLite local de fallback.")
    DATABASE_URL = "sqlite:///./clinica_local.db"
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Tablas de la base de datos inicializadas correctamente.")
        
        # Insertar valores predeterminados de configuración
        db: Session = SessionLocal()
        default_settings = {
            "clinic_name": os.getenv("CLINIC_NAME", "Clínica Dental Sonrisas"),
            "clinic_phone": os.getenv("CLINIC_PHONE", "+34 900 123 456"),
            "clinic_address": os.getenv("CLINIC_ADDRESS", "Calle Principal 123, Madrid"),
            "clinic_hours": os.getenv("CLINIC_HOURS", "Lunes a Viernes 09:00 - 20:00, Sábados 10:00 - 14:00"),
            "ai_instructions": "Eres el asistente inteligente de la clínica dental. Asistes al paciente con empatía, aplicas el triaje médico ALICIA y aconsejas agendar una cita sin dar diagnósticos médicos definitivos."
        }
        
        for key, val in default_settings.items():
            existing = db.query(ClinicSetting).filter(ClinicSetting.setting_key == key).first()
            if not existing:
                db.add(ClinicSetting(setting_key=key, setting_value=val))
        
        # Crear usuario admin por defecto si no existe
        existing_admin = db.query(AdminUser).filter(AdminUser.username == "admin").first()
        if not existing_admin:
            hashed_pwd = hashlib.sha256("admin123".encode()).hexdigest()
            db.add(AdminUser(username="admin", password_hash=hashed_pwd, full_name="Administrador Clínica", role="admin"))
            
        db.commit()
        db.close()
    except Exception as e:
        print(f"⚠️ Nota de DB initialization: {e}")
