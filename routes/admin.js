// routes/admin.js - مسارات الإدارة
const express = require('express');
const router = express.Router();
const { getSessionManager } = require('../utils/sessionManager');
const logger = require('../utils/logger');
const config = require('../config');
const path = require('path');
const fs = require('fs-extra');
const os = require('os');

// استرجاع مدير الجلسات
const sessionManager = getSessionManager();

// التحقق من المستخدم المسؤول
const isAdmin = (req, res, next) => {
  // للتبسيط، استخدام متغير بيئة لتحديد المستخدمين المسؤولين
  // في الواقع، يجب استخدام نظام أكثر أمانًا للمصادقة
  const adminIps = process.env.ADMIN_IPS ? process.env.ADMIN_IPS.split(',') : ['127.0.0.1', '::1'];
  
  if (adminIps.includes(req.ip)) {
    return next();
  }
  
  logger.warn(`Unauthorized admin access attempt from IP: ${req.ip}`);
  return res.status(403).render('error', {
    errorCode: 403,
    errorMessage: 'غير مصرح بالوصول إلى لوحة الإدارة'
  });
};

// صفحة الجلسات النشطة
router.get('/sessions', isAdmin, async (req, res) => {
  try {
    const sessions = sessionManager.getAllSessions();
    
    // جمع إحصائيات النظام
    const systemInfo = {
      uptime: process.uptime(),
      memoryUsage: process.memoryUsage(),
      totalMemory: os.totalmem(),
      freeMemory: os.freemem(),
      cpus: os.cpus().length,
      hostname: os.hostname(),
      platform: os.platform(),
      nodeVersion: process.version
    };
    
    // جمع إحصائيات المجلدات
    const dirStats = await getDirStats();
    
    res.render('admin_sessions', {
      title: 'إدارة الجلسات - DTF Smart Packer',
      sessions,
      systemInfo,
      dirStats
    });
  } catch (error) {
    logger.error(`Error rendering admin sessions page: ${error.message}`, { error: error.stack });
    res.render('error', {
      errorCode: 500,
      errorMessage: `حدث خطأ في صفحة إدارة الجلسات: ${error.message}`
    });
  }
});

// تنظيف الجلسات القديمة
router.post('/cleanup-old-sessions', isAdmin, async (req, res) => {
  try {
    const { ageHours } = req.body;
    const maxAgeMs = parseInt(ageHours || 24) * 60 * 60 * 1000;
    const now = Date.now();
    let cleanedCount = 0;
    
    const sessions = sessionManager.getAllSessions();
    
    for (const session of sessions) {
      const lastAccess = new Date(session.lastAccessedAt);
      const age = now - lastAccess;
      
      if (age > maxAgeMs) {
        await sessionManager.removeSession(session.id);
        cleanedCount++;
      }
    }
    
    logger.info(`Admin cleaned up ${cleanedCount} old sessions`);
    
    res.redirect('/admin/sessions?cleaned=' + cleanedCount);
  } catch (error) {
    logger.error(`Error cleaning up old sessions: ${error.message}`, { error: error.stack });
    res.render('error', {
      errorCode: 500,
      errorMessage: `حدث خطأ في تنظيف الجلسات القديمة: ${error.message}`
    });
  }
});

// حذف جلسة معينة
router.post('/delete-session/:sessionId', isAdmin, async (req, res) => {
  try {
    const { sessionId } = req.params;
    
    await sessionManager.removeSession(sessionId);
    
    logger.info(`Admin deleted session ${sessionId}`);
    
    res.redirect('/admin/sessions?deleted=' + sessionId);
  } catch (error) {
    logger.error(`Error deleting session: ${error.message}`, { sessionId: req.params.sessionId, error: error.stack });
    res.render('error', {
      errorCode: 500,
      errorMessage: `حدث خطأ في حذف الجلسة: ${error.message}`
    });
  }
});

// الحصول على إحصائيات المجلدات
async function getDirStats() {
  try {
    const uploadSize = await getDirectorySize(config.UPLOAD_FOLDER);
    const outputSize = await getDirectorySize(config.OUTPUT_FOLDER);
    const logsSize = await getDirectorySize(config.LOGS_FOLDER);
    
    return {
      uploads: {
        size: uploadSize,
        formattedSize: formatBytes(uploadSize)
      },
      outputs: {
        size: outputSize,
        formattedSize: formatBytes(outputSize)
      },
      logs: {
        size: logsSize,
        formattedSize: formatBytes(logsSize)
      },
      total: {
        size: uploadSize + outputSize + logsSize,
        formattedSize: formatBytes(uploadSize + outputSize + logsSize)
      }
    };
  } catch (error) {
    logger.error(`Error getting directory stats: ${error.message}`, { error: error.stack });
    return {
      error: error.message
    };
  }
}

// حساب حجم المجلد
async function getDirectorySize(dirPath) {
  let size = 0;
  
  try {
    if (!fs.existsSync(dirPath)) {
      return 0;
    }
    
    const files = await fs.readdir(dirPath);
    
    for (const file of files) {
      const filePath = path.join(dirPath, file);
      const stats = await fs.stat(filePath);
      
      if (stats.isDirectory()) {
        size += await getDirectorySize(filePath);
      } else {
        size += stats.size;
      }
    }
    
    return size;
  } catch (error) {
    logger.error(`Error calculating directory size: ${error.message}`, { dirPath, error: error.stack });
    return 0;
  }
}

// تنسيق أحجام الملفات
function formatBytes(bytes, decimals = 2) {
  if (bytes === 0) return '0 Bytes';
  
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
  
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

module.exports = router; 