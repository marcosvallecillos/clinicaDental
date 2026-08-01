import os
import re
import logging
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any, Optional, List
from sqlalchemy.orm import Session
from src.models import Patient, Conversation, Appointment, ClinicSetting
from src.pdf_loader import KnowledgeLoader
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class ChatbotEngine:
    def __init__(self, pdfs_dir: str):
        self.loader = KnowledgeLoader(pdfs_dir)
        self.knowledge = self.loader.load_all_knowledge()
        
        # ✅ USAR GROK (Gratis)
        self.grok_api_key = os.getenv("GROK_API_KEY", "")
        self.grok_enabled = bool(self.grok_api_key and self.grok_api_key != "TU_GROK_API_KEY")
        
        logger.info(f"🤖 ChatbotEngine inicializado. RAG: {self.knowledge.get('has_rag', False)}, Grok: {self.grok_enabled}")

    def get_or_create_patient(self, db: Session, platform: str, platform_id: str, full_name: str = None, phone: str = None) -> Patient:
        """Obtiene o crea un registro de paciente en la base de datos."""
        patient = db.query(Patient).filter(
            Patient.platform == platform,
            Patient.platform_id == str(platform_id)
        ).first()

        if not patient:
            patient = Patient(
                platform=platform,
                platform_id=str(platform_id),
                full_name=full_name or f"Usuario {platform_id[-4:]}",
                phone=phone or (platform_id if platform == "whatsapp" else None),
                status="new",
                triage_level="GREEN"
            )
            db.add(patient)
            db.commit()
            db.refresh(patient)

        return patient

    def record_message(self, db: Session, patient_id: int, platform: str, sender: str, text: str, triage_code: str = None, intent: str = None):
        """Guarda cada mensaje en el historial."""
        conv = Conversation(
            patient_id=patient_id,
            platform=platform,
            sender=sender,
            message=text,
            triage_code=triage_code,
            intent_detected=intent,
            timestamp=datetime.utcnow()
        )
        db.add(conv)
        db.commit()

    def evaluate_triage(self, message: str) -> Tuple[str, str]:
        """Evalúa si hay signos de alarma"""
        msg_lower = message.lower()

        red_keywords = [
            "respirar", "dificultad para respirar", "no puedo respirar",
            "tragar agua", "tragar saliva", "ojo cerrado", "cuello hinchado",
            "hemorragia", "no para de sangrar", "pérdida de conciencia",
            "convulsiones", "pecho oprimido", "dolor de pecho", "desmayo"
        ]
        if any(kw in msg_lower for kw in red_keywords):
            return "RED", (
                "🚨 **ALERTA DE URGENCIA MÉDICA** 🚨\n\n"
                "Los síntomas que describes requieren **atención médica hospitalaria inmediata**.\n\n"
                "Por favor, dirígete al Hospital más cercano o llama al **112**.\n"
                "Teléfono urgencias clínica: **" + os.getenv("CLINIC_PHONE", "+34 900 123 456") + "**"
            )

        yellow_keywords = [
            "despierta por la noche", "dolor insoportable", "fiebre",
            "hinchado", "pus", "golpe", "muela rota", "dolor agudo",
            "inflamación severa", "absceso", "fístula", "hemorragia menor"
        ]
        if any(kw in msg_lower for kw in yellow_keywords):
            return "YELLOW", (
                "⚠️ **CITA PRIORITARIA (24-48h)** ⚠️\n\n"
                "Siento que estés sufriendo. Los síntomas sugieren atención urgente.\n"
                "¿Te gustaría agendar una cita de urgencia?"
            )

        return "GREEN", ""

    BOOKING_STATES = ("cita_nombre", "cita_telefono", "cita_fecha_hora")
    AFFIRMATIVE_RESPONSES = {
        "si", "sí", "yes", "vale", "ok", "okay", "de acuerdo", "claro",
        "perfecto", "por supuesto", "genial", "bueno", "venga",
    }
    GREETING_WORDS = {
        "hola", "buenas", "buenos", "dias", "días", "tardes", "noches",
        "hey", "saludos", "buen", "dia", "día", "hello", "hi",
    }

    def _is_greeting(self, message: str) -> bool:
        """Detecta saludos simples sin otra intención."""
        msg = re.sub(r"[^\w\sáéíóúñ]", "", message.strip().lower())
        words = msg.split()
        return bool(words) and all(w in self.GREETING_WORDS for w in words)

    def get_welcome_message(self, user_name: str = None) -> str:
        """Mensaje de bienvenida con presentación de la clínica."""
        clinic_name = os.getenv("CLINIC_NAME", "Clínica Dental Sonrisas")
        clinic_address = os.getenv("CLINIC_ADDRESS", "Calle Principal 123, Madrid")
        clinic_hours = os.getenv("CLINIC_HOURS", "Lunes a Viernes de 09:00 a 20:00")
        name_part = f", {user_name.split()[0]}" if user_name else ""

        return (
            f"👋 **¡Hola{name_part}, buenas!** Somos **{clinic_name}**.\n\n"
            f"Soy el asistente virtual de la clínica. Estoy aquí para ayudarte con "
            f"consultas sobre síntomas, información o agendar una cita.\n\n"
            f"📍 {clinic_address}\n"
            f"⏰ {clinic_hours}\n\n"
            f"¿En qué puedo ayudarte?"
        )

    def detect_appointment_intent(self, message: str) -> bool:
        """Detecta si el usuario quiere agendar explícitamente."""
        msg_lower = message.lower()
        
        cita_keywords = [
            "cita", "agendar", "reservar", "turno", "horario disponible",
            "agenda", "quiero agendar", "me gustaría una cita",
            "puedo pedir una cita", "necesito una cita", "deseo agendar",
            "programar una cita", "programar cita", "pedir cita", "pedir una cita",
            "quiero una cita", "necesito reservar",
        ]
        
        return any(kw in msg_lower for kw in cita_keywords)

    def _bot_offered_appointment(self, history: List[Dict[str, str]]) -> bool:
        """Comprueba si el bot acaba de ofrecer agendar una cita."""
        if not history:
            return False
        for msg in reversed(history[:-1]):
            if msg["role"] == "assistant":
                text = msg["content"].lower()
                offer_keywords = [
                    "agendar", "programar", "reservar", "cita",
                    "¿quieres", "te gustaría", "¿deseas", "¿necesitas",
                ]
                return any(kw in text for kw in offer_keywords)
        return False

    def _wants_appointment(self, message: str, history: Optional[List[Dict[str, str]]] = None) -> bool:
        """Detecta intención de reservar, incluido un 'sí' tras una oferta del bot."""
        if self.detect_appointment_intent(message):
            return True
        msg = message.strip().lower().rstrip("!.?")
        if msg in self.AFFIRMATIVE_RESPONSES and history and self._bot_offered_appointment(history):
            return True
        return False

    def _detect_cancel_appointment_intent(self, message: str) -> bool:
        """Detecta si el usuario quiere cancelar una reserva."""
        msg = message.lower()
        cancel_words = [
            "elimina", "eliminar", "cancelar", "cancela", "anular", "anula",
            "borrar", "borra", "quitar", "quita",
        ]
        appt_words = ["reserva", "cita", "turno"]
        return any(c in msg for c in cancel_words) and any(a in msg for a in appt_words)

    def _cancel_active_appointments(self, db: Session, patient_id: int) -> int:
        """Cancela citas activas en la base de datos."""
        appts = db.query(Appointment).filter(
            Appointment.patient_id == patient_id,
            Appointment.status.in_(["pending", "confirmed"]),
        ).all()
        for appt in appts:
            appt.status = "cancelled"
        if appts:
            patient = db.query(Patient).filter(Patient.id == patient_id).first()
            if patient and patient.status == "scheduled":
                patient.status = "new"
            db.commit()
        return len(appts)

    def _get_patient_appointments_info(self, db: Session, patient_id: int) -> str:
        """Devuelve las citas reales del paciente para el prompt del LLM."""
        appts = (
            db.query(Appointment)
            .filter(
                Appointment.patient_id == patient_id,
                Appointment.status.in_(["pending", "confirmed"]),
                Appointment.appointment_date >= datetime.utcnow(),
            )
            .order_by(Appointment.appointment_date)
            .all()
        )
        if not appts:
            return "CITAS ACTIVAS EN BASE DE DATOS: Ninguna. NO digas que tiene cita si no aparece aquí."
        lines = [
            f"- {a.appointment_date.strftime('%d/%m/%Y %H:%M')} ({a.service_type}, {a.status})"
            for a in appts
        ]
        return "CITAS ACTIVAS EN BASE DE DATOS:\n" + "\n".join(lines)

    def _start_appointment_flow(self, db: Session, patient: Patient, platform: str) -> str:
        """Inicia el flujo guiado de reserva con recogida de datos."""
        patient.status = "cita_nombre"
        db.commit()
        reply = (
            "¡Perfecto! Voy a agendar tu cita.\n\n"
            "**Paso 1 de 3: ¿Cuál es tu nombre completo?**\n"
            "(Escribe *cancelar* en cualquier momento para salir)"
        )
        self.record_message(db, patient.id, platform, "bot", reply, intent="ask_name_for_appointment")
        return reply

    def _parse_relative_datetime(self, text: str) -> Optional[datetime]:
        """Extrae día y hora de texto en español"""
        msg = text.lower()
        now = datetime.utcnow()
        
        days_map = {
            "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, 
            "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6
        }
        
        target_day = None
        target_hour = None
        target_minute = 0
        
        if "hoy" in msg:
            target_day = now.weekday()
        elif "mañana" in msg:
            target_day = (now.weekday() + 1) % 7
        else:
            for day, idx in days_map.items():
                if day in msg:
                    target_day = idx
                    break
                    
        time_match = re.search(r"\b([0-1]?[0-9]|2[0-3])(?::([0-5][0-9]))?\b", msg)
        if time_match:
            target_hour = int(time_match.group(1))
            if time_match.group(2):
                target_minute = int(time_match.group(2))
            
            if target_hour < 12 and ("tarde" in msg or "pm" in msg):
                target_hour += 12
                
        if target_day is not None and target_hour is not None:
            days_ahead = target_day - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
                
            if "hoy" in msg: days_ahead = 0
            elif "mañana" in msg: days_ahead = 1
                
            dt = now + timedelta(days=days_ahead)
            return dt.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            
        return None

    def _load_conversation_history(self, db: Session, patient_id: int, limit: int = 20) -> List[Dict[str, str]]:
        """Carga el historial reciente de la conversación para el LLM."""
        rows = (
            db.query(Conversation)
            .filter(Conversation.patient_id == patient_id)
            .order_by(Conversation.timestamp.desc())
            .limit(limit)
            .all()
        )
        rows.reverse()

        history = []
        for conv in rows:
            role = "user" if conv.sender == "user" else "assistant"
            history.append({"role": role, "content": conv.message})
        return history

    def _get_grok_response(
        self,
        user_message: str,
        context: str = "",
        conversation_history: Optional[List[Dict[str, str]]] = None,
        patient_context: str = "",
    ) -> Optional[str]:
        """Obtiene respuesta de Grok con historial de conversación."""
        if not self.grok_enabled:
            return None
        
        try:
            import openai
            
            client = openai.OpenAI(
                api_key=self.grok_api_key,
                base_url="https://api.groq.com/openai/v1"
            )
            
            system_prompt = (
                "Eres un asistente médico empático de una clínica dental.\n"
                "REGLAS CRÍTICAS:\n"
                "1. Lee TODO el historial de la conversación antes de responder.\n"
                "2. Responde ESPECÍFICAMENTE a lo que el paciente ha dicho.\n"
                "3. NO inventes ni menciones síntomas que el paciente no haya dicho.\n"
                "4. El manual clínico es solo referencia; no asumas que el paciente tiene esos síntomas.\n"
                "5. NUNCA confirmes, crees, modifiques ni canceles citas por tu cuenta.\n"
                "6. Para citas, usa SOLO los datos de 'CITAS ACTIVAS EN BASE DE DATOS'.\n"
                "7. En saludos, preséntate como la clínica de forma cálida. NO pidas agendar cita de entrada.\n"
                "8. Solo menciona agendar si el paciente lo pide o tras hablar de un problema.\n"
                "9. Tono empático y profesional.\n"
                "10. Máximo 200 caracteres.\n"
                "11. NUNCA des diagnósticos - solo orientación.\n"
            )
            
            if patient_context:
                system_prompt += f"\n\n{patient_context}"
            
            if context:
                system_prompt += f"\n\nINFORMACIÓN CLÍNICA DE REFERENCIA (no atribuir al paciente):\n{context[:1000]}"
            
            messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
            if conversation_history:
                messages.extend(conversation_history)
            else:
                messages.append({"role": "user", "content": user_message})
            
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                max_tokens=250,
                temperature=0.4
            )
            
            reply = response.choices[0].message.content
            logger.info("✅ Respuesta generada con Grok")
            return reply
            
        except Exception as e:
            logger.error(f"❌ Error en Grok: {e}")
            return None

    def process_message(self, db: Session, platform: str, platform_id: str, message_text: str, user_name: str = None) -> str:
        """
        ✅ Flujo MEJORADO con recolección de datos para citas
        """
        # 1. Obtener o crear paciente
        patient = self.get_or_create_patient(db, platform, platform_id, full_name=user_name)
        self.record_message(db, patient.id, platform, "user", message_text)

        # 2. Evaluar triaje
        triage_code, emergency_reply = self.evaluate_triage(message_text)

        if triage_code == "RED":
            self.record_message(db, patient.id, platform, "bot", emergency_reply, triage_code="RED")
            return emergency_reply

        if triage_code == "YELLOW":
            patient.triage_level = triage_code
            patient.status = "contacted"
            db.commit()

        history = self._load_conversation_history(db, patient.id)

        # Saludo inicial → presentación de la clínica (sin pasar por el LLM)
        if self._is_greeting(message_text) and patient.status not in self.BOOKING_STATES:
            reply = self.get_welcome_message(user_name or patient.full_name)
            self.record_message(db, patient.id, platform, "bot", reply, intent="welcome")
            return reply

        # Cancelar reserva (solo actúa sobre la base de datos real)
        if self._detect_cancel_appointment_intent(message_text):
            cancelled = self._cancel_active_appointments(db, patient.id)
            if cancelled:
                reply = (
                    f"✅ He cancelado {cancelled} cita(s) en el sistema.\n"
                    "Ya no tienes reservas pendientes."
                )
            else:
                reply = "No tienes ninguna cita activa en nuestro sistema."
            self.record_message(db, patient.id, platform, "bot", reply, intent="appointment_cancelled")
            return reply

        # Cancelar flujo de reserva en curso
        if patient.status in self.BOOKING_STATES and message_text.strip().lower() in {
            "cancelar", "no", "nunca", "cancelar cita", "salir",
        }:
            patient.status = "new"
            db.commit()
            reply = "Entendido, he cancelado el proceso de reserva. ¿Puedo ayudarte con algo más?"
            self.record_message(db, patient.id, platform, "bot", reply, intent="appointment_cancelled")
            return reply

        # ===== FLUJO DE AGENDAMIENTO DE CITA (Estados específicos) =====
        
        # ESTADO 1: Usuario quiere cita → Pedir nombre
        if self._wants_appointment(message_text, history) and patient.status not in self.BOOKING_STATES:
            return self._start_appointment_flow(db, patient, platform)

        # ESTADO 2: Recolectar nombre → Pedir teléfono
        if patient.status == "cita_nombre":
            # Guardar nombre
            patient.full_name = message_text.strip()
            patient.status = "cita_telefono"
            db.commit()
            
            reply = (
                f"✅ Perfecto, {patient.full_name}.\n\n"
                "**Paso 2 de 3: ¿Cuál es tu número de teléfono?**\n"
                "(Ej: 666123456 o +34 666 123 456)"
            )
            self.record_message(db, patient.id, platform, "bot", reply, intent="ask_phone_for_appointment")
            return reply

        # ESTADO 3: Recolectar teléfono → Pedir fecha y hora
        if patient.status == "cita_telefono":
            # Validar y guardar teléfono
            phone = re.sub(r"\D", "", message_text)  # Solo números
            if len(phone) < 9:
                reply = "❌ El número parece incompleto. ¿Podrías escribirlo nuevamente?"
                self.record_message(db, patient.id, platform, "bot", reply, intent="ask_phone_again")
                return reply
            
            patient.phone = message_text.strip()
            patient.status = "cita_fecha_hora"
            db.commit()
            
            reply = (
                f"✅ Número guardado: {patient.phone}\n\n"
                "**Paso 3 de 3: ¿Qué día y hora prefieres?**\n"
                "Ejemplo: 'Mañana a las 10:00' o 'El próximo viernes a las 15:30'"
            )
            self.record_message(db, patient.id, platform, "bot", reply, intent="ask_date_for_appointment")
            return reply

        # ESTADO 4: Recolectar fecha/hora → Confirmar cita
        if patient.status == "cita_fecha_hora":
            parsed_dt = self._parse_relative_datetime(message_text)
            
            if not parsed_dt:
                reply = (
                    "❌ No entendí bien la fecha. Intenta así:\n"
                    "• 'Mañana a las 10:00'\n"
                    "• 'El próximo lunes a las 14:30'\n"
                    "• 'Viernes a las 16:00'"
                )
                self.record_message(db, patient.id, platform, "bot", reply, intent="ask_date_again")
                return reply

            # Verificar disponibilidad
            day_start = parsed_dt.replace(hour=0, minute=0, second=0)
            day_end = parsed_dt.replace(hour=23, minute=59, second=59)
            
            appts_day = db.query(Appointment).filter(
                Appointment.appointment_date >= day_start,
                Appointment.appointment_date <= day_end,
                Appointment.status.in_(["pending", "confirmed"])
            ).all()
            
            busy_hours = [a.appointment_date.hour for a in appts_day]
            
            if parsed_dt.hour in busy_hours:
                available_hours = [h for h in range(9, 20) if h not in busy_hours]
                if available_hours:
                    free_list = ", ".join([f"{h}:00" for h in available_hours])
                    reply = (
                        f"❌ A las {parsed_dt.strftime('%H:%M')} está ocupado.\n\n"
                        f"**Horarios disponibles ese día:** {free_list}"
                    )
                else:
                    reply = f"❌ Ese día está completamente lleno.\n\n¿Puedes elegir otro día?"
                
                self.record_message(db, patient.id, platform, "bot", reply, intent="slot_not_available")
                return reply
            
            # ✅ CREAR CITA
            new_appt = Appointment(
                patient_id=patient.id,
                appointment_date=parsed_dt,
                service_type="Consulta Médica",
                doctor_name="Por asignar",
                status="confirmed",
                notes=f"Agendada por bot. Teléfono: {patient.phone}"
            )
            db.add(new_appt)
            patient.status = "scheduled"
            patient.phone = patient.phone  # Actualizar teléfono
            db.commit()
            
            reply = (
                f"✅ **¡CITA CONFIRMADA!**\n\n"
                f"📋 **Datos de tu cita:**\n"
                f"👤 Nombre: {patient.full_name}\n"
                f"📞 Teléfono: {patient.phone}\n"
                f"📅 Fecha: {parsed_dt.strftime('%A, %d de %B')}\n"
                f"⏰ Hora: {parsed_dt.strftime('%H:%M')}\n\n"
                f"Te esperamos en la clínica. 😊"
            )
            self.record_message(db, patient.id, platform, "bot", reply, intent="appointment_confirmed")
            return reply

        # ===== CONVERSACIÓN GENERAL (Sin flujo de cita) =====

        # Extraer nombre si lo proporciona
        name_match = re.search(r"(?:mi nombre (?:completo )?es|me llamo)\s+([A-Za-zÁÉÍÓÚáéíóúÑñ\s]+)", message_text, re.IGNORECASE)
        if name_match and patient.full_name.startswith("Usuario"):
            patient.full_name = name_match.group(1).strip()
            patient.status = "new"
            db.commit()

        # Responder consulta general con historial y datos reales del paciente
        context = ""
        if self.knowledge.get('has_rag'):
            context = self.loader.get_context_for_query(message_text)

        appointments_info = self._get_patient_appointments_info(db, patient.id)
        clinic_address = os.getenv("CLINIC_ADDRESS", "Calle Principal 123")
        clinic_phone = os.getenv("CLINIC_PHONE", "+34 900 123 456")
        patient_context = (
            f"{appointments_info}\n"
            f"DIRECCIÓN CLÍNICA: {clinic_address}\n"
            f"TELÉFONO CLÍNICA: {clinic_phone}"
        )

        reply = self._get_grok_response(
            message_text,
            context,
            conversation_history=history,
            patient_context=patient_context,
        )

        if not reply:
            reply = self._fallback_response(message_text, triage_code)

        self.record_message(db, patient.id, platform, "bot", reply, triage_code=triage_code, intent="general_qa")
        return reply

    def _fallback_response(self, message: str, triage_code: str) -> str:
        """Respuesta empática como fallback"""
        msg_lower = message.lower()

        if any(word in msg_lower for word in ["hola", "buenas", "inicio", "qué"]):
            return self.get_welcome_message()

        if any(word in msg_lower for word in ["precio", "costo", "tarifa"]):
            return (
                "💰 Ofrecemos **primera consulta gratuita** con diagnóstico.\n"
                "¿Deseas agendar?"
            )

        if any(word in msg_lower for word in ["horario", "donde", "dirección", "ubicación"]):
            address = os.getenv("CLINIC_ADDRESS", "Calle Principal 123")
            phone = os.getenv("CLINIC_PHONE", "+34 900 123 456")
            return f"📍 {address}\n📞 {phone}\n⏰ L-V: 09:00-20:00, Sáb: 10:00-14:00"

        if any(word in msg_lower for word in ["duele", "dolor", "molestia", "síntoma"]):
            return (
                "Entiendo. Para poder orientarte mejor, necesito detalles.\n"
                "¿Desde cuándo lo padeces? ¿Es continuo o va y viene?\n\n"
                "Si es urgente, puedo agendar una cita de urgencia."
            )

        return (
            "Estoy aquí para ayudarte con consultas médicas o para agendar una cita.\n"
            "¿Hay algo específico en lo que pueda asistirte?"
        )