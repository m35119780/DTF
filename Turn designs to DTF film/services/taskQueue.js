// services/taskQueue.js - نظام قائمة المهام
const Bull = require('bull');
const { v4: uuidv4 } = require('uuid');
const path = require('path');
const logger = require('../utils/logger');
const config = require('../config');
const imgProcessor = require('./imageProcessor');

// إنشاء قائمة المهام باستخدام Bull
const imageProcessingQueue = new Bull('image-processing', config.REDIS_URL);

// تخزين تقارير حالة المهام (استخدام Map بدلاً من Redis لتبسيط المثال)
const taskStatusMap = new Map();

// إعداد معالجات قائمة الانتظار
imageProcessingQueue.process(async (job) => {
  const { taskId, uploadId, files, outputDir, options } = job.data;
  logger.info(`Processing task ${taskId} for session ${uploadId}`);
  
  try {
    // تحديث حالة المهمة
    updateTaskStatus(taskId, {
      status: 'processing',
      progress: 10,
      message: 'بدء معالجة الصور...'
    });
    
    // قراءة بيانات الصور
    updateTaskStatus(taskId, {
      progress: 20,
      message: 'قراءة بيانات الصور...'
    });
    
    // وضع الصور
    updateTaskStatus(taskId, {
      progress: 40,
      message: 'تحسين مواضع الصور...'
    });
    
    const result = await imgProcessor.packImages(files, outputDir, options);
    
    // توليد الإخراج
    updateTaskStatus(taskId, {
      progress: 80,
      message: 'توليد ملفات الإخراج...'
    });
    
    // اكتمال المهمة
    updateTaskStatus(taskId, {
      status: 'completed',
      progress: 100,
      message: 'اكتملت معالجة الصور',
      result: {
        totalImages: result.totalImages,
        placedImages: result.placedImages,
        unplacedImages: result.unplacedImages,
        canvasSize: `${result.canvasWidth}cm x ${result.canvasHeight.toFixed(2)}cm`
      }
    });
    
    return result;
  } catch (error) {
    logger.error(`Task ${taskId} failed: ${error.message}`, { taskId, error: error.stack });
    
    // تحديث الحالة إلى فشل
    updateTaskStatus(taskId, {
      status: 'failed',
      error: error.message,
      message: `فشلت المعالجة: ${error.message}`
    });
    
    throw error;
  }
});

// معالجة أحداث نجاح المهمة
imageProcessingQueue.on('completed', (job, result) => {
  logger.info(`Task ${job.data.taskId} completed successfully`);
});

// معالجة أحداث فشل المهمة
imageProcessingQueue.on('failed', (job, error) => {
  logger.error(`Task ${job.data.taskId} failed: ${error.message}`, { error: error.stack });
});

// تحديث حالة المهمة
const updateTaskStatus = (taskId, updates) => {
  if (!taskStatusMap.has(taskId)) {
    taskStatusMap.set(taskId, {
      taskId,
      status: 'pending',
      progress: 0,
      message: 'في الانتظار...',
      timestamp: Date.now()
    });
  }
  
  const currentStatus = taskStatusMap.get(taskId);
  const updatedStatus = {
    ...currentStatus,
    ...updates,
    updatedAt: Date.now()
  };
  
  taskStatusMap.set(taskId, updatedStatus);
  return updatedStatus;
};

// إضافة مهمة معالجة صور جديدة إلى القائمة
const addImageProcessingTask = async (uploadId, files, outputDir, options = {}) => {
  const taskId = uuidv4();
  
  // إنشاء حالة المهمة الأولية
  updateTaskStatus(taskId, {
    status: 'pending',
    message: 'مهمة جديدة في قائمة الانتظار',
    uploadId
  });
  
  // إضافة المهمة إلى قائمة الانتظار
  await imageProcessingQueue.add({
    taskId,
    uploadId,
    files,
    outputDir,
    options
  }, {
    attempts: 2, // عدد محاولات إعادة التشغيل في حالة الفشل
    backoff: {
      type: 'fixed',
      delay: 5000 // تأخير 5 ثوانٍ بين المحاولات
    },
    removeOnComplete: true, // إزالة المهام المكتملة من القائمة
    removeOnFail: false, // الاحتفاظ بالمهام الفاشلة للإصلاح
    timeout: 600000 // محدد زمني 10 دقائق
  });
  
  logger.info(`Task ${taskId} added to queue for session ${uploadId}`);
  
  return taskId;
};

// الحصول على حالة المهمة
const getTaskStatus = async (taskId) => {
  // محاولة الحصول على الحالة من Map
  if (taskStatusMap.has(taskId)) {
    return taskStatusMap.get(taskId);
  }
  
  // محاولة الحصول على المهمة من Bull
  const job = await imageProcessingQueue.getJob(taskId);
  if (job) {
    // إذا لم تكن الحالة معروفة ولكن المهمة موجودة، احتفظ بها كـ "قيد التشغيل"
    return {
      taskId,
      status: job.isFailed() ? 'failed' : (job.isCompleted() ? 'completed' : 'processing'),
      message: job.isFailed() ? 'فشلت المهمة' : (job.isCompleted() ? 'اكتملت المهمة' : 'المهمة قيد التنفيذ'),
      timestamp: job.timestamp
    };
  }
  
  return null;
};

// تنظيف حالات المهام القديمة
const cleanupTaskStatus = () => {
  const now = Date.now();
  const MAX_AGE = 24 * 60 * 60 * 1000; // 24 ساعة
  
  for (const [taskId, status] of taskStatusMap.entries()) {
    const age = now - (status.updatedAt || status.timestamp);
    if (age > MAX_AGE && (status.status === 'completed' || status.status === 'failed')) {
      taskStatusMap.delete(taskId);
    }
  }
};

// جدولة تنظيف دوري كل ساعة
setInterval(cleanupTaskStatus, 60 * 60 * 1000);

module.exports = {
  addImageProcessingTask,
  getTaskStatus
}; 