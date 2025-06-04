/**
 * DTF Film Smart Packer - تطبيق الواجهة الأمامية
 * يوفر تفاعل المستخدم والوظائف الديناميكية للتطبيق
 */

// عند اكتمال تحميل المستند
document.addEventListener('DOMContentLoaded', () => {
  // تهيئة المكونات المختلفة بناءً على الصفحة الحالية
  initializeUploaders();
  initializeDimensionsReview();
  initializeConfigForm();
  initializeTaskStatus();
  initializeResults();
});

/**
 * مكون تحميل الملفات - للصفحة الرئيسية
 */
function initializeUploaders() {
  const uploadForm = document.getElementById('upload-form');
  const fileInput = document.getElementById('file-input');
  const dropZone = document.getElementById('drop-zone');
  const uploadProgress = document.getElementById('upload-progress');
  const uploadStatus = document.getElementById('upload-status');
  const fileList = document.getElementById('file-list');
  
  if (!uploadForm) return;
  
  // تحميل الملفات عبر النموذج
  uploadForm.addEventListener('submit', function(e) {
    e.preventDefault();
    if (fileInput.files.length > 0) {
      uploadFiles(fileInput.files);
    } else {
      showMessage('الرجاء اختيار ملفات للتحميل', 'warning');
    }
  });
  
  // السحب والإفلات
  if (dropZone) {
    // منع السلوك الافتراضي للسحب والإفلات
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
      dropZone.addEventListener(eventName, preventDefaults, false);
    });
    
    // إضافة التأثيرات البصرية
    ['dragenter', 'dragover'].forEach(eventName => {
      dropZone.addEventListener(eventName, () => {
        dropZone.classList.add('highlight');
      }, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
      dropZone.addEventListener(eventName, () => {
        dropZone.classList.remove('highlight');
      }, false);
    });
    
    // معالجة إسقاط الملفات
    dropZone.addEventListener('drop', function(e) {
      const files = e.dataTransfer.files;
      if (files.length > 0) {
        uploadFiles(files);
      }
    }, false);
  }
  
  // وظيفة تحميل الملفات
  function uploadFiles(files) {
    // التحقق من الملفات قبل التحميل
    const validFiles = Array.from(files).filter(file => {
      const fileExt = file.name.split('.').pop().toLowerCase();
      return ['png', 'jpg', 'jpeg'].includes(fileExt);
    });
    
    if (validFiles.length === 0) {
      showMessage('لم يتم توفير ملفات صالحة. الرجاء اختيار ملفات PNG أو JPG', 'error');
      return;
    }
    
    // إعداد نموذج البيانات لإرسال الملفات
    const formData = new FormData();
    validFiles.forEach(file => {
      formData.append('images', file);
    });
    
    // إظهار شريط التقدم
    uploadProgress.style.display = 'block';
    uploadStatus.innerText = 'جاري التحميل... 0%';
    
    // إنشاء طلب XHR للتحميل
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload', true);
    
    // معالجة تقدم التحميل
    xhr.upload.onprogress = function(e) {
      if (e.lengthComputable) {
        const percentComplete = Math.round((e.loaded / e.total) * 100);
        uploadStatus.innerText = `جاري التحميل... ${percentComplete}%`;
        uploadProgress.querySelector('.progress-bar').style.width = percentComplete + '%';
      }
    };
    
    // معالجة نجاح التحميل
    xhr.onload = function() {
      if (xhr.status === 200) {
        const response = JSON.parse(xhr.responseText);
        showMessage(`تم تحميل ${response.files.length} من الملفات بنجاح.`, 'success');
        
        // إعادة تعيين شريط التقدم
        setTimeout(() => {
          uploadProgress.style.display = 'none';
          uploadStatus.innerText = '';
          uploadProgress.querySelector('.progress-bar').style.width = '0%';
        }, 1000);
        
        // عرض الملفات التي تم تحميلها
        displayUploadedFiles(response.files);
        
        // التوجيه إلى الخطوة التالية بعد التأخير
        setTimeout(() => {
          window.location.href = '/review-dimensions';
        }, 1500);
      } else {
        let errorMessage = 'حدث خطأ أثناء التحميل.';
        try {
          const response = JSON.parse(xhr.responseText);
          errorMessage = response.message || errorMessage;
        } catch (e) {}
        
        showMessage(errorMessage, 'error');
        uploadProgress.style.display = 'none';
      }
    };
    
    // معالجة أخطاء التحميل
    xhr.onerror = function() {
      showMessage('فشل الاتصال بالخادم. يرجى المحاولة مرة أخرى.', 'error');
      uploadProgress.style.display = 'none';
    };
    
    // إرسال الطلب
    xhr.send(formData);
  }
  
  // عرض قائمة الملفات التي تم تحميلها
  function displayUploadedFiles(files) {
    if (!fileList) return;
    
    fileList.innerHTML = '';
    
    files.forEach(file => {
      const fileElement = document.createElement('div');
      fileElement.className = 'file-item';
      
      let dimensions = '';
      if (file.dimensions) {
        dimensions = `${file.dimensions.width}cm × ${file.dimensions.height}cm`;
      } else {
        dimensions = 'الأبعاد غير معروفة';
      }
      
      fileElement.innerHTML = `
        <span class="file-name">${file.name}</span>
        <span class="file-dimensions">${dimensions}</span>
      `;
      
      fileList.appendChild(fileElement);
    });
    
    document.getElementById('files-container').style.display = 'block';
  }
}

