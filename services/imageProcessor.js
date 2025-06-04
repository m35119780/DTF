// services/imageProcessor.js - خدمة معالجة الصور
const sharp = require('sharp');
const { createCanvas, Image } = require('canvas');
const path = require('path');
const fs = require('fs-extra');
const logger = require('../utils/logger');
const { Worker } = require('worker_threads');
const os = require('os');
const config = require('../config');
const PDFDocument = require('pdfkit');

// استخراج الأبعاد من اسم الملف
const extractDimensionsCm = async (filename) => {
  try {
    // نمط لمطابقة الأبعاد في اسم الملف (مثال: design_9cm_x_5cm.png)
    const dimensionPattern = /(\d+\.?\d*)cm_x_(\d+\.?\d*)cm/i;
    // نمط لمطابقة بعد مربع (مثال: pattern_main_9cm.png)
    const squarePattern = /(\d+\.?\d*)cm(?!_)/i;
    
    let match = filename.match(dimensionPattern);
    if (match && match.length >= 3) {
      const width = parseFloat(match[1]);
      const height = parseFloat(match[2]);
      return { width, height, unit: 'cm' };
    }
    
    // إذا لم يتم العثور على نمط مستطيل، ابحث عن أبعاد مربعة
    match = filename.match(squarePattern);
    if (match && match.length >= 2) {
      const size = parseFloat(match[1]);
      return { width: size, height: size, unit: 'cm' };
    }
    
    // إذا لم يكن هناك أبعاد في اسم الملف
    return null;
  } catch (error) {
    logger.error(`Error extracting dimensions: ${error.message}`, { filename, error: error.stack });
    return null;
  }
};

// إنشاء صورة مصغرة
const createThumbnail = async (imagePath, outputPath, maxWidth = 200) => {
  try {
    await sharp(imagePath)
      .resize({ width: maxWidth, withoutEnlargement: true })
      .toFile(outputPath);
    
    return outputPath;
  } catch (error) {
    logger.error(`Error creating thumbnail: ${error.message}`, { imagePath, error: error.stack });
    throw error;
  }
};

// الحصول على بيانات الصورة
const getImageData = async (filepath, spacingMm) => {
  try {
    // قراءة الصورة باستخدام sharp
    const metadata = await sharp(filepath).metadata();
    const filename = path.basename(filepath);
    
    // الحصول على الأبعاد من اسم الملف أو الاعتماد على أبعاد الصورة الفعلية
    let dimensions = await extractDimensionsCm(filename);
    
    if (!dimensions) {
      // استخدام أبعاد الصورة الفعلية مع افتراض DPI 300
      const dpi = 300;
      const width = metadata.width / dpi * 2.54; // تحويل البوصة إلى سم
      const height = metadata.height / dpi * 2.54;
      
      dimensions = { width, height, unit: 'cm' };
      logger.warn(`Dimensions not found in filename, using image dimensions: ${width.toFixed(2)}cm x ${height.toFixed(2)}cm`, { filename });
    }
    
    // تحويل الأبعاد بالسنتيمتر إلى المليمتر للمعالجة
    const widthMm = dimensions.width * 10;
    const heightMm = dimensions.height * 10;
    
    // إنشاء قناع ثنائي للصورة (للكشف عن التداخل)
    const { data: mask, info } = await sharp(filepath)
      .ensureAlpha()
      .raw()
      .toBuffer({ resolveWithObject: true });
    
    return {
      id: path.basename(filepath, path.extname(filepath)),
      filename: filename,
      filepath: filepath,
      originalWidth: metadata.width,
      originalHeight: metadata.height,
      widthMm,
      heightMm,
      mask: {
        data: mask,
        width: info.width,
        height: info.height,
        channels: info.channels
      },
      dimensions
    };
  } catch (error) {
    logger.error(`Error getting image data: ${error.message}`, { filepath, error: error.stack });
    throw error;
  }
};

// التحقق من صلاحية المواقع (فحص التداخل)
const isPositionValid = (x, y, image, placements, spacingMm) => {
  // تحويل المسافة من المليمتر إلى وحدات البكسل
  const pixelsPerMm = 1; // يمكن ضبط هذا بناءً على الدقة المطلوبة
  const spacingPixels = spacingMm * pixelsPerMm;
  
  const imageWidth = image.widthMm * pixelsPerMm;
  const imageHeight = image.heightMm * pixelsPerMm;
  
  // التحقق من عدم وجود تداخل مع الصور الموجودة
  for (const placement of placements) {
    const otherImageWidth = placement.image.widthMm * pixelsPerMm;
    const otherImageHeight = placement.image.heightMm * pixelsPerMm;
    
    // التحقق من عدم وجود تداخل مع مراعاة المسافة المطلوبة
    if (
      x - spacingPixels < placement.x + otherImageWidth + spacingPixels &&
      x + imageWidth + spacingPixels > placement.x - spacingPixels &&
      y - spacingPixels < placement.y + otherImageHeight + spacingPixels &&
      y + imageHeight + spacingPixels > placement.y - spacingPixels
    ) {
      return false;
    }
  }
  
  return true;
};

