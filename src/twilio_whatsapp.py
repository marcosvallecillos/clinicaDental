import os
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from sqlalchemy.orm import Session
from src.bot_engine import ChatbotEngine

load_dotenv()

account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
from_whatsapp_number = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

def get_twilio_client():
    if account_sid and auth_token and account_sid != "TU_TWILIO_ACCOUNT_SID":
        try:
            return Client(account_sid, auth_token)
        except Exception as e:
            print(f"⚠️ Error al inicializar cliente Twilio: {e}")
    return None

def process_whatsapp_webhook(db: Session, engine: ChatbotEngine, incoming_data: dict) -> str:
    """
    Procesa el webhook enviado por Twilio WhatsApp cuando un paciente envía un mensaje.
    Datos recibidos típicamente:
    - From: 'whatsapp:+34600000000'
    - Body: 'Hola quiero pedir cita'
    - ProfileName: 'Juan Pérez'
    """
    from_number = incoming_data.get("From", "")
    body_text = incoming_data.get("Body", "").strip()
    profile_name = incoming_data.get("ProfileName", "")

    if not from_number or not body_text:
        twiml = MessagingResponse()
        return str(twiml)

    # El platform_id para WhatsApp es el número completo de WhatsApp (ej. whatsapp:+34600000000)
    clean_phone = from_number.replace("whatsapp:", "")
    user_name = profile_name if profile_name else f"Paciente WhatsApp ({clean_phone})"

    # Procesar con el motor central
    bot_reply = engine.process_message(
        db=db,
        platform="whatsapp",
        platform_id=from_number,
        message_text=body_text,
        user_name=user_name
    )

    # Generar respuesta TwiML XML para Twilio
    twiml = MessagingResponse()
    twiml.message(bot_reply)
    return str(twiml)

def send_direct_whatsapp_message(to_number: str, message_text: str) -> bool:
    """Envía un mensaje directo a WhatsApp (para intervención humana del Admin)."""
    client = get_twilio_client()
    if not client:
        print(f"⚠️ Twilio no configurado. Mensaje simulado a {to_number}: {message_text}")
        return False

    target_num = to_number if to_number.startswith("whatsapp:") else f"whatsapp:{to_number}"

    try:
        msg = client.messages.create(
            from_=from_whatsapp_number,
            body=message_text,
            to=target_num
        )
        print(f"✅ Mensaje WhatsApp enviado via Twilio SID: {msg.sid}")
        return True
    except Exception as e:
        print(f"❌ Error enviando mensaje WhatsApp via Twilio: {e}")
        return False
