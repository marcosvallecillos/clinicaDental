import os
import uvicorn
import asyncio
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from src.db import init_db
from src.api_routes import router as api_router
from src.telegram_bot import setup_telegram_application

load_dotenv()

app = FastAPI(
    title=os.getenv("APP_NAME", "DentalBot Admin & Chatbot Engine"),
    version="1.0.0",
    description="Sistema Chatbot Multicanal (Telegram & WhatsApp/Twilio) + Base de Datos MySQL + Panel de Administración para Clínica Dental"
)

# Configuración CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar rutas API
app.include_router(api_router)

@app.on_event("startup")
async def on_startup():
    print("🚀 Inicializando base de datos MySQL / SQLite...")
    init_db()

    # Iniciar bot de Telegram en segundo plano si está configurado
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if token and token != "TU_TELEGRAM_BOT_TOKEN_AQUI":
        try:
            telegram_app = setup_telegram_application()
            if telegram_app:
                await telegram_app.initialize()
                await telegram_app.start()
                await telegram_app.updater.start_polling()
                print("🤖 Bot de Telegram iniciado exitosamente en segundo plano.")
                app.state.telegram_app = telegram_app
        except Exception as e:
            print(f"⚠️ No se pudo iniciar el bot de Telegram automáticamente: {e}")
    else:
        print("ℹ️ TELEGRAM_BOT_TOKEN no provisto o es de prueba. Configúralo en .env para activar Telegram.")

@app.on_event("shutdown")
async def on_shutdown():
    if hasattr(app.state, "telegram_app"):
        tg_app = app.state.telegram_app
        if tg_app:
            print("🛑 Deteniendo el bot de Telegram...")
            await tg_app.updater.stop()
            await tg_app.stop()
            await tg_app.shutdown()

@app.get("/", response_class=HTMLResponse)
@app.get("/admin", response_class=HTMLResponse)
def serve_admin_panel():
    """Sirve la interfaz web del Panel de Administración."""
    html_path = os.path.join(os.path.dirname(__file__), "src", "admin_ui.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return "<h1>Panel de administración en construcción</h1>"

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"🌍 Servidor iniciando en http://{host}:{port} (Panel Admin en http://localhost:{port}/admin)")
    uvicorn.run("main:app", host=host, port=port, reload=True)
