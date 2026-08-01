import os
import re
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any, Optional
from sqlalchemy.orm import Session
from src.models import Patient, Conversation, Appointment, ClinicSetting
from src.pdf_loader import KnowledgeLoader
from dotenv import load_dotenv

load_dotenv()

class ChatbotEngine:
    def __init__(self, pdfs_dir: str):
        self.loader = KnowledgeLoader(pdfs_dir)
        self.knowledge = self.loader.load_all_knowledge()
        self.openai_key = os.getenv("OPENAI_API_KEY", "")

    def get_or_create_patient(self, db: Session, platform: str, platform_id: str, full_name: str = None, phone: str = None) -> Patient:
        """Obtiene o crea un registro de paciente/lead en la base de datos MySQL."""
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
        elif full_name and patient.full_name.startswith("Usuario "):
            patient.full_name = full_name
            db.commit()

        return patient

    def record_message(self, db: Session, patient_id: int, platform: str, sender: str, text: str, triage_code: str = None, intent: str = None):
        """Guarda cada mensaje en la tabla de conversaciones para el historial del Admin."""
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
        """
        Evalúa si hay signos de alarma (Triaje Odontológico):
        - RED: Urgencia Hospitalaria (dificultad respiratoria, hinchazón cara/ojo, hemorragia grave)
        - YELLOW: Urgencia 24h (dolor nocturno, punzante grave, fiebre > 38C)
        - GREEN: Consulta / Cita habitual
        """
        msg_lower = message.lower()

        # CÓDIGO ROJO - Urgencia Vital / Hospitalaria
        red_keywords = ["respirar", "dificultad para respirar", "tragar agua", "tragar saliva", "ojo cerrado", "cuello hinchado", "hemorragia", "no para de sangrar"]
        if any(kw in msg_lower for kw in red_keywords):
            return "RED", (
                "🚨 **ALERTA DE URGENCIA MÉDICA** 🚨\n\n"
                "Los síntomas que describes (dificultad para respirar, tragar o inflamación severa) requieren **atención médica hospitalaria inmediata**.\n\n"
                "Por favor, dirígete de inmediato al Servicio de Urgencias del Hospital más cercano o llama al **112 / 061**.\n"
                "Si deseas hablar directamente con nuestra clínica, nuestro teléfono de urgencias es: **" + os.getenv("CLINIC_PHONE", "+34 900 123 456") + "**."
            )

        # CÓDIGO AMARILLO - Cita prioritaria en 24h
        yellow_keywords = ["despierta por la noche", "dolor insoportable", "fiebre", "hinchado", "absceso", "fístula", "pus", "golpe", "muela rota dolor"]
        if any(kw in msg_lower for kw in yellow_keywords):
            return "YELLOW", (
                "⚠️ **CITA PRIORITARIA RECOMENDADA (CÓDIGO AMARILLO)** ⚠️\n\n"
                "Siento mucho que estés sufriendo estas molestias. Los síntomas descritos (dolor nocturno/intenso o inflamación) sugieren que el tejido interno requiere atención prioritaria en 24-48h.\n\n"
                "¿Te gustaría que te reservemos un hueco de **urgencia preferente** para hoy o mañana por la mañana?"
            )

        return "GREEN", ""

    def parse_appointment_request(self, message: str) -> Optional[Dict[str, Any]]:
        """Detecta si el usuario desea pedir o agendar una cita."""
        msg_lower = message.lower()
        if any(word in msg_lower.replace(',',' ').replace('.',' ').split() for word in ["cita", "agendar", "reservar", "turnos", "horario", "revision", "limpieza", "consulta", "si", "sí", "quiero", "vale", "ok"]):
            # Intentar extraer tipo de servicio
            service = "Revisión General"
            if "limpieza" in msg_lower: service = "Higiene / Limpieza Dental"
            elif "urgencia" in msg_lower or "dolor" in msg_lower: service = "Cita de Urgencia"
            elif "ortodoncia" in msg_lower or "brackets" in msg_lower: service = "Ortodoncia / Valoración"
            elif "implante" in msg_lower: service = "Implantología"
            elif "estética" in msg_lower or "blanqueamiento" in msg_lower: service = "Estética / Blanqueamiento"

            return {
                "service": service,
                "suggested_date": datetime.utcnow() + timedelta(days=1)
            }
        return None

    def _parse_relative_datetime(self, text: str) -> Optional[datetime]:
        """Intenta extraer día de la semana y hora de un texto en español básico."""
        msg = text.lower()
        now = datetime.utcnow()
        
        days_map = {
            "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, 
            "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6
        }
        
        target_day = None
        target_hour = None
        target_minute = 0
        
        # Buscar día
        if "hoy" in msg:
            target_day = now.weekday()
        elif "mañana" in msg:
            target_day = (now.weekday() + 1) % 7
        else:
            for day, idx in days_map.items():
                if day in msg:
                    target_day = idx
                    break
                    
        # Buscar hora (ej. 16:00, a las 16)
        time_match = re.search(r"\b([0-1]?[0-9]|2[0-3])(?::([0-5][0-9]))?\b", msg)
        if time_match:
            target_hour = int(time_match.group(1))
            if time_match.group(2):
                target_minute = int(time_match.group(2))
            
            # Ajuste pm (si dice a las 4 de la tarde -> 16:00)
            if target_hour < 12 and ("tarde" in msg or "pm" in msg):
                target_hour += 12
                
        if target_day is not None and target_hour is not None:
            # Calcular cuántos días sumar
            days_ahead = target_day - now.weekday()
            if days_ahead <= 0: # Si es el mismo día y la hora ya pasó o un día anterior
                days_ahead += 7
                
            if "hoy" in msg: days_ahead = 0
            elif "mañana" in msg: days_ahead = 1
                
            if "semana que viene" in msg or "proxima" in msg or "próxima" in msg:
                days_ahead += 7
                
            dt = now + timedelta(days=days_ahead)
            return dt.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            
        return None

    def process_message(self, db: Session, platform: str, platform_id: str, message_text: str, user_name: str = None) -> str:
        """
        Procesa un mensaje entrante de Telegram o WhatsApp:
        1. Registra/Actualiza al paciente en MySQL.
        2. Guarda el mensaje del usuario en MySQL.
        3. Realiza el triaje clínico (RED, YELLOW, GREEN).
        4. Genera la respuesta empática adecuada.
        5. Guarda la respuesta del chatbot en MySQL.
        """
        # 1. Obtener o crear paciente
        patient = self.get_or_create_patient(db, platform, platform_id, full_name=user_name)
        
        # 2. Registrar mensaje del usuario
        self.record_message(db, patient.id, platform, "user", message_text)

        # 3. Evaluar triaje clínico
        triage_code, emergency_reply = self.evaluate_triage(message_text)

        # Actualizar triaje del paciente si cambia
        if triage_code in ["RED", "YELLOW"]:
            patient.triage_level = triage_code
            if triage_code == "RED":
                patient.status = "contacted"
            db.commit()

        if triage_code == "RED":
            reply = emergency_reply
            self.record_message(db, patient.id, platform, "bot", reply, triage_code="RED", intent="emergency_hospital")
            return reply

        # Extracción simple de nombre: "mi nombre es X" o "me llamo X"
        name_match = re.search(r"(?:mi nombre (?:completo )?es|me llamo)\s+([A-Za-zÁÉÍÓÚáéíóúÑñ\s]+)", message_text, re.IGNORECASE)
        if name_match:
            patient.full_name = name_match.group(1).strip()
            db.commit()

        # 4. Verificar si el paciente está respondiendo a la pregunta de qué día y hora quiere
        if patient.status == "asking_date":
            parsed_dt = self._parse_relative_datetime(message_text)
            
            if parsed_dt:
                # Comprobar disponibilidad ese día en la BD
                day_start = parsed_dt.replace(hour=0, minute=0, second=0)
                day_end = parsed_dt.replace(hour=23, minute=59, second=59)
                
                appts_day = db.query(Appointment).filter(
                    Appointment.appointment_date >= day_start,
                    Appointment.appointment_date <= day_end,
                    Appointment.status.in_(["pending", "confirmed"])
                ).all()
                
                # Horario de clínica básico: de 9 a 20h
                available_hours = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
                busy_hours = [a.appointment_date.hour for a in appts_day]
                
                if parsed_dt.hour in busy_hours:
                    # El slot está ocupado
                    free_hours = [h for h in available_hours if h not in busy_hours]
                    if free_hours:
                        free_list = ", ".join([f"{h}:00" for h in free_hours])
                        reply = (f"Lo siento, a las {parsed_dt.strftime('%H:%M')} nuestra agenda ya está ocupada. 😔\n\n"
                                 f"Para el mismo día ({parsed_dt.strftime('%d/%m')}), tenemos hueco a las: **{free_list}**.\n\n"
                                 "¿Alguna de esas horas te sirve o prefieres mirar otro día?")
                    else:
                        reply = (f"Lo siento, la agenda del {parsed_dt.strftime('%d/%m')} ya está completamente llena. 😔\n"
                                 "¿Qué otro día te vendría bien?")
                    self.record_message(db, patient.id, platform, "bot", reply, triage_code=triage_code, intent="retry_appointment_date")
                    return reply
                else:
                    # Slot libre, agendar cita
                    new_appt = Appointment(
                        patient_id=patient.id,
                        appointment_date=parsed_dt,
                        service_type="Consulta General",
                        status="confirmed",
                        notes=f"Automatizado por bot: {message_text}"
                    )
                    db.add(new_appt)
                    patient.status = "scheduled" 
                    db.commit()
                    
                    # Formatear la fecha en español
                    fechas_str = f"{parsed_dt.strftime('%d/%m/%Y')} a las {parsed_dt.strftime('%H:%M')}"
                    reply = (f"✅ **¡Cita Confirmada!**\n\n"
                             f"He reservado tu consulta para el **{fechas_str}**.\n"
                             f"*(Nombre registrado: {patient.full_name})*\n\n"
                             "Te esperamos en la clínica. ¡Un saludo!")
                    self.record_message(db, patient.id, platform, "bot", reply, triage_code=triage_code, intent="appointment_created")
                    return reply
            else:
                # Fallback por si la IA NLP básica no logró extraer bien el horario
                # Buscar si ya tiene una cita pendiente para no duplicar
                existing_appt = db.query(Appointment).filter(
                    Appointment.patient_id == patient.id,
                    Appointment.status == "pending"
                ).order_by(Appointment.id.desc()).first()

                if existing_appt:
                    existing_appt.notes = f"Preferencia actualizada: {message_text}"
                else:
                    new_appt = Appointment(
                        patient_id=patient.id,
                        appointment_date=datetime.utcnow() + timedelta(days=1), # Fecha dummy
                        service_type="Pendiente de confirmar horario",
                        status="pending",
                        notes=f"Preferencia del paciente: {message_text}"
                    )
                    db.add(new_appt)

                patient.status = "scheduled"
                db.commit()

                reply = (
                    f"✅ **¡Detalles Recibidos!**\n\n"
                    f"He tomado nota: '{message_text}'.\n"
                    f"*(Nombre registrado: {patient.full_name})*\n\n"
                    f"Nuestro equipo de recepción revisará la agenda y se contactará contigo."
                )
                self.record_message(db, patient.id, platform, "bot", reply, triage_code=triage_code, intent="appointment_created")
                return reply

        # Verificar si es solicitud de cita
        appt_info = self.parse_appointment_request(message_text)
        if appt_info and any(w in message_text.lower() for w in ["mañana", "si", "sí", "cita", "quiero", "vale", "ok"]):
            patient.status = "asking_date"
            db.commit()
            
            reply = (
                f"¡Genial! Para poder organizarlo, **¿qué día de la semana y en qué horario te vendría mejor acudir a la clínica?**\n"
                f"(Por ejemplo: 'Los martes por la tarde' o 'El próximo viernes a primera hora')"
            )
            self.record_message(db, patient.id, platform, "bot", reply, triage_code=triage_code, intent="ask_appointment_date")
            return reply

        # 5. Respuesta inteligente (OpenAI o Plantilla Guía Empática)
        if self.openai_key and self.openai_key != "TU_OPENAI_API_KEY_O_GEMINI_KEY":
            try:
                import openai
                client = openai.OpenAI(api_key=self.openai_key)
                system_prompt = (
                    "Eres el asistente virtual empático de la Clínica Dental Sonrisas. "
                    "REGLAS OBLIGATORIAS:\n"
                    "1. NUNCA des diagnósticos médicos concluyentes.\n"
                    "2. Usa la metodología ALICIA (Aparición, Localización, Intensidad, Característica, Irradiación, Aliviadores).\n"
                    "3. Usa tono empático, calmado y respetuoso.\n"
                    "4. Invita al paciente a pedir cita presencial.\n"
                    "5. Si el triaje detecta urgencia, facilítale la cita rápida.\n\n"
                    f"INFORMACIÓN BASE DE CONOCIMIENTO (MANUAL CLINICO):\n{self.knowledge['text'][:2000]}"
                )
                response = client.chat.completions.create(
                    model=os.getenv("AI_MODEL", "gpt-4o-mini"),
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message_text}
                    ],
                    max_tokens=350,
                    temperature=0.7
                )
                reply = response.choices[0].message.content
            except Exception as e:
                print(f"Error llamando a OpenAI API: {e}")
                reply = self._fallback_response(message_text, triage_code)
        else:
            reply = self._fallback_response(message_text, triage_code)

        # 6. Guardar respuesta del bot
        self.record_message(db, patient.id, platform, "bot", reply, triage_code=triage_code, intent="general_qa")
        return reply

    def _fallback_response(self, message: str, triage_code: str) -> str:
        """Respuesta guiada empática basada en el manual clínico cuando no hay API Key de OpenAI."""
        msg_lower = message.lower()

        if triage_code == "YELLOW":
            return (
                "Siento mucho que estés sufriendo estas molestias dentales. "
                "Para poder orientar mejor al odontólogo, ¿podrías indicarme desde cuándo sientes este dolor y si es punzante o constante?\n\n"
                "En cualquier caso, te recomiendo una revisión urgente. ¿Deseas que agendemos una cita prioritaria para mañana?"
            )
        
        if any(word in msg_lower for word in ["hola", "buenas", "inicio", "empezar", "saludos"]):
            clinic_name = os.getenv("CLINIC_NAME", "Clínica Dental Sonrisas")
            return (
                f"¡Hola! 👋 Te damos la bienvenida a **{clinic_name}**.\n\n"
                "Soy tu asistente virtual. Estoy aquí para ayudarte con consultas sobre molestias dentales, tratamientos o para **agendar tu cita**.\n\n"
                "¿En qué te puedo ayudar hoy? (puedes describir tus síntomas o pedir una cita)."
            )

        if any(word in msg_lower for word in ["precio", "costo", "tarifa", "cuanto cuesta", "presupuesto"]):
            return (
                "El coste de los tratamientos varía según la valoración clínica de cada paciente.\n"
                "Ofrecemos **primera consulta y diagnóstico totalmente gratuitos** con radiografía incluida.\n\n"
                "¿Te gustaría agendar tu primera consulta gratuita?"
            )

        if any(word in msg_lower for word in ["horario", "donde estan", "direccion", "telefono", "ubicacion"]):
            address = os.getenv("CLINIC_ADDRESS", "Calle Principal 123, Madrid")
            hours = os.getenv("CLINIC_HOURS", "Lunes a Viernes de 09:00 a 20:00")
            phone = os.getenv("CLINIC_PHONE", "+34 900 123 456")
            return (
                f"📍 **Nuestra Ubicación:** {address}\n"
                f"⏰ **Horario de atención:** {hours}\n"
                f"📞 **Teléfono de contacto:** {phone}\n\n"
                "¿Deseas pedir cita para acudir a la clínica?"
            )

        if any(word in msg_lower.replace(',',' ').replace('.',' ').split() for word in ["no", "nunca", "nada"]):
            return "Entendido. Si no deseas agendar una cita por ahora, no pasa nada. ¡Sigo aquí a tu disposición por si necesitas alguna otra consulta clínica!"

        if any(word in msg_lower for word in ["duele", "dolor", "molestia", "molesta", "sensibilidad", "frio", "agua", "caliente", "diente"]):
            return (
                "Pudiera tratarse de sensibilidad dental, inflamación o incluso daño en el esmalte que está avisando al contacto. "
                "Lo más prudente para tu salud dental es que nuestro equipo odontológico lo revise de cerca.\n\n"
                "¿Deseas que te reservemos una cita de valoración para averiguar qué ocurre?"
            )

        return (
            "Gracias por comunicarte con nosotros. Para determinar exactamente el origen de tu consulta y ofrecerte la mejor solución, "
            "es imprescindible una valoración presencial por nuestro equipo de odontólogos.\n\n"
            "¿Deseas pedir cita ahora o consultar algún otro detalle?"
        )