// وضع الصور على اللوحة
const packImages = async (imageFiles, outputDir, options = {}) => {
  const startTime = Date.now();
  
  // استخراج الخيارات
  const spacingMm = options.spacing || config.SPACING_MM;
  const canvasWidthCm = options.canvasWidth || config.CANVAS_WIDTH_CM;
  const allowRotation = options.allowRotation !== undefined ? options.allowRotation : config.ALLOW_ROTATION;
  const placementStepMm = options.placementStepMm || config.PLACEMENT_STEP_MM;
  
  logger.info(`Starting image packing with ${imageFiles.length} images`, { options });
  
  try {
    // تحويل عرض اللوحة من السنتيمتر إلى المليمتر
    const canvasWidthMm = canvasWidthCm * 10;
    
    // معالجة الصور وجمع البيانات
    const imageDataPromises = imageFiles.map(file => getImageData(file.path, spacingMm));
    const imagesData = await Promise.all(imageDataPromises);
    
    // ترتيب الصور حسب المساحة (من الأكبر إلى الأصغر)
    imagesData.sort((a, b) => (b.widthMm * b.heightMm) - (a.widthMm * a.heightMm));
    
    // البدء بوضع الصور
    const placements = [];
    const unplaced = [];
    
    // تقدير ارتفاع اللوحة الأولي بناءً على مجموع مساحات الصور
    let totalArea = imagesData.reduce((sum, img) => sum + img.widthMm * img.heightMm, 0);
    let initialCanvasHeightMm = Math.ceil(totalArea / canvasWidthMm) * 1.2; // 20% إضافية للمساحة
    
    // وضع الصور
    for (const image of imagesData) {
      let bestScore = Number.MAX_SAFE_INTEGER;
      let bestX = 0;
      let bestY = 0;
      let bestRotation = false;
      
      // تجربة الدوران إذا كان مسموحًا به
      const orientations = allowRotation ? [false, true] : [false];
      
      for (const rotate of orientations) {
        // تدوير الأبعاد إذا لزم الأمر
        const width = rotate ? image.heightMm : image.widthMm;
        const height = rotate ? image.widthMm : image.heightMm;
        
        // لا يمكن وضع صورة أعرض من اللوحة
        if (width > canvasWidthMm) {
          continue;
        }
        
        // البحث عن الموضع الأفضل
        for (let y = 0; y <= initialCanvasHeightMm; y += placementStepMm) {
          for (let x = 0; x <= canvasWidthMm - width; x += placementStepMm) {
            if (isPositionValid(x, y, { widthMm: width, heightMm: height }, placements, spacingMm)) {
              // حساب النتيجة: الأفضلية للمواضع العليا واليسرى
              const score = y * 1000 + x;
              
              if (score < bestScore) {
                bestScore = score;
                bestX = x;
                bestY = y;
                bestRotation = rotate;
              }
            }
          }
        }
      }
      
      // إذا تم العثور على موضع صالح
      if (bestScore !== Number.MAX_SAFE_INTEGER) {
        const widthMm = bestRotation ? image.heightMm : image.widthMm;
        const heightMm = bestRotation ? image.widthMm : image.heightMm;
        
        placements.push({
          image,
          x: bestX,
          y: bestY,
          rotated: bestRotation,
          widthMm,
          heightMm
        });
      } else {
        // لم نتمكن من وضع الصورة
        unplaced.push(image);
      }
    }
    
    // حساب أبعاد اللوحة النهائية
    let canvasHeightMm = 0;
    for (const placement of placements) {
      const bottomY = placement.y + placement.heightMm;
      if (bottomY > canvasHeightMm) {
        canvasHeightMm = bottomY;
      }
    }
    
    // إضافة هامش في الأسفل
    canvasHeightMm += spacingMm;
    
    // تحويل الأبعاد إلى السنتيمتر للإخراج
    const canvasHeightCm = canvasHeightMm / 10;
    
    logger.info(`Packing complete: ${placements.length} images placed, ${unplaced.length} unplaced`, {
      canvasSize: `${canvasWidthCm}cm x ${canvasHeightCm.toFixed(2)}cm`,
      duration: `${(Date.now() - startTime) / 1000}s`
    });
    
    // توليد الإخراج
    await generateOutputs(placements, unplaced, {
      canvasWidthMm,
      canvasHeightMm,
      canvasWidthCm,
      canvasHeightCm,
      spacingMm,
      outputDir
    });
    
    return {
      placements,
      unplaced,
      canvasWidth: canvasWidthCm,
      canvasHeight: canvasHeightCm,
      totalImages: imagesData.length,
      placedImages: placements.length,
      unplacedImages: unplaced.length
    };
  } catch (error) {
    logger.error(`Image packing failed: ${error.message}`, { error: error.stack });
    throw error;
  }
};

