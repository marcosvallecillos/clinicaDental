# 🦷 Chatbot para Clínica Dental (Telegram + Twilio WhatsApp + MySQL + Panel Admin)

Este proyecto es una solución integral y profesional para clínicas dentales. Incluye:
- **Chatbot Inteligente con Triaje ALICIA y Detección de Urgencias** (Código Rojo, Amarillo y Verde).
- **Soporte Multicanal:** Telegram listo para probar + Twilio WhatsApp integrado.
- **Base de Datos MySQL:** Guarda leads/pacientes, agendamientos de citas e historial completo de conversaciones.
- **Panel de Administración Web:** Dashboard con métricas, gestión de pacientes, calendario de citas, monitor de chats en vivo e intervención humana (Live Handoff).

---

## 📁 Estructura del Proyecto

```text
clinica/
├── .env                       # Configuración de MySQL, Telegram, Twilio y OpenAI
├── main.py                    # Servidor principal FastAPI + Ejecutor de bots
├── requirements.txt           # Librerías de Python requeridas
├── schema.sql                 # Script de creación de tablas en MySQL
├── pdfs/                      # Base de conocimiento (PDFs, Markdown, JSON, YAML)
│   ├── manual_integral_sintomas_chatbot.pdf
│   ├── manual_chatbot_dental.md
│   ├── chatbot_knowledge_base.json
│   └── chatbot_rules.yaml
├── uploads/                   # Carpeta para archivos o fotos de pacientes
├── logs/                      # Registro de auditoría
└── src/
    ├── admin_ui.html          # Panel de Administración Web (Dashboard)
    ├── api_routes.py          # Rutas REST API para el Panel Admin y Webhooks
    ├── bot_engine.py          # Motor del chatbot (Triaje ALICIA + IA)
    ├── db.py                  # Conexión SQLAlchemy a MySQL (con fallback SQLite)
    ├── models.py              # Modelos de MySQL (Pacientes, Citas, Chats, Settings)
    ├── pdf_loader.py          # Cargador automático de PDFs y base de datos
    ├── telegram_bot.py        # Integrador de Telegram Bot
    └── twilio_whatsapp.py     # Integrador de Twilio WhatsApp
```

---

## 🚀 Instalación y Puesta en Marcha

### 1. Requisitos Previos
- Python 3.9 o superior.
- MySQL Server (o phpMyAdmin / XAMPP / DBeaver).

### 2. Instalar Dependencias
```bash
pip install -r requirements.txt
```

### 3. Configurar Base de Datos MySQL
1. Crea la base de datos importando el archivo `schema.sql` en tu servidor MySQL (o deja que la aplicación la cree automáticamente al iniciar):
   ```sql
   mysql -u root -p < schema.sql
   ```
2. Revisa el archivo `.env` y ajusta las credenciales de tu MySQL:
   ```env
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=tu_contraseña
   DB_NAME=clinica_dental_db
   ```

### 4. Configurar Telegram (Pruebas Iniciales)
1. Habla con `@BotFather` en Telegram y crea un nuevo Bot (`/newbot`).
2. Copia el Token obtenido y pégalo en `.env`:
   ```env
   TELEGRAM_BOT_TOKEN="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
   ```

### 5. Configurar Twilio (WhatsApp para Producción)
1. Crea una cuenta en [Twilio.com](https://www.twilio.com/).
2. Copia tu `ACCOUNT SID` y `AUTH TOKEN` al `.env`:
   ```env
   TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxx"
   TWILIO_AUTH_TOKEN="your_auth_token"
   TWILIO_WHATSAPP_NUMBER="whatsapp:+14155238886"
   ```
3. Configura en la consola de Twilio Sandbox/WhatsApp el Webhook HTTP POST señalando a la URL pública de tu servidor (ej. usando Ngrok):
   `https://tu-dominio.com/api/webhooks/twilio`

---

## 🖥️ Iniciar el Sistema y Panel Admin

Ejecuta el servidor principal:
```bash
python main.py
```

- **Panel de Administración Web:** Abre tu navegador en `http://localhost:8000/admin` o `http://localhost:8000/`
- **Bot de Telegram:** Empezará a responder automáticamente a tus usuarios en Telegram y a guardar todos los leads y citas en MySQL.

---

## 📋 Documentos Recomendados para el 100% de Funcionamiento

Para que el chatbot tenga una cobertura del 100% de la clínica, te recomendamos añadir los siguientes archivos PDF a la carpeta `pdfs/`:

1. `tarifario_y_tratamientos.pdf`: Lista de precios oficial y seguros médicos aceptados.
2. `equipo_medico_y_especialidades.pdf`: Lista de doctores y especialidades de la clínica.
3. `politica_privacidad_rgpd.pdf`: Documento de protección de datos de salud.
4. `instrucciones_post_tratamiento.pdf`: Cuidados recomendados tras cirugías o extracciones.
