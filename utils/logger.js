// utils/logger.js - وحدة تسجيل السجلات

const winston = require('winston');
const fs = require('fs-extra');
const path = require('path');
const config = require('../config');

// إنشاء مجلد السجلات إذا لم يكن موجودًا
fs.ensureDirSync(config.LOGS_FOLDER);

// تنسيق وقت السجل
const timeFormat = winston.format.timestamp({
  format: 'YYYY-MM-DD HH:mm:ss'
});

// تنسيق JSON مخصص
const jsonFormat = winston.format.printf(info => {
  const log = {
    timestamp: info.timestamp,
    level: info.level,
    message: info.message,
  };

  // إضافة معلومات السياق إذا كانت متوفرة
  if (info.context) {
    log.context = info.context;
  }

  // إضافة معلومات الخطأ إذا كانت متوفرة
  if (info.stack) {
    log.stack = info.stack;
  }

  return JSON.stringify(log);
});

// تكوين وحدة تسجيل السجلات
const logger = winston.createLogger({
  level: config.DEBUG ? 'debug' : 'info',
  format: winston.format.combine(
    timeFormat,
    winston.format.errors({ stack: true }),
    config.DEBUG ? winston.format.simple() : jsonFormat
  ),
  defaultMeta: { service: 'dtf-packer' },
  transports: [
    // سجل الأخطاء
    new winston.transports.File({
      filename: path.join(config.LOGS_FOLDER, 'error.log'),
      level: 'error',
      maxsize: 10485760, // 10 ميغابايت
      maxFiles: 10,
    }),
    // سجل عام
    new winston.transports.File({
      filename: path.join(config.LOGS_FOLDER, 'combined.log'),
      maxsize: 10485760, // 10 ميغابايت
      maxFiles: 10,
    })
  ]
});

// إضافة سجل وحدة التحكم في وضع التصحيح
if (config.DEBUG) {
  logger.add(new winston.transports.Console({
    format: winston.format.combine(
      winston.format.colorize(),
      winston.format.simple()
    )
  }));
}

// وظائف مساعدة للتسجيل مع السياق
const logWithContext = (level, message, context = {}) => {
  const logMethod = logger[level].bind(logger);
  
  if (Object.keys(context).length > 0) {
    logMethod(message, { context });
  } else {
    logMethod(message);
  }
};

// صادرات مساعدة لوظائف التسجيل
module.exports = {
  debug: (message, context = {}) => logWithContext('debug', message, context),
  info: (message, context = {}) => logWithContext('info', message, context),
  warn: (message, context = {}) => logWithContext('warn', message, context),
  error: (message, context = {}) => logWithContext('error', message, context),
  stream: {
    write: (message) => {
      logger.info(message.trim());
    }
  },
  logger // تصدير كائن winston الأصلي للاستخدام المتقدم
}; 