// توليد ملفات الإخراج
const generateOutputs = async (placements, unplaced, options) => {
  try {
    const { canvasWidthMm, canvasHeightMm, canvasWidthCm, canvasHeightCm, spacingMm, outputDir } = options;
    
    // إنشاء مجلد الإخراج إذا لم يكن موجودًا
    await fs.ensureDir(outputDir);
    
    // 1. إنشاء PDF
    const pdfPath = path.join(outputDir, 'output.pdf');
    await generatePDF(placements, pdfPath, {
      widthCm: canvasWidthCm,
      heightCm: canvasHeightCm,
      marginCm: config.PDF_MARGIN_CM
    });
    
    // 2. إنشاء PNG للمعاينة
    const pngPath = path.join(outputDir, 'output.png');
    await generatePNG(placements, pngPath, {
      widthMm: canvasWidthMm,
      heightMm: canvasHeightMm,
      dpi: config.PNG_OUTPUT_DPI
    });
    
    // 3. حفظ معلومات الوضع في ملف نصي
    const placementsPath = path.join(outputDir, 'placements.txt');
    await generatePlacementsFile(placements, placementsPath);
    
    // 4. حفظ قائمة الصور غير الموضوعة
    if (unplaced.length > 0) {
      const unplacedPath = path.join(outputDir, 'unplaced.txt');
      await generateUnplacedFile(unplaced, unplacedPath);
    }
    
    logger.info(`All outputs generated in ${outputDir}`);
    
    return {
      pdfPath,
      pngPath,
      placementsPath,
      unplacedPath: unplaced.length > 0 ? path.join(outputDir, 'unplaced.txt') : null
    };
  } catch (error) {
    logger.error(`Error generating outputs: ${error.message}`, { error: error.stack });
    throw error;
  }
};

// توليد ملف PDF
const generatePDF = async (placements, outputPath, options) => {
  return new Promise((resolve, reject) => {
    try {
      const { widthCm, heightCm, marginCm } = options;
      
      // تحويل السنتيمتر إلى نقاط النظام (72pt = 1 بوصة)
      const cmToPoints = 28.35; // 1سم = 28.35 نقطة تقريبًا
      
      const pageWidthPt = widthCm * cmToPoints;
      const pageHeightPt = heightCm * cmToPoints;
      const marginPt = marginCm * cmToPoints;
      
      // إنشاء مستند PDF
      const doc = new PDFDocument({
        size: [pageWidthPt, pageHeightPt],
        margins: {
          top: marginPt,
          bottom: marginPt,
          left: marginPt,
          right: marginPt
        }
      });
      
      const writeStream = fs.createWriteStream(outputPath);
      doc.pipe(writeStream);
      
      // رسم حدود الصفحة (اختياري)
      doc.rect(marginPt, marginPt, pageWidthPt - 2 * marginPt, pageHeightPt - 2 * marginPt)
         .stroke('#CCCCCC');
      
      // وضع الصور
      for (const placement of placements) {
        const x = (placement.x / 10) * cmToPoints + marginPt;
        const y = (placement.y / 10) * cmToPoints + marginPt;
        const width = (placement.widthMm / 10) * cmToPoints;
        const height = (placement.heightMm / 10) * cmToPoints;
        
        // إضافة الصورة
        doc.image(placement.image.filepath, x, y, {
          width: width,
          height: height,
          fit: [width, height]
        });
        
        // إضافة اسم الملف كتعليق صغير (اختياري)
        doc.fontSize(5)
           .fillColor('#888888')
           .text(placement.image.filename, x, y + height + 2, { width: width });
      }
      
      // إنهاء المستند
      doc.end();
      
      // الانتظار حتى اكتمال الكتابة
      writeStream.on('finish', () => {
        resolve(outputPath);
      });
      
      writeStream.on('error', (err) => {
        reject(err);
      });
    } catch (error) {
      reject(error);
    }
  });
};