/**
 * مكون مراجعة الأبعاد - لصفحة مراجعة الأبعاد
 */
function initializeDimensionsReview() {
  const dimensionForm = document.getElementById('dimensions-form');
  
  if (!dimensionForm) return;
  
  // التحقق من صحة المدخلات وتحديثها
  document.querySelectorAll('.dimension-input').forEach(input => {
    input.addEventListener('input', function() {
      validateDimension(this);
    });
    
    input.addEventListener('blur', function() {
      if (this.value && !isNaN(parseFloat(this.value)) && parseFloat(this.value) > 0) {
        updateDimension(this);
      }
    });
  });
  
  // معالجة إرسال نموذج الأبعاد
  dimensionForm.addEventListener('submit', function(e) {
    e.preventDefault();
    
    // التحقق من صحة جميع المدخلات
    let isValid = true;
    document.querySelectorAll('.dimension-input').forEach(input => {
      if (!validateDimension(input)) {
        isValid = false;
      }
    });
    
    if (!isValid) {
      showMessage('الرجاء تصحيح الأخطاء في الأبعاد قبل المتابعة.', 'warning');
      return;
    }
    
    // توجيه المستخدم إلى صفحة التكوين
    window.location.href = '/configure';
  });
  
  // التحقق من صحة أبعاد الصورة
  function validateDimension(input) {
    const value = input.value;
    const errorElement = input.parentElement.querySelector('.error-message');
    
    if (!value) {
      input.classList.add('is-invalid');
      errorElement.textContent = 'القيمة مطلوبة';
      return false;
    }
    
    const numValue = parseFloat(value);
    if (isNaN(numValue) || numValue <= 0) {
      input.classList.add('is-invalid');
      errorElement.textContent = 'يرجى إدخال رقم موجب';
      return false;
    }
    
    input.classList.remove('is-invalid');
    errorElement.textContent = '';
    return true;
  }
  
  // تحديث أبعاد الصورة عبر API
  function updateDimension(input) {
    const fileId = input.getAttribute('data-file-id');
    const dimensionType = input.getAttribute('data-dimension');
    const value = parseFloat(input.value);
    
    // الحصول على قيمتي العرض والارتفاع
    const fileContainer = input.closest('.file-dimensions-container');
    let width, height;
    
    if (dimensionType === 'width') {
      width = value;
      height = parseFloat(fileContainer.querySelector('[data-dimension="height"]').value);
    } else {
      width = parseFloat(fileContainer.querySelector('[data-dimension="width"]').value);
      height = value;
    }
    
    // التحقق من أن كلا البعدين صالحان
    if (isNaN(width) || isNaN(height) || width <= 0 || height <= 0) {
      return;
    }
    
    // إرسال طلب تحديث الأبعاد
    fetch('/api/update-dimension', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        fileId,
        width,
        height
      })
    })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        // تحديث عرض الأبعاد في واجهة المستخدم
        fileContainer.querySelector('.dimensions-display').textContent = `${width}cm × ${height}cm`;
        
        // إظهار علامة التحديث الناجح
        const successIcon = fileContainer.querySelector('.success-icon');
        successIcon.style.display = 'inline';
        setTimeout(() => {
          successIcon.style.display = 'none';
        }, 2000);
      } else {
        showMessage(`خطأ: ${data.message}`, 'error');
      }
    })
    .catch(error => {
      console.error('Error updating dimensions:', error);
      showMessage('حدث خطأ أثناء تحديث الأبعاد.', 'error');
    });
  }
}

/**
 * مكون نموذج التكوين - لصفحة التكوين
 */
function initializeConfigForm() {
  const configForm = document.getElementById('config-form');
  
  if (!configForm) return;
  
  configForm.addEventListener('submit', function(e) {
    e.preventDefault();
    
    // جمع بيانات التكوين
    const formData = {
      spacing: parseFloat(document.getElementById('spacing').value),
      canvasWidth: parseFloat(document.getElementById('canvas-width').value),
      allowRotation: document.getElementById('allow-rotation').checked
    };
    
    // التحقق من صحة البيانات
    if (isNaN(formData.spacing) || formData.spacing < 0) {
      showMessage('يرجى إدخال قيمة صالحة للمباعدة.', 'warning');
      return;
    }
    
    if (isNaN(formData.canvasWidth) || formData.canvasWidth <= 0) {
      showMessage('يرجى إدخال قيمة صالحة لعرض اللوحة.', 'warning');
      return;
    }
    
    // إظهار مؤشر التحميل
    document.getElementById('processing-indicator').style.display = 'block';
    
    // إرسال طلب المعالجة
    fetch('/api/process', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(formData)
    })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        // التوجيه إلى صفحة حالة المهمة
        window.location.href = `/task-status/${data.taskId}`;
      } else {
        document.getElementById('processing-indicator').style.display = 'none';
        showMessage(`خطأ: ${data.message}`, 'error');
      }
    })
    .catch(error => {
      document.getElementById('processing-indicator').style.display = 'none';
      console.error('Error processing images:', error);
      showMessage('حدث خطأ أثناء معالجة الصور.', 'error');
    });
  });
}

