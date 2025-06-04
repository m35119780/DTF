// app.js - تكوين تطبيق Express ومحرك قوالب EJS

const express = require('express');
const path = require('path');
const logger = require('./utils/logger');
const config = require('./config');

// إنشاء تطبيق Express
const app = express();

// إعداد محرك قوالب EJS
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));

// الإعدادات الافتراضية للقوالب
app.locals.title = 'DTF Film Smart Packer';

// إعداد صفحة 404 مخصصة
app.use((req, res, next) => {
  // المتابعة إذا تم العثور على المسار
  const routes = app.routes[req.method.toLowerCase()];
  if (routes) {
    const found = routes.some(route => route.match(req.path));
    if (found) {
      return next();
    }
  }
  
  // إعداد صفحة 404
  res.status(404).render('error', {
    errorCode: 404,
    errorMessage: 'الصفحة التي تبحث عنها غير موجودة.'
  });
});

// إنشاء دالة لتمرير إعدادات مشتركة للقوالب
app.use((req, res, next) => {
  // إضافة عنوان الموقع
  res.locals.siteTitle = 'DTF Film Smart Packer';
  
  // إضافة المعلومات الأساسية للمستخدم
  res.locals.user = req.session && req.session.user ? req.session.user : null;
  
  // إضافة دالة مساعدة لتنسيق التاريخ
  res.locals.formatDate = (date) => {
    return new Date(date).toLocaleString('ar-SA');
  };
  
  next();
});

// إضافة وسيلة مساعدة لتمرير رسائل الفلاش بين الصفحات
app.use((req, res, next) => {
  if (!req.session.flash) {
    req.session.flash = [];
  }
  
  // دالة لإضافة رسالة فلاش
  req.flash = (type, message) => {
    req.session.flash.push({ type, message });
  };
  
  // نقل رسائل الفلاش إلى القالب وإزالتها من الجلسة
  res.locals.flash = req.session.flash || [];
  req.session.flash = [];
  
  next();
});

// تصدير التطبيق
module.exports = app; 