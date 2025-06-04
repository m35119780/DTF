// routes/api.js - مسارات API للتطبيق
const express = require('express');
const router = express.Router();
const multer = require('multer');
const path = require('path');
const fs = require('fs-extra');
const { v4: uuidv4 } = require('uuid');
const logger = require('../utils/logger');
const config = require('../config');
const { getSessionManager } = require('../utils/sessionManager');
const imgProcessor = require('../services/imageProcessor');
const taskQueue = require('../services/taskQueue');

// استرجاع مدير الجلسات
const sessionManager = getSessionManager();

// تكوين تخزين Multer للتحميل
const storage = multer.diskStorage({
  destination: async function(req, file, cb) {
    try {
      // الحصول على معلومات الجلسة أو إنشاء جلسة جديدة
      const uploadId = req.session.uploadId || uuidv4();
      req.session.uploadId = uploadId;
      
      // إنشاء مجلد التحميل الخاص بالجلسة
      const sessionUploadDir = path.join(config.UPLOAD_FOLDER, uploadId);
      await fs.ensureDir(sessionUploadDir);
      
      cb(null, sessionUploadDir);
    } catch (err) {
      logger.error(`Upload directory creation failed: ${err.message}`, { error: err.stack });
      cb(err);
    }
  },
  filename: function(req, file, cb) {
    // تنظيف اسم الملف وإضافة طابع زمني
    const cleanFilename = file.originalname.replace(/[^a-zA-Z0-9_\u0600-\u06FF\-\.]/g, '_');
    cb(null, `${Date.now()}_${cleanFilename}`);
  }
});

// فلترة الملفات لقبول صور فقط
const fileFilter = (req, file, cb) => {
  const allowedExtensions = config.ALLOWED_EXTENSIONS;
  const fileExt = path.extname(file.originalname).substring(1).toLowerCase();
  
  if (allowedExtensions.includes(fileExt)) {
    cb(null, true); // قبول الملف
  } else {
    cb(new Error(`نوع الملف غير مدعوم. الأنواع المدعومة: ${allowedExtensions.join(', ')}`), false);
  }
};

// إعداد وحدة التحميل
const upload = multer({ 
  storage: storage,
  fileFilter: fileFilter,
  limits: { fileSize: parseInt(config.MAX_FILE_SIZE) || 50 * 1024 * 1024 } // 50MB افتراضيًا
});

// مسار تحميل الصور
router.post('/upload', upload.array('images', 50), async (req, res) => {
  try {
    if (!req.files || req.files.length === 0) {
      return res.status(400).json({
        error: true,
        message: 'لم يتم تقديم ملفات للتحميل'
      });
    }
    
    // إنشاء أو تحديث الجلسة
    const uploadId = sessionManager.createOrUpdateSession(req);
    const sessionData = await sessionManager.getSession(uploadId);
    
    // معالجة الملفات المحملة
    const uploadedFiles = [];
    for (const file of req.files) {
      try {
        // استخراج الأبعاد من اسم الملف
        const dimensions = await imgProcessor.extractDimensionsCm(file.originalname);
        
        // إنشاء سجل ملف التحميل
        const fileRecord = {
          id: uuidv4(),
          originalName: file.originalname,
          filename: file.filename,
          mimetype: file.mimetype,
          size: file.size,
          path: file.path,
          uploadedAt: new Date(),
          dimensions: dimensions || null
        };
        
        // إضافة إلى قائمة الملفات المحملة
        uploadedFiles.push(fileRecord);
        
        // إنشاء صورة مصغرة
        await imgProcessor.createThumbnail(file.path, path.join(sessionData.uploadDir, `thumb_${file.filename}`));
      } catch (fileErr) {
        logger.error(`Error processing uploaded file: ${fileErr.message}`, {
          filename: file.originalname,
          error: fileErr.stack
        });
      }
    }
    
    // تحديث سجلات التحميل في الجلسة
    await sessionManager.updateSession(uploadId, {
      uploads: [...(sessionData.uploads || []), ...uploadedFiles]
    });
    
    // إرسال الاستجابة
    res.status(200).json({
      success: true,
      uploadId: uploadId,
      files: uploadedFiles.map(file => ({
        id: file.id,
        name: file.originalName,
        filename: file.filename,
        size: file.size,
        dimensions: file.dimensions
      }))
    });
  } catch (error) {
    logger.error(`Upload error: ${error.message}`, { error: error.stack });
    res.status(500).json({
      error: true,
      message: `خطأ في تحميل الملفات: ${error.message}`
    });
  }
});

// تحديث أبعاد الصورة
router.post('/update-dimension', async (req, res) => {
  try {
    const { fileId, width, height } = req.body;
    const uploadId = req.session.uploadId;
    
    if (!uploadId) {
      return res.status(400).json({
        error: true,
        message: 'لم يتم العثور على جلسة نشطة'
      });
    }
    
    if (!fileId || !width || !height) {
      return res.status(400).json({
        error: true,
        message: 'البيانات المطلوبة مفقودة (fileId, width, height)'
      });
    }
    
    // الحصول على بيانات الجلسة
    const sessionData = await sessionManager.getSession(uploadId);
    if (!sessionData) {
      return res.status(404).json({
        error: true,
        message: 'لم يتم العثور على الجلسة'
      });
    }
    
    // البحث عن الملف وتحديث أبعاده
    const uploads = sessionData.uploads || [];
    const fileIndex = uploads.findIndex(file => file.id === fileId);
    
    if (fileIndex === -1) {
      return res.status(404).json({
        error: true,
        message: 'لم يتم العثور على الملف'
      });
    }
    
    // تحديث الأبعاد
    uploads[fileIndex].dimensions = {
      width: parseFloat(width),
      height: parseFloat(height),
      unit: 'cm'
    };
    
    // حفظ التغييرات
    await sessionManager.updateSession(uploadId, { uploads });
    
    res.status(200).json({
      success: true,
      fileId,
      dimensions: uploads[fileIndex].dimensions
    });
  } catch (error) {
    logger.error(`Update dimension error: ${error.message}`, { error: error.stack });
    res.status(500).json({
      error: true,
      message: `خطأ في تحديث الأبعاد: ${error.message}`
    });
  }
});

