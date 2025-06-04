// routes/web.js - مسارات واجهة المستخدم
const express = require('express');
const router = express.Router();
const path = require('path');
const fs = require('fs-extra');
const { getSessionManager } = require('../utils/sessionManager');
const logger = require('../utils/logger');
const config = require('../config');
const { v4: uuidv4 } = require('uuid');

// استرجاع مدير الجلسات
const sessionManager = getSessionManager();

// الصفحة الرئيسية
router.get('/', (req, res) => {
  try {
    // إنشاء جلسة جديدة إذا لم تكن موجودة
    if (!req.session.uploadId) {
      const uploadId = sessionManager.createOrUpdateSession(req);
      logger.info(`New session created: ${uploadId}`);
    }
    
    res.render('index', {
      title: 'DTF Smart Packer',
      session: req.session
    });
  } catch (error) {
    logger.error(`Error rendering index page: ${error.message}`, { error: error.stack });
    res.render('error', {
      errorCode: 500,
      errorMessage: `حدث خطأ في تحميل الصفحة الرئيسية: ${error.message}`
    });
  }
});

// صفحة مراجعة الأبعاد
router.get('/review-dimensions', async (req, res) => {
  try {
    const uploadId = req.session.uploadId;
    
    if (!uploadId) {
      return res.redirect('/');
    }
    
    const sessionData = await sessionManager.getSession(uploadId);
    
    if (!sessionData || !sessionData.uploads || sessionData.uploads.length === 0) {
      return res.redirect('/');
    }
    
    res.render('review_dimensions', {
      title: 'مراجعة أبعاد الصور - DTF Smart Packer',
      uploads: sessionData.uploads,
      session: req.session
    });
  } catch (error) {
    logger.error(`Error rendering review dimensions page: ${error.message}`, { error: error.stack });
    res.render('error', {
      errorCode: 500,
      errorMessage: `حدث خطأ في صفحة مراجعة الأبعاد: ${error.message}`
    });
  }
});

// صفحة التكوين
router.get('/configure', async (req, res) => {
  try {
    const uploadId = req.session.uploadId;
    
    if (!uploadId) {
      return res.redirect('/');
    }
    
    const sessionData = await sessionManager.getSession(uploadId);
    
    if (!sessionData || !sessionData.uploads || sessionData.uploads.length === 0) {
      return res.redirect('/');
    }
    
    res.render('configure', {
      title: 'تكوين التعبئة - DTF Smart Packer',
      config: {
        canvasWidth: config.CANVAS_WIDTH_CM,
        spacing: config.SPACING_MM,
        allowRotation: config.ALLOW_ROTATION
      },
      session: req.session,
      uploadsCount: sessionData.uploads.length
    });
  } catch (error) {
    logger.error(`Error rendering configure page: ${error.message}`, { error: error.stack });
    res.render('error', {
      errorCode: 500,
      errorMessage: `حدث خطأ في صفحة التكوين: ${error.message}`
    });
  }
});

// صفحة حالة المهمة
router.get('/task-status/:taskId', async (req, res) => {
  try {
    const { taskId } = req.params;
    
    if (!req.session.uploadId) {
      return res.redirect('/');
    }
    
    res.render('task_status', {
      title: 'حالة المهمة - DTF Smart Packer',
      taskId,
      session: req.session
    });
  } catch (error) {
    logger.error(`Error rendering task status page: ${error.message}`, { taskId: req.params.taskId, error: error.stack });
    res.render('error', {
      errorCode: 500,
      errorMessage: `حدث خطأ في صفحة حالة المهمة: ${error.message}`
    });
  }
});

// صفحة النتائج
router.get('/results', async (req, res) => {
  try {
    const uploadId = req.session.uploadId;
    
    if (!uploadId) {
      return res.redirect('/');
    }
    
    const sessionData = await sessionManager.getSession(uploadId);
    
    if (!sessionData || !sessionData.currentTaskId) {
      return res.redirect('/');
    }
    
    const outputDir = sessionData.outputDir;
    
    // التحقق من وجود ملفات الإخراج
    if (!fs.existsSync(outputDir)) {
      return res.redirect(`/task-status/${sessionData.currentTaskId}`);
    }
    
    // قراءة ملفات النتائج
    const files = await fs.readdir(outputDir);
    const results = {};
    
    // التحقق من وجود ملفات الإخراج
    results.hasPNG = files.includes('output.png');
    results.hasPDF = files.includes('output.pdf');
    
    // قراءة معلومات الوضع إذا كانت موجودة
    if (files.includes('placements.txt')) {
      const placementsContent = await fs.readFile(path.join(outputDir, 'placements.txt'), 'utf-8');
      results.placementsText = placementsContent;
      
      // استخراج عدد الصور الموضعة
      const matchPlaced = placementsContent.match(/Total Images: (\d+)/);
      results.placedCount = matchPlaced ? parseInt(matchPlaced[1]) : 0;
    }
    
    // قراءة الصور غير الموضعة إذا كانت موجودة
    if (files.includes('unplaced.txt')) {
      const unplacedContent = await fs.readFile(path.join(outputDir, 'unplaced.txt'), 'utf-8');
      results.unplacedText = unplacedContent;
      
      // استخراج عدد الصور غير الموضعة
      const matchUnplaced = unplacedContent.match(/Total Unplaced: (\d+)/);
      results.unplacedCount = matchUnplaced ? parseInt(matchUnplaced[1]) : 0;
    } else {
      results.unplacedCount = 0;
    }
    
    res.render('results', {
      title: 'نتائج المعالجة - DTF Smart Packer',
      results,
      session: req.session
    });
  } catch (error) {
    logger.error(`Error rendering results page: ${error.message}`, { error: error.stack });
    res.render('error', {
      errorCode: 500,
      errorMessage: `حدث خطأ في صفحة النتائج: ${error.message}`
    });
  }
});