// توليد صورة PNG للمعاينة
const generatePNG = async (placements, outputPath, options) => {
  try {
    const { widthMm, heightMm, dpi } = options;
    
    // تحويل المليمترات إلى بكسل
    const mmToPixels = dpi / 25.4; // 25.4 ملم = 1 بوصة
    const widthPx = Math.ceil(widthMm * mmToPixels);
    const heightPx = Math.ceil(heightMm * mmToPixels);
    
    // إنشاء canvas
    const canvas = createCanvas(widthPx, heightPx);
    const ctx = canvas.getContext('2d');
    
    // تلوين الخلفية باللون الأبيض
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(0, 0, widthPx, heightPx);
    
    // رسم شبكة خفيفة (اختياري)
    ctx.strokeStyle = '#EEEEEE';
    const gridStep = 10 * mmToPixels; // شبكة كل 10 ملم
    
    for (let x = 0; x <= widthPx; x += gridStep) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, heightPx);
      ctx.stroke();
    }
    
    for (let y = 0; y <= heightPx; y += gridStep) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(widthPx, y);
      ctx.stroke();
    }
    
    // وضع الصور
    for (const placement of placements) {
      try {
        const x = placement.x * mmToPixels;
        const y = placement.y * mmToPixels;
        const width = placement.widthMm * mmToPixels;
        const height = placement.heightMm * mmToPixels;
        
        // تحميل الصورة باستخدام canvas
        const img = new Image();
        
        // تحميل الصورة بشكل متزامن
        const imageBuffer = await fs.readFile(placement.image.filepath);
        img.src = imageBuffer;
        
        // رسم الصورة
        if (placement.rotated) {
          // حفظ السياق
          ctx.save();
          // الانتقال إلى موضع الصورة
          ctx.translate(x + height, y);
          // التدوير بـ 90 درجة
          ctx.rotate(Math.PI / 2);
          // رسم الصورة
          ctx.drawImage(img, 0, 0, width, height);
          // استعادة السياق
          ctx.restore();
        } else {
          // رسم الصورة بدون تدوير
          ctx.drawImage(img, x, y, width, height);
        }
        
        // رسم إطار حول الصورة
        ctx.strokeStyle = '#CCCCCC';
        ctx.strokeRect(x, y, width, height);
        
        // إضافة التسمية (اختياري)
        ctx.font = '10px Arial';
        ctx.fillStyle = '#888888';
        ctx.fillText(placement.image.filename, x + 5, y + height - 5);
      } catch (imgError) {
        logger.error(`Error drawing image in PNG: ${imgError.message}`, { image: placement.image.filename });
      }
    }
    
    // حفظ الصورة
    const buffer = canvas.toBuffer('image/png');
    await fs.writeFile(outputPath, buffer);
    
    return outputPath;
  } catch (error) {
    logger.error(`Error generating PNG: ${error.message}`, { error: error.stack });
    throw error;
  }
};

// توليد ملف معلومات الوضع
const generatePlacementsFile = async (placements, outputPath) => {
  try {
    let content = 'DTF Film Smart Packer - Placements Information\n';
    content += '===========================================\n\n';
    content += `Date: ${new Date().toISOString()}\n`;
    content += `Total Images: ${placements.length}\n\n`;
    content += 'ID,Filename,X(mm),Y(mm),Width(mm),Height(mm),Rotated\n';
    content += '----------------------------------------------------\n';
    
    for (const placement of placements) {
      content += `${placement.image.id},`;
      content += `"${placement.image.filename}",`;
      content += `${placement.x.toFixed(2)},`;
      content += `${placement.y.toFixed(2)},`;
      content += `${placement.widthMm.toFixed(2)},`;
      content += `${placement.heightMm.toFixed(2)},`;
      content += `${placement.rotated ? 'Yes' : 'No'}\n`;
    }
    
    await fs.writeFile(outputPath, content);
    return outputPath;
  } catch (error) {
    logger.error(`Error generating placements file: ${error.message}`, { error: error.stack });
    throw error;
  }
};

// توليد ملف الصور غير الموضوعة
const generateUnplacedFile = async (unplaced, outputPath) => {
  try {
    let content = 'DTF Film Smart Packer - Unplaced Images\n';
    content += '======================================\n\n';
    content += `Date: ${new Date().toISOString()}\n`;
    content += `Total Unplaced: ${unplaced.length}\n\n`;
    
    for (const image of unplaced) {
      content += `${image.filename} (${image.widthMm.toFixed(2)}mm x ${image.heightMm.toFixed(2)}mm)\n`;
    }
    
    await fs.writeFile(outputPath, content);
    return outputPath;
  } catch (error) {
    logger.error(`Error generating unplaced file: ${error.message}`, { error: error.stack });
    throw error;
  }
};

// تصدير الوظائف
module.exports = {
  extractDimensionsCm,
  createThumbnail,
  getImageData,
  packImages,
  generateOutputs
}; 