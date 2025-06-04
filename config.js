// config.js - إعدادات التطبيق المركزية

const path = require('path');
const os = require('os');

// تحميل متغيرات البيئة
require('dotenv').config();

// تكوين المسارات
const UPLOAD_FOLDER = process.env.UPLOAD_DIR || path.join(__dirname, 'uploads');
const OUTPUT_FOLDER = process.env.OUTPUT_DIR || path.join(__dirname, 'outputs');
const LOGS_FOLDER = path.join(__dirname, 'logs');

// الإعدادات العامة
const config = {
  // بيئة التطبيق
  DEBUG: process.env.NODE_ENV !== 'production',
  NODE_ENV: process.env.NODE_ENV || 'development',
  
  // المجلدات والمسارات
  UPLOAD_FOLDER,
  OUTPUT_FOLDER,
  LOGS_FOLDER,
  
  // تكوين تحميل الملفات
  MAX_FILE_SIZE: process.env.MAX_FILE_SIZE || '50mb',
  ALLOWED_EXTENSIONS: ['png', 'jpg', 'jpeg'],
  
  // تكوين الجلسة
  SESSION_SECRET: process.env.SESSION_SECRET || 'default_secure_session_secret',
  SESSION_TIMEOUT: parseInt(process.env.SESSION_TIMEOUT) || 3600000, // ساعة واحدة بالمللي ثانية
  SESSION_CLEANUP_INTERVAL: parseInt(process.env.SESSION_CLEANUP_INTERVAL) || 21600000, // 6 ساعات
  
  // تكوين التخزين المؤقت
  CACHE_CONFIG: {
    ENABLE_CACHE: true,
    DEFAULT_TIMEOUT: 3600, // ساعة واحدة بالثواني
    CACHE_TYPE: process.env.NODE_ENV === 'production' ? 'redis' : 'memory',
    SEND_FILE_MAX_AGE_DEFAULT: 86400000, // يوم واحد بالمللي ثانية
  },
  
  // إعدادات معالجة الصور
  CANVAS_WIDTH_CM: parseFloat(process.env.CANVAS_WIDTH_CM) || 60,
  SPACING_MM: parseFloat(process.env.SPACING_MM) || 3,
  PDF_MARGIN_CM: parseFloat(process.env.PDF_MARGIN_CM) || 0.5,
  PNG_OUTPUT_DPI: parseInt(process.env.PNG_OUTPUT_DPI) || 150,
  PLACEMENT_STEP_MM: parseFloat(process.env.PLACEMENT_STEP_MM) || 5,
  ALLOW_ROTATION: process.env.ALLOW_ROTATION !== 'false',
  
  // إعدادات الأداء
  NUM_PROCESSES: process.env.NUM_PROCESSES || os.cpus().length,
  MAX_PLACEMENT_ATTEMPTS: parseInt(process.env.MAX_PLACEMENT_ATTEMPTS) || 10000,
  
  // إعدادات Redis
  REDIS_URL: process.env.REDIS_URL || 'redis://localhost:6379',
};

module.exports = config; 