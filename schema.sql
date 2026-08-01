-- ========================================================
-- ESQUEMA DE BASE DE DATOS MYSQL PARA CLÍNICA DENTAL CHATBOT
-- ========================================================

CREATE DATABASE IF NOT EXISTS clinica_dental_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE clinica_dental_db;

-- 1. Tabla de Pacientes / Leads
CREATE TABLE IF NOT EXISTS patients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(150),
    phone VARCHAR(50),
    email VARCHAR(100),
    platform ENUM('telegram', 'whatsapp') NOT NULL DEFAULT 'telegram',
    platform_id VARCHAR(100) NOT NULL UNIQUE, -- Telegram ID o Número de WhatsApp (ej. whatsapp:+34123456789)
    status ENUM('new', 'contacted', 'scheduled', 'converted', 'lost') DEFAULT 'new',
    triage_level ENUM('RED', 'YELLOW', 'GREEN') DEFAULT 'GREEN',
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_platform (platform, platform_id),
    INDEX idx_phone (phone),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Tabla de Citas / Agendamientos
CREATE TABLE IF NOT EXISTS appointments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    appointment_date DATETIME NOT NULL,
    service_type VARCHAR(100) DEFAULT 'Revisión General',
    doctor_name VARCHAR(100) DEFAULT 'Por asignar',
    status ENUM('pending', 'confirmed', 'completed', 'cancelled') DEFAULT 'pending',
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    INDEX idx_patient (patient_id),
    INDEX idx_date (appointment_date),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Tabla de Conversaciones e Historial de Mensajes
CREATE TABLE IF NOT EXISTS conversations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    platform ENUM('telegram', 'whatsapp') NOT NULL,
    sender ENUM('user', 'bot', 'admin') NOT NULL,
    message TEXT NOT NULL,
    triage_code VARCHAR(20) DEFAULT NULL,
    intent_detected VARCHAR(50) DEFAULT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    INDEX idx_patient_chat (patient_id, timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Tabla de Configuración de la Clínica
CREATE TABLE IF NOT EXISTS clinic_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    setting_key VARCHAR(100) UNIQUE NOT NULL,
    setting_value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Tabla de Usuarios Administradores
CREATE TABLE IF NOT EXISTS admin_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    role ENUM('admin', 'receptionist') DEFAULT 'admin',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Datos Iniciales de Ejemplo para Pruebas
INSERT IGNORE INTO clinic_settings (setting_key, setting_value) VALUES
('clinic_name', 'Clínica Dental Sonrisas'),
('clinic_phone', '+34 900 123 456'),
('clinic_address', 'Calle Principal 123, Madrid'),
('clinic_hours', 'Lunes a Viernes de 09:00 a 20:00, Sábados de 10:00 a 14:00'),
('ai_prompt_instructions', 'Eres la asistente virtual amable y profesional de la Clínica Dental Sonrisas. Realizas triaje según la metodología ALICIA y aconsejas agendar una cita. NUNCA diagnostiques medicaciones ni enfermedades concluyentes.');

-- Usuario Admin por defecto: admin / admin123 (hash SHA256 básico para demostración)
INSERT IGNORE INTO admin_users (username, password_hash, full_name, role) VALUES
('admin', '8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918', 'Administrador General', 'admin');