// عرض الصورة المصغرة
router.get('/thumbnail/:uploadId/:filename', async (req, res) => {
  try {
    const { uploadId, filename } = req.params;
    
    // التحقق من أن معرف التحميل يتطابق مع الجلسة الحالية
    if (uploadId !== req.session.uploadId) {
      return res.status(403).send('غير مصرح بالوصول');
    }
    
    const sessionData = await sessionManager.getSession(uploadId);
    
    if (!sessionData) {
      return res.status(404).send('الجلسة غير موجودة');
    }
    
    // بناء مسار الصورة المصغرة
    const thumbnailPath = path.join(sessionData.uploadDir, `thumb_${filename}`);
    
    if (!fs.existsSync(thumbnailPath)) {
      // إذا لم توجد صورة مصغرة، جرب الملف الأصلي
      const originalPath = path.join(sessionData.uploadDir, filename);
      
      if (!fs.existsSync(originalPath)) {
        return res.status(404).send('الملف غير موجود');
      }
      
      return res.sendFile(originalPath);
    }
    
    // إرسال الصورة المصغرة مع إعدادات التخزين المؤقت
    res.setHeader('Cache-Control', 'public, max-age=3600');
    res.sendFile(thumbnailPath);
  } catch (error) {
    logger.error(`Error serving thumbnail: ${error.message}`, { error: error.stack });
    res.status(500).send('خطأ في عرض الصورة المصغرة');
  }
});

// عرض صورة المعاينة
router.get('/preview/:uploadId/:filename', async (req, res) => {
  try {
    const { uploadId, filename } = req.params;
    
    // التحقق من أن معرف التحميل يتطابق مع الجلسة الحالية
    if (uploadId !== req.session.uploadId) {
      return res.status(403).send('غير مصرح بالوصول');
    }
    
    const sessionData = await sessionManager.getSession(uploadId);
    
    if (!sessionData) {
      return res.status(404).send('الجلسة غير موجودة');
    }
    
    // التحقق من نوع الملف
    let filePath;
    if (filename === 'output.png' || filename === 'output.pdf') {
      filePath = path.join(sessionData.outputDir, filename);
    } else {
      // للملفات الأخرى، ابحث في مجلد التحميل
      filePath = path.join(sessionData.uploadDir, filename);
    }
    
    if (!fs.existsSync(filePath)) {
      return res.status(404).send('الملف غير موجود');
    }
    
    // إرسال الملف مع إعدادات التخزين المؤقت
    res.setHeader('Cache-Control', 'public, max-age=3600');
    res.sendFile(filePath);
  } catch (error) {
    logger.error(`Error serving preview: ${error.message}`, { error: error.stack });
    res.status(500).send('خطأ في عرض المعاينة');
  }
});

// تحميل الملفات
router.get('/download/:fileType', async (req, res) => {
  try {
    const { fileType } = req.params;
    const uploadId = req.session.uploadId;
    
    if (!uploadId) {
      return res.status(400).send('لم يتم العثور على جلسة نشطة');
    }
    
    const sessionData = await sessionManager.getSession(uploadId);
    
    if (!sessionData) {
      return res.status(404).send('الجلسة غير موجودة');
    }
    
    const outputDir = sessionData.outputDir;
    
    // التحقق من نوع الملف المطلوب
    if (fileType === 'pdf') {
      const pdfPath = path.join(outputDir, 'output.pdf');
      if (!fs.existsSync(pdfPath)) {
        return res.status(404).send('ملف PDF غير موجود');
      }
      
      res.download(pdfPath, `dtf_packing_${uploadId}.pdf`);
    } else if (fileType === 'png') {
      const pngPath = path.join(outputDir, 'output.png');
      if (!fs.existsSync(pngPath)) {
        return res.status(404).send('ملف PNG غير موجود');
      }
      
      res.download(pngPath, `dtf_packing_${uploadId}.png`);
    } else {
      return res.status(400).send('نوع ملف غير صالح');
    }
  } catch (error) {
    logger.error(`Error downloading file: ${error.message}`, { error: error.stack });
    res.status(500).send('خطأ في تحميل الملف');
  }
});

// تنظيف الجلسة
router.get('/cleanup', async (req, res) => {
  try {
    const uploadId = req.session.uploadId;
    
    if (!uploadId) {
      return res.redirect('/');
    }
    
    // إزالة الجلسة
    await sessionManager.removeSession(uploadId);
    
    // إزالة معرف التحميل من جلسة المتصفح
    delete req.session.uploadId;
    
    res.redirect('/');
  } catch (error) {
    logger.error(`Error cleaning up session: ${error.message}`, { error: error.stack });
    res.render('error', {
      errorCode: 500,
      errorMessage: `حدث خطأ في تنظيف الجلسة: ${error.message}`
    });
  }
});

module.exports = router; 