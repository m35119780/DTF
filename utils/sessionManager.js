// utils/sessionManager.js - مدير جلسات التطبيق
const { v4: uuidv4 } = require('uuid');
const logger = require('./logger');
const config = require('../config');
const path = require('path');
const fs = require('fs-extra');

class SessionManager {
  constructor(app, redisClient) {
    this.app = app;
    this.redisClient = redisClient;
    this.sessions = new Map();
    this.timeout = config.SESSION_TIMEOUT;
    this.cleanupInterval = config.SESSION_CLEANUP_INTERVAL;
    
    // بدء مهمة التنظيف الدورية
    this.startCleanupTask();
  }

  /**
   * إنشاء جلسة جديدة أو تحديث الحالية
   * @param {Object} req - كائن الطلب
   * @returns {String} معرف الجلسة
   */
  createOrUpdateSession(req) {
    // استخدام معرف الجلسة الموجود أو إنشاء جديد
    const uploadId = req.session.uploadId || uuidv4();
    
    // تعيين معرف الجلسة في جلسة Express
    req.session.uploadId = uploadId;
    
    // إنشاء مسارات مجلدات التحميل والإخراج الخاصة بالجلسة
    const sessionUploadDir = path.join(config.UPLOAD_FOLDER, uploadId);
    const sessionOutputDir = path.join(config.OUTPUT_FOLDER, uploadId);
    
    // إنشاء المجلدات إذا لم تكن موجودة
    fs.ensureDirSync(sessionUploadDir);
    fs.ensureDirSync(sessionOutputDir);
    
    // تخزين معلومات الجلسة
    const sessionData = {
      id: uploadId,
      createdAt: new Date(),
      lastAccessedAt: new Date(),
      uploadDir: sessionUploadDir,
      outputDir: sessionOutputDir,
      uploads: [],
      ipAddress: req.ip,
      userAgent: req.headers['user-agent'],
    };
    
    // تخزين الجلسة في الذاكرة وRedis
    this.sessions.set(uploadId, sessionData);
    this.saveSessionToRedis(uploadId, sessionData);
    
    logger.debug(`Session created/updated: ${uploadId}`, { sessionId: uploadId });
    
    return uploadId;
  }

  /**
   * الحصول على معلومات الجلسة
   * @param {String} sessionId - معرف الجلسة
   * @returns {Object|null} بيانات الجلسة أو null إذا لم تكن موجودة
   */
  async getSession(sessionId) {
    // أولاً، محاولة الحصول على الجلسة من الذاكرة
    if (this.sessions.has(sessionId)) {
      const sessionData = this.sessions.get(sessionId);
      sessionData.lastAccessedAt = new Date(); // تحديث وقت آخر وصول
      
      // تحديث الجلسة في Redis
      this.saveSessionToRedis(sessionId, sessionData);
      
      return sessionData;
    }
    
    // إذا لم تكن موجودة في الذاكرة، محاولة الحصول عليها من Redis
    try {
      const sessionJson = await this.redisClient.get(`session:${sessionId}`);
      if (sessionJson) {
        const sessionData = JSON.parse(sessionJson);
        sessionData.lastAccessedAt = new Date(); // تحديث وقت آخر وصول
        
        // تخزين في الذاكرة للوصول السريع لاحقًا
        this.sessions.set(sessionId, sessionData);
        
        // تحديث في Redis بوقت الوصول الجديد
        this.saveSessionToRedis(sessionId, sessionData);
        
        return sessionData;
      }
    } catch (error) {
      logger.error(`Error retrieving session from Redis: ${error.message}`, { 
        sessionId, 
        error: error.stack 
      });
    }
    
    return null;
  }

  /**
   * تحديث بيانات الجلسة
   * @param {String} sessionId - معرف الجلسة
   * @param {Object} updates - البيانات المراد تحديثها
   */
  async updateSession(sessionId, updates) {
    try {
      const session = await this.getSession(sessionId);
      if (!session) return false;
      
      // تحديث البيانات
      Object.assign(session, updates, { lastAccessedAt: new Date() });
      
      // حفظ التغييرات
      this.sessions.set(sessionId, session);
      this.saveSessionToRedis(sessionId, session);
      
      logger.debug(`Session updated: ${sessionId}`, { sessionId });
      
      return true;
    } catch (error) {
      logger.error(`Error updating session: ${error.message}`, { 
        sessionId, 
        error: error.stack 
      });
      return false;
    }
  }