/**
 * مكون حالة المهمة - لصفحة متابعة حالة المهمة
 */
function initializeTaskStatus() {
  const taskElement = document.getElementById('task-status');
  
  if (!taskElement) return;
  
  const taskId = taskElement.getAttribute('data-task-id');
  if (!taskId) return;
  
  const progressBar = document.getElementById('task-progress-bar');
  const statusText = document.getElementById('status-text');
  const progressValue = document.getElementById('progress-value');
  
  // التحقق من حالة المهمة بشكل دوري
  let checkInterval = setInterval(checkTaskStatus, 2000);
  
  function checkTaskStatus() {
    fetch(`/api/task-status/${taskId}`)
      .then(response => response.json())
      .then(data => {
        if (data.error) {
          clearInterval(checkInterval);
          statusText.textContent = `خطأ: ${data.message}`;
          return;
        }
        
        // تحديث شريط التقدم
        if (progressBar) {
          progressBar.style.width = `${data.progress || 0}%`;
          progressValue.textContent = `${data.progress || 0}%`;
        }
        
        // تحديث نص الحالة
        if (statusText) {
          statusText.textContent = data.message || 'جاري المعالجة...';
        }
        
        // التحقق من اكتمال المهمة
        if (data.status === 'completed') {
          clearInterval(checkInterval);
          showMessage('اكتملت معالجة الصور بنجاح!', 'success');
          
          // توجيه المستخدم إلى صفحة النتائج بعد تأخير قصير
          setTimeout(() => {
            window.location.href = '/results';
          }, 1500);
        } else if (data.status === 'failed') {
          clearInterval(checkInterval);
          showMessage(`فشلت معالجة الصور: ${data.message}`, 'error');
        }
      })
      .catch(error => {
        console.error('Error checking task status:', error);
      });
  }
  
  // التحقق فورًا عند تحميل الصفحة
  checkTaskStatus();
}

/**
 * مكون النتائج - لصفحة عرض نتائج المعالجة
 */
function initializeResults() {
  const resultsContainer = document.getElementById('results-container');
  
  if (!resultsContainer) return;
  
  // تفعيل معاينة الصور المكبرة
  document.querySelectorAll('.preview-image').forEach(img => {
    img.addEventListener('click', function() {
      const previewModal = document.getElementById('preview-modal');
      const modalImage = document.getElementById('modal-image');
      
      if (previewModal && modalImage) {
        modalImage.src = this.src;
        previewModal.style.display = 'flex';
      }
    });
  });
  
  // إغلاق معاينة الصور المكبرة
  const closeModal = document.querySelector('.close-modal');
  if (closeModal) {
    closeModal.addEventListener('click', function() {
      document.getElementById('preview-modal').style.display = 'none';
    });
  }
  
  // إغلاق النافذة عند النقر خارجها
  window.addEventListener('click', function(e) {
    const modal = document.getElementById('preview-modal');
    if (modal && e.target === modal) {
      modal.style.display = 'none';
    }
  });
}

/**
 * وظائف مساعدة عامة
 */

// منع السلوك الافتراضي للأحداث
function preventDefaults(e) {
  e.preventDefault();
  e.stopPropagation();
}

// عرض رسائل التنبيه
function showMessage(message, type = 'info') {
  const alertContainer = document.getElementById('alert-container');
  if (!alertContainer) {
    // إنشاء حاوية التنبيهات إذا لم تكن موجودة
    const container = document.createElement('div');
    container.id = 'alert-container';
    container.style.position = 'fixed';
    container.style.top = '20px';
    container.style.right = '20px';
    container.style.zIndex = '1000';
    document.body.appendChild(container);
  }
  
  // إنشاء تنبيه جديد
  const alertDiv = document.createElement('div');
  alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
  alertDiv.role = 'alert';
  alertDiv.innerHTML = `
    ${message}
    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
  `;
  
  // إضافة التنبيه إلى الحاوية
  const container = document.getElementById('alert-container');
  container.appendChild(alertDiv);
  
  // إزالة التنبيه تلقائيًا بعد 5 ثوانٍ
  setTimeout(() => {
    alertDiv.classList.remove('show');
    setTimeout(() => {
      if (alertDiv.parentNode) {
        alertDiv.parentNode.removeChild(alertDiv);
      }
    }, 300);
  }, 5000);
} 