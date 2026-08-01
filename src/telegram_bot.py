import os
import asyncio
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from src.db import SessionLocal
from src.bot_engine import ChatbotEngine

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Instancia global del motor del bot
engine_instance = None

def get_engine():
    global engine_instance
    if engine_instance is None:
        pdfs_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pdfs")
        engine_instance = ChatbotEngine(pdfs_path)
    return engine_instance

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start en Telegram con menú de botones interactivos."""
    user = update.effective_user
    user_name = user.first_name if user else "Paciente"
    telegram_id = str(user.id)

    keyboard = [
        [InlineKeyboardButton("📅 Pedir Cita Dental", callback_data="btn_cita")],
        [InlineKeyboardButton("🚨 Tengo Dolor / Urgencia", callback_data="btn_urgencia")],
        [InlineKeyboardButton("📍 Horarios y Ubicación", callback_data="btn_info")],
        [InlineKeyboardButton("📞 Contactar Recepción", callback_data="btn_telefono")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
        f"👋 **¡Hola, {user_name}!** Bienvenido a la **{os.getenv('CLINIC_NAME', 'Clínica Dental Sonrisas')}**.\n\n"
        "Soy tu asistente virtual inteligente. ¿En qué te puedo ayudar hoy?\n"
        "Puedes escribir tus dudas o síntomas directamente o seleccionar una de las siguientes opciones:"
    )

    db = SessionLocal()
    try:
        engine = get_engine()
        engine.get_or_create_patient(db, "telegram", telegram_id, full_name=user.full_name or user_name)
    finally:
        db.close()

    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa los clics en los botones inline."""
    query = update.callback_query
    await query.answer()

    telegram_id = str(query.from_user.id)
    user_name = query.from_user.full_name or query.from_user.first_name

    db = SessionLocal()
    engine = get_engine()
    try:
        if query.data == "btn_cita":
            reply = engine.process_message(db, "telegram", telegram_id, "Quiero pedir una cita", user_name)
        elif query.data == "btn_urgencia":
            reply = engine.process_message(db, "telegram", telegram_id, "Tengo un dolor muy fuerte y urgente", user_name)
        elif query.data == "btn_info":
            reply = engine.process_message(db, "telegram", telegram_id, "Donde estan y que horarios tienen", user_name)
        elif query.data == "btn_telefono":
            phone = os.getenv("CLINIC_PHONE", "+34 900 123 456")
            reply = f"📞 Puedes llamarnos directamente a recepción al: **{phone}**."
            engine.record_message(db, engine.get_or_create_patient(db, "telegram", telegram_id).id, "telegram", "bot", reply)
        else:
            reply = "Opción no reconocida."
    finally:
        db.close()

    await query.message.reply_text(reply, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe y procesa los mensajes de texto del usuario en Telegram."""
    if not update.message or not update.message.text:
        return

    text = update.message.text
    telegram_id = str(update.effective_user.id)
    user_name = update.effective_user.full_name or update.effective_user.first_name

    db = SessionLocal()
    try:
        engine = get_engine()
        reply = engine.process_message(db, "telegram", telegram_id, text, user_name)
    finally:
        db.close()

    await update.message.reply_text(reply, parse_mode="Markdown")

def setup_telegram_application():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token or token == "TU_TELEGRAM_BOT_TOKEN_AQUI":
        logger.warning("⚠️ TELEGRAM_BOT_TOKEN no configurado en el archivo .env. El bot de Telegram no iniciará hasta tener el token.")
        return None

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    return app

if __name__ == "__main__":
    app = setup_telegram_application()
    if app:
        print("🤖 Bot de Telegram iniciando en modo Polling...")
        app.run_polling()