// بدء معالجة الصور
router.post('/process', async (req, res) => {
  try {
    const { spacing, allowRotation, canvasWidth } = req.body;
    const uploadId = req.session.uploadId;
    
    if (!uploadId) {
      return res.status(400).json({
        error: true,
        message: 'لم يتم العثور على جلسة نشطة'
      });
    }
    
    // الحصول على بيانات الجلسة
    const sessionData = await sessionManager.getSession(uploadId);
    if (!sessionData) {
      return res.status(404).json({
        error: true,
        message: 'لم يتم العثور على الجلسة'
      });
    }
    
    // التحقق من وجود ملفات للمعالجة
    if (!sessionData.uploads || sessionData.uploads.length === 0) {
      return res.status(400).json({
        error: true,
        message: 'لم يتم تحميل أي ملفات للمعالجة'
      });
    }
    
    // جمع خيارات المعالجة
    const processingOptions = {
      spacing: parseFloat(spacing || config.SPACING_MM),
      allowRotation: allowRotation !== undefined ? allowRotation : config.ALLOW_ROTATION,
      canvasWidth: parseFloat(canvasWidth || config.CANVAS_WIDTH_CM)
    };
    
    // إنشاء مهمة معالجة الصور
    const taskId = await taskQueue.addImageProcessingTask(
      uploadId, 
      sessionData.uploads, 
      sessionData.outputDir, 
      processingOptions
    );
    
    // تحديث الجلسة بمعرف المهمة
    await sessionManager.updateSession(uploadId, {
      currentTaskId: taskId,
      processingOptions
    });
    
    res.status(200).json({
      success: true,
      taskId,
      message: 'تمت إضافة مهمة المعالجة إلى قائمة الانتظار'
    });
  } catch (error) {
    logger.error(`Process request error: ${error.message}`, { error: error.stack });
    res.status(500).json({
      error: true,
      message: `خطأ في بدء معالجة الصور: ${error.message}`
    });
  }
});

// حالة المهمة
router.get('/task-status/:taskId', async (req, res) => {
  try {
    const { taskId } = req.params;
    
    // الحصول على حالة المهمة من Queue
    const status = await taskQueue.getTaskStatus(taskId);
    
    if (!status) {
      return res.status(404).json({
        error: true,
        message: 'لم يتم العثور على المهمة'
      });
    }
    
    res.status(200).json(status);
  } catch (error) {
    logger.error(`Task status error: ${error.message}`, { taskId: req.params.taskId, error: error.stack });
    res.status(500).json({
      error: true,
      message: `خطأ في استرجاع حالة المهمة: ${error.message}`
    });
  }
});

// عرض نتائج المعالجة
router.get('/results', async (req, res) => {
  try {
    const uploadId = req.session.uploadId;
    
    if (!uploadId) {
      return res.status(400).json({
        error: true,
        message: 'لم يتم العثور على جلسة نشطة'
      });
    }
    
    // الحصول على بيانات الجلسة
    const sessionData = await sessionManager.getSession(uploadId);
    if (!sessionData) {
      return res.status(404).json({
        error: true,
        message: 'لم يتم العثور على الجلسة'
      });
    }
    
    // التحقق من وجود مجلد النتائج
    const outputDir = sessionData.outputDir;
    if (!fs.existsSync(outputDir)) {
      return res.status(404).json({
        error: true,
        message: 'لم يتم العثور على مجلد النتائج'
      });
    }
    
    // قراءة ملفات النتائج
    const files = await fs.readdir(outputDir);
    const results = {};
    
    // فحص ملفات النتائج المختلفة
    if (files.includes('output.png')) {
      results.png = true;
    }
    
    if (files.includes('output.pdf')) {
      results.pdf = true;
    }
    
    if (files.includes('placements.txt')) {
      const placementsContent = await fs.readFile(path.join(outputDir, 'placements.txt'), 'utf-8');
      results.placements = placementsContent;
    }
    
    if (files.includes('unplaced.txt')) {
      const unplacedContent = await fs.readFile(path.join(outputDir, 'unplaced.txt'), 'utf-8');
      results.unplaced = unplacedContent.split('\n').filter(line => line.trim().length > 0);
    }
    
    res.status(200).json({
      success: true,
      results
    });
  } catch (error) {
    logger.error(`Results error: ${error.message}`, { error: error.stack });
    res.status(500).json({
      error: true,
      message: `خطأ في استرجاع النتائج: ${error.message}`
    });
  }
});

// تنظيف الجلسة
router.post('/cleanup', async (req, res) => {
  try {
    const uploadId = req.session.uploadId;
    
    if (!uploadId) {
      return res.status(400).json({
        error: true,
        message: 'لم يتم العثور على جلسة نشطة'
      });
    }
    
    // إزالة الجلسة
    const removed = await sessionManager.removeSession(uploadId);
    
    // إزالة معرف الجلسة من جلسة المتصفح
    delete req.session.uploadId;
    
    res.status(200).json({
      success: true,
      message: 'تم تنظيف الجلسة بنجاح'
    });
  } catch (error) {
    logger.error(`Cleanup error: ${error.message}`, { error: error.stack });
    res.status(500).json({
      error: true,
      message: `خطأ في تنظيف الجلسة: ${error.message}`
    });
  }
});

module.exports = router; 