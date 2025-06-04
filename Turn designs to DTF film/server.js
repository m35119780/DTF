// server.js - نقطة الدخول الرئيسية للتطبيق

// استيراد المكتبات
require('dotenv').config();
const express = require('express');
const session = require('express-session');
const RedisStore = require('connect-redis').default;
const { createClient } = require('redis');
const path = require('path');
const morgan = require('morgan');
const helmet = require('helmet');
const compression = require('compression');
const cors = require('cors');
const fs = require('fs-extra');
const config = require('./config');
const logger = require('./utils/logger');
const { setupSessionManager } = require('./utils/sessionManager');
const app = require('./app'); // استيراد تطبيق Express من app.js

const PORT = process.env.PORT || 3000;

// إعداد Redis للجلسات واتصال العمل
const redisClient = createClient({
  url: process.env.REDIS_URL || 'redis://localhost:6379'
});

// الاتصال بـ Redis
(async () => {
  try {
    await redisClient.connect();
    logger.info('Redis client connected');
  } catch (err) {
    logger.error(`Redis connection error: ${err}`);
  }
})();

// إعداد middleware
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      ...helmet.contentSecurityPolicy.getDefaultDirectives(),
      "img-src": ["'self'", "data:", "blob:"],
    }
  }
}));
app.use(compression());
app.use(cors());
app.use(express.json({ limit: config.MAX_FILE_SIZE }));
app.use(express.urlencoded({ extended: true, limit: config.MAX_FILE_SIZE }));
app.use(morgan('combined', { stream: { write: message => logger.info(message.trim()) } }));
app.use(express.static(path.join(__dirname, 'public')));

// تكوين جلسات Express مع Redis
app.use(session({
  store: new RedisStore({ client: redisClient }),
  secret: process.env.SESSION_SECRET || 'secure_session_secret',
  resave: false,
  saveUninitialized: false,
  cookie: {
    secure: process.env.NODE_ENV === 'production',
    httpOnly: true,
    maxAge: parseInt(process.env.SESSION_TIMEOUT) || 3600000
  }
}));

// إعداد مدير الجلسة
setupSessionManager(app, redisClient);

// إنشاء مجلدات التحميل والإخراج إذا لم تكن موجودة
Promise.all([
  fs.ensureDir(config.UPLOAD_FOLDER),
  fs.ensureDir(config.OUTPUT_FOLDER)
]).then(() => {
  logger.info('Upload and output directories ready');
}).catch(err => {
  logger.error(`Error creating directories: ${err}`);
});

// استيراد وتعيين المسارات
const apiRoutes = require('./routes/api');
const webRoutes = require('./routes/web');
const adminRoutes = require('./routes/admin');

app.use('/api', apiRoutes);
app.use('/', webRoutes);
app.use('/admin', adminRoutes);

// معالج الأخطاء العامة
app.use((err, req, res, next) => {
  const statusCode = err.statusCode || 500;
  logger.error(`Error ${statusCode}: ${err.message}`, { stack: err.stack });
  
  if (req.path.startsWith('/api')) {
    return res.status(statusCode).json({ 
      error: true, 
      message: err.message,
      details: process.env.NODE_ENV === 'development' ? err.stack : undefined
    });
  }
  
  res.status(statusCode).render('error', { 
    errorCode: statusCode,
    errorMessage: err.message,
    stack: process.env.NODE_ENV === 'development' ? err.stack : undefined
  });
});

// بدء الخادم
app.listen(PORT, () => {
  logger.info(`Server is running on port ${PORT}`);
  logger.info(`Environment: ${process.env.NODE_ENV}`);
}); 