  /**
   * إزالة جلسة وتنظيف الملفات المرتبطة بها
   * @param {String} sessionId - معرف الجلسة
   */
  async removeSession(sessionId) {
    try {
      // الحصول على معلومات الجلسة قبل الإزالة
      const session = await this.getSession(sessionId);
      if (!session) return false;
      
      // إزالة الجلسة من الذاكرة وRedis
      this.sessions.delete(sessionId);
      await this.redisClient.del(`session:${sessionId}`);
      
      // تنظيف الملفات والمجلدات
      try {
        if (session.uploadDir && fs.existsSync(session.uploadDir)) {
          await fs.remove(session.uploadDir);
        }
        
        if (session.outputDir && fs.existsSync(session.outputDir)) {
          await fs.remove(session.outputDir);
        }
      } catch (fileError) {
        logger.error(`Error removing session directories: ${fileError.message}`, { 
          sessionId, 
          error: fileError.stack 
        });
      }
      
      logger.info(`Session removed: ${sessionId}`, { sessionId });
      return true;
    } catch (error) {
      logger.error(`Error removing session: ${error.message}`, { 
        sessionId, 
        error: error.stack 
      });
      return false;
    }
  }

  /**
   * حفظ الجلسة في Redis
   * @private
   */
  saveSessionToRedis(sessionId, sessionData) {
    try {
      // تعيين وقت انتهاء صلاحية Redis على نفس وقت انتهاء صلاحية الجلسة
      const ttlMs = this.timeout;
      const sessionCopy = { ...sessionData };
      
      // تحويل التواريخ إلى سلاسل ISO لـ JSON
      if (sessionCopy.createdAt instanceof Date) {
        sessionCopy.createdAt = sessionCopy.createdAt.toISOString();
      }
      if (sessionCopy.lastAccessedAt instanceof Date) {
        sessionCopy.lastAccessedAt = sessionCopy.lastAccessedAt.toISOString();
      }
      
      this.redisClient.set(
        `session:${sessionId}`, 
        JSON.stringify(sessionCopy),
        { EX: Math.floor(ttlMs / 1000) }  // تحويل المللي ثانية إلى ثوانٍ للتوافق مع Redis
      ).catch(err => {
        logger.error(`Redis session save error: ${err.message}`);
      });
    } catch (error) {
      logger.error(`Error saving session to Redis: ${error.message}`, { 
        sessionId, 
        error: error.stack 
      });
    }
  }

  /**
   * تنظيف الجلسات المنتهية الصلاحية
   * @private
   */
  async cleanupExpiredSessions() {
    logger.debug('Starting session cleanup task');
    
    const now = new Date();
    const expiredSessions = [];
    
    // تحديد الجلسات المنتهية في الذاكرة
    for (const [sessionId, sessionData] of this.sessions.entries()) {
      const lastAccess = new Date(sessionData.lastAccessedAt);
      const elapsedMs = now - lastAccess;
      
      if (elapsedMs > this.timeout) {
        expiredSessions.push(sessionId);
      }
    }
    
    // إزالة الجلسات المنتهية
    for (const sessionId of expiredSessions) {
      try {
        await this.removeSession(sessionId);
      } catch (error) {
        logger.error(`Error during cleanup for session ${sessionId}: ${error.message}`);
      }
    }
    
    if (expiredSessions.length > 0) {
      logger.info(`Cleaned up ${expiredSessions.length} expired sessions`);
    } else {
      logger.debug('No expired sessions to clean up');
    }
    
    // جدولة المهمة التالية
    setTimeout(() => this.cleanupExpiredSessions(), this.cleanupInterval);
  }

  /**
   * بدء مهمة تنظيف الجلسات المجدولة
   * @private
   */
  startCleanupTask() {
    // جدولة التنظيف الأول بعد 5 دقائق من بدء التشغيل
    setTimeout(() => this.cleanupExpiredSessions(), 300000);
    logger.info('Session cleanup task scheduled');
  }

  /**
   * استرجاع قائمة بجميع الجلسات النشطة (للإدارة)
   * @returns {Array} قائمة بجميع الجلسات
   */
  getAllSessions() {
    return Array.from(this.sessions.values());
  }
}

// كائن مدير الجلسات الواحد للتطبيق
let sessionManagerInstance = null;

/**
 * إعداد مدير الجلسات
 * @param {Object} app - تطبيق Express
 * @param {Object} redisClient - عميل Redis
 * @returns {SessionManager} نسخة مدير الجلسات
 */
function setupSessionManager(app, redisClient) {
  if (!sessionManagerInstance) {
    sessionManagerInstance = new SessionManager(app, redisClient);
    
    // إضافة Middleware لفحص الجلسات قبل كل طلب
    app.use(async (req, res, next) => {
      try {
        if (req.session && req.session.uploadId) {
          const sessionData = await sessionManagerInstance.getSession(req.session.uploadId);
          
          if (sessionData) {
            // تخزين معلومات الجلسة في res.locals للوصول إليها في المسارات
            res.locals.sessionData = sessionData;
          }
        }
        next();
      } catch (error) {
        logger.error(`Session middleware error: ${error.message}`, { error: error.stack });
        next();
      }
    });
  }
  
  return sessionManagerInstance;
}

module.exports = {
  setupSessionManager,
  getSessionManager: () => sessionManagerInstance
}; 