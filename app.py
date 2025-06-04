from flask import Flask, request, jsonify, session, url_for, render_template, send_file, flash, redirect, abort
import os
import uuid
import cv2
import numpy as np
from PIL import Image
import time
import re
import zipfile
import shutil
import secrets
from datetime import datetime, timedelta
import io
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.units import mm, cm
from reportlab.lib.utils import ImageReader
from werkzeug.utils import secure_filename
from flask_wtf.csrf import CSRFProtect, CSRFError
import logging
from logging.handlers import RotatingFileHandler
from flask_caching import Cache
from session_manager import SessionManager
import json

# Load environment variables from .env file if it exists
from pathlib import Path
from dotenv import load_dotenv

env_path = Path('.') / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

import config  # Import the centralized config module after loading .env

app = Flask(__name__)
# Load configuration from config module
app.secret_key = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = config.OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
app.config['SESSION_COOKIE_SECURE'] = config.SESSION_COOKIE_SECURE
app.config['SESSION_COOKIE_HTTPONLY'] = config.SESSION_COOKIE_HTTPONLY
app.config['SESSION_COOKIE_SAMESITE'] = config.SESSION_COOKIE_SAMESITE
app.config['PERMANENT_SESSION_LIFETIME'] = config.PERMANENT_SESSION_LIFETIME
app.config['WTF_CSRF_TIME_LIMIT'] = config.WTF_CSRF_TIME_LIMIT
app.config['SESSION_TIMEOUT'] = config.SESSION_TIMEOUT
app.config['SESSION_CLEANUP_INTERVAL'] = config.SESSION_CLEANUP_INTERVAL

# Configure caching
app.config.from_mapping(config.CACHE_CONFIG)
cache = Cache(app)

# Configure static file caching with ETags
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = config.SEND_FILE_MAX_AGE_DEFAULT

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Initialize session manager
session_manager = SessionManager(app)

# Logging helper functions
def log_with_context(logger, level, message, **kwargs):
    """Log with additional context information"""
    # Add request context if available
    if hasattr(request, 'remote_addr'):
        kwargs['ip'] = request.remote_addr
    if hasattr(request, 'path'):
        kwargs['path'] = request.path
    if hasattr(request, 'method'):
        kwargs['method'] = request.method
    if 'upload_id' in session:
        kwargs['session_id'] = session['upload_id']

    # Get the appropriate logging method
    log_method = getattr(logger, level)
    
    # Create extra context dictionary
    extra = {'context': kwargs}
    
    # Log with context
    log_method(message, extra=extra)

def log_debug(message, **kwargs):
    """Log debug message with context"""
    log_with_context(app.logger, 'debug', message, **kwargs)

def log_info(message, **kwargs):
    """Log info message with context"""
    log_with_context(app.logger, 'info', message, **kwargs)

def log_warning(message, **kwargs):
    """Log warning message with context"""
    log_with_context(app.logger, 'warning', message, **kwargs)

def log_error(message, **kwargs):
    """Log error message with context"""
    log_with_context(app.logger, 'error', message, **kwargs)

# Configure logging
import logging
from logging.handlers import RotatingFileHandler

# Create logs directory if it doesn't exist
os.makedirs(config.LOGS_FOLDER, exist_ok=True)

# Custom JSON formatter for structured logging
class JsonFormatter(logging.Formatter):
    """Format log records as JSON for better parsing in production"""
    def format(self, record):
        log_record = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'name': record.name,
            'message': record.getMessage(),
            'pathname': record.pathname,
            'lineno': record.lineno,
            'process_id': record.process
        }
        
        # Add exception info if available
        if record.exc_info:
            log_record['exception'] = self.formatException(record.exc_info)
        
        # Add any extra attributes
        for key, value in record.__dict__.items():
            if key not in ['args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename',
                          'funcName', 'id', 'levelname', 'levelno', 'lineno', 'module',
                          'msecs', 'message', 'msg', 'name', 'pathname', 'process',
                          'processName', 'relativeCreated', 'stack_info', 'thread', 'threadName']:
                log_record[key] = value
        
        return json.dumps(log_record)

# Set up logging
if not config.DEBUG:
    # Set up file handler for production (JSON structured logging)
    file_handler = RotatingFileHandler(
        os.path.join(config.LOGS_FOLDER, 'dtf_packer.log'),
        maxBytes=10485760,  # 10MB
        backupCount=10
    )
    file_handler.setFormatter(JsonFormatter())
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)

    # Set application log level
    app.logger.setLevel(logging.INFO)
    app.logger.info('DTF Design Packer startup')
else:
    # In debug mode, log to console with more readable format
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [%(pathname)s:%(lineno)d]'
    ))
    console_handler.setLevel(logging.DEBUG)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.DEBUG)
    app.logger.debug('Debug mode active - logging to console')

# CSRF error handler
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    app.logger.warning(f"CSRF error: {str(e)}")
    return jsonify({
        'error': 'CSRF token validation failed. Please refresh the page and try again.',
        'details': str(e)
    }), 400

# Global error handlers
@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 Not Found errors."""
    if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'error': 'Resource not found', 'details': str(error)}), 404
    return render_template('error.html', error_code=404, 
                          error_message="The page you're looking for doesn't exist."), 404

@app.errorhandler(403)
def forbidden_error(error):
    """Handle 403 Forbidden errors."""
    app.logger.warning(f"403 Forbidden: {request.path} - {str(error)}")
    if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'error': 'Access forbidden', 'details': 'You don\'t have permission to access this resource.'}), 403
    return render_template('error.html', error_code=403, 
                          error_message="You don't have permission to access this page."), 403

@app.errorhandler(405)
def method_not_allowed_error(error):
    """Handle 405 Method Not Allowed errors."""
    app.logger.warning(f"405 Method Not Allowed: {request.method} {request.path}")
    return jsonify({'error': 'Method not allowed', 'details': str(error)}), 405

@app.errorhandler(429)
def too_many_requests_error(error):
    """Handle 429 Too Many Requests errors."""
    app.logger.warning(f"429 Too Many Requests: {request.remote_addr} - {request.path}")
    if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'error': 'Too many requests',
            'details': 'You have sent too many requests. Please wait before trying again.'
        }), 429
    return render_template('error.html', error_code=429, 
                          error_message="Too many requests. Please slow down."), 429

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 Internal Server Error."""
    # Log the error
    app.logger.error(f"500 error: {error}", exc_info=True)
    
    # Check if it's an API request
    if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'error': 'Internal server error', 'details': 'The server encountered an error processing your request.'}), 500
    
    # Debug mode for error template
    error_details = str(error) if config.DEBUG else None
    
    return render_template('error.html', 
                          error_code=500, 
                          error_message="Something went wrong on our end. Please try again later.",
                          debug=config.DEBUG,
                          error_details=error_details), 500

@app.errorhandler(Exception)
def handle_unhandled_exception(e):
    """Handle any unhandled exceptions."""
    # Log the error
    app.logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
    
    # Determine if it's an API request
    if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Only show detailed error in development
        error_details = str(e) if config.DEBUG else 'An unexpected error occurred'
        return jsonify({
            'error': 'Unexpected error',
            'details': error_details
        }), 500
    
    # Debug mode for error template
    error_details = str(e) if config.DEBUG else None
    
    # For regular requests, render an error page
    return render_template('error.html', 
                          error_code=500, 
                          error_message="An unexpected error occurred. Please try again later.",
                          debug=config.DEBUG,
                          error_details=error_details), 500

# Create directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

def allowed_file(filename):
    """Check if a file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg'}

def validate_file(file):
    """Comprehensive file validation to ensure security and data integrity.
    
    Args:
        file: The uploaded file object
        
    Returns:
        tuple: (is_valid, error_message)
    """
    # Check if file exists
    if not file or file.filename == '':
        return False, "No file provided"
    
    # Check filename
    filename = file.filename
    
    # Basic filename security check
    if not allowed_file(filename):
        return False, f"File type not allowed. Only PNG and JPEG images are accepted."
    
    # Check for suspicious filenames (e.g., path traversal attempts)
    if '..' in filename or '/' in filename or '\\' in filename:
        return False, "Invalid filename"
    
    # Check file size (max 20MB per file)
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)  # Reset file pointer
    
    if file_size > 20 * 1024 * 1024:  # 20MB
        return False, f"File too large. Maximum size is 20MB."
    
    # Check file content (validate it's actually an image)
    try:
        # Read the first few bytes to check file signature
        header = file.read(10)
        file.seek(0)  # Reset file pointer
        
        # PNG signature: 89 50 4E 47 0D 0A 1A 0A
        png_signature = b'\x89PNG\r\n\x1a\n'
        # JPEG signature: FF D8 FF
        jpeg_signature = b'\xff\xd8\xff'
        
        if not (header.startswith(png_signature) or header.startswith(jpeg_signature)):
            return False, "File content doesn't match expected image format"
        
        # Optional: Try to open the image to verify it's valid
        # This is more thorough but more resource-intensive
        try:
            with Image.open(file) as img:
                img.verify()  # Verify it's an image
                file.seek(0)  # Reset file pointer after verification
        except Exception:
            return False, "Invalid image file"
            
        # Reset file pointer again to be safe
        file.seek(0)
        
    except Exception as e:
        return False, f"Error validating file: {str(e)}"
    
    return True, ""

def extract_dimensions_cm(filename):
    """Extract width from filename with comprehensive pattern matching."""
    # Remove common prefixes/suffixes that might interfere
    clean_name = filename.lower().replace('_design', '').replace('design_', '')
    
    # Comprehensive patterns for width detection
    patterns = [
        # Explicit cm patterns
        r'(\d+(?:\.\d+)?)cm',                    # "5cm", "5.5cm"
        r'(\d+(?:\.\d+)?)_?cm',                  # "5_cm", "5.5_cm"
        r'w_?(\d+(?:\.\d+)?)cm',                 # "w5cm", "w_5cm"
        r'width_?(\d+(?:\.\d+)?)cm',             # "width5cm", "width_5cm"
        
        # Size in filename patterns
        r'_(\d+(?:\.\d+)?)\.(?:png|jpg|jpeg)$',  # "design_5.png"
        r'-(\d+(?:\.\d+)?)\.(?:png|jpg|jpeg)$',  # "design-5.png"
        r'(\d+(?:\.\d+)?)\.(?:png|jpg|jpeg)$',   # "5.png", "5.5.png"
        
        # Width x Height patterns (take width)
        r'(\d+(?:\.\d+)?)x\d+(?:\.\d+)?',        # "5x7", "5.5x7.2"
        r'(\d+(?:\.\d+)?)_x_\d+(?:\.\d+)?',      # "5_x_7"
        
        # Common DTF size patterns
        r'(\d+(?:\.\d+)?)inch',                  # "5inch" (convert to cm)
        r'(\d+(?:\.\d+)?)"',                     # '5"' (inches)
        r'(\d+(?:\.\d+)?)in',                    # "5in"
        
        # Special format patterns
        r'size_?(\d+(?:\.\d+)?)',                # "size5", "size_5"
        r's_?(\d+(?:\.\d+)?)',                   # "s5", "s_5"
        r'(\d+(?:\.\d+)?)_?w',                   # "5w", "5_w"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, clean_name, re.IGNORECASE)
        if match:
            try:
                width = float(match.group(1))
                if width > 0:
                    # Convert inches to cm if needed
                    if 'inch' in pattern or '"' in pattern or 'in' in pattern:
                        width = width * 2.54  # Convert inches to cm
                    
                    # Reasonable size validation (0.5cm to 100cm)
                    if 0.5 <= width <= 100:
                        return width
            except (ValueError, IndexError):
                continue
    
    # Special cases for common DTF sizes (if no pattern matches)
    special_cases = {
        'small': 5.0,
        'medium': 10.0,
        'large': 15.0,
        'xl': 20.0,
        'xxl': 25.0,
    }
    
    for size_name, width_cm in special_cases.items():
        if size_name in clean_name:
            return width_cm
    
    return None

def enhanced_get_image_data(filepath, spacing_mm, custom_width_cm=None):
    """Enhanced version that allows custom width and tracks detection info."""
    try:
        # Get width from custom input or filename detection
        if custom_width_cm:
            width_cm = float(custom_width_cm)
            detection_info = {'method': 'custom', 'width_cm': width_cm}
        else:
            width_cm = extract_dimensions_cm(os.path.basename(filepath))
            detection_info = {'method': 'filename', 'width_cm': width_cm}
        
        if not width_cm or width_cm <= 0:
            return None, {'error': 'No valid width found'}
        
        # Load and process image
        img_orig = cv2.imread(filepath, cv2.IMREAD_UNCHANGED)
        if img_orig is None:
            return None, {'error': 'Failed to load image'}
        
        h, w = img_orig.shape[:2]
        
        # Calculate dimensions in mm
        width_mm = width_cm * 10.0
        height_mm = width_mm * (h / w)
        
        # Convert to integers for pixel operations
        width_mm_int = int(round(width_mm))
        height_mm_int = int(round(height_mm))
        
        # Create mask and convert image to BGRA format (expected by generate_outputs)
        if len(img_orig.shape) == 2:  # Grayscale
            mask = (img_orig > 0).astype(np.uint8) * 255
            img_bgra = cv2.cvtColor(img_orig, cv2.COLOR_GRAY2BGRA)
        elif img_orig.shape[2] == 3:  # BGR
            mask = np.ones((img_orig.shape[0], img_orig.shape[1]), dtype=np.uint8) * 255
            img_bgra = cv2.cvtColor(img_orig, cv2.COLOR_BGR2BGRA)
            img_bgra[:, :, 3] = 255
        elif img_orig.shape[2] == 4:  # BGRA
            mask = (img_orig[:, :, 3] > 0).astype(np.uint8) * 255
            img_bgra = img_orig
        else:
            return None, {'error': f'Unsupported image format: {img_orig.shape}'}
        
        # Resize mask to match placement dimensions
        mask = cv2.resize(mask, (width_mm_int, height_mm_int), interpolation=cv2.INTER_NEAREST)
        
        detection_info.update({
            'pixel_size': f"{w}x{h}",
            'calculated_height_cm': height_mm / 10.0,
            'aspect_ratio': h / w
        })
        
        return {
            'path': filepath,
            'filename': os.path.basename(filepath),
            'img_bgra': img_bgra,  # This is what generate_outputs expects
            'mask': mask,
            'width_mm': width_mm_int,
            'height_mm': height_mm_int,
            'area_mm2': width_mm_int * height_mm_int,
            'id': os.path.basename(filepath),
            'width_cm': width_cm,
            'height_cm': height_mm / 10.0,
            'detection_info': detection_info
        }, detection_info
        
    except Exception as e:
        return None, {'error': f'Processing error: {str(e)}'}

def get_image_data(filepath, spacing_mm):
    """Original function maintained for compatibility."""
    # Use a cache key based on filepath and spacing_mm
    cache_key = f"image_data_{filepath}_{spacing_mm}"
    
    # Try to get from cache first
    cached_result = cache.get(cache_key)
    if cached_result:
        app.logger.debug(f"Cache hit for image data: {filepath}")
        return cached_result
    
    # Not in cache, compute and store
    app.logger.debug(f"Cache miss for image data: {filepath}")
    image_data, _ = enhanced_get_image_data(filepath, spacing_mm)
    
    # Only cache successful results
    if image_data:
        cache.set(cache_key, image_data)
    
    return image_data

def simple_pack_images(image_data_list, canvas_width_mm, spacing_mm=2):
    """Smart global packing algorithm that optimizes overall layout like manual arrangement."""
    # Ensure canvas width is integer
    canvas_width_mm = int(canvas_width_mm)
    spacing_mm = float(spacing_mm)
    
    log_info(f"Starting image packing algorithm", 
             image_count=len(image_data_list), 
             canvas_width_mm=canvas_width_mm, 
             spacing_mm=spacing_mm)
    
    # Prepare image data with required fields
    images = []
    for img_data in image_data_list:
        images.append({
            'id': img_data['id'],
            'filename': img_data['filename'],
            'path': img_data['path'],
            'width_mm': int(img_data['width_mm']),
            'height_mm': int(img_data['height_mm']),
            'area_mm2': int(img_data['area_mm2']),
            'img_bgra': img_data['img_bgra'],
            'mask': img_data['mask']
        })
    
    def is_position_valid(x, y, w, h, placements, exclude_id=None):
        """Check if position is valid, optionally excluding a specific placement."""
        for p in placements:
            if exclude_id and p['id'] == exclude_id:
                continue
            if not (x >= p['x_mm'] + p['width_mm'] + spacing_mm or 
                   p['x_mm'] >= x + w + spacing_mm or
                   y >= p['y_mm'] + p['height_mm'] + spacing_mm or 
                   p['y_mm'] >= y + h + spacing_mm):
                return False
        return True
    
    def calculate_layout_score(placements):
        """Score the entire layout - lower is better."""
        if not placements:
            return float('inf')
            
        # Calculate bounding box
        max_x = max(p['x_mm'] + p['width_mm'] for p in placements)
        max_y = max(p['y_mm'] + p['height_mm'] for p in placements)
        
        # Total area used by images
        total_image_area = sum(p['width_mm'] * p['height_mm'] for p in placements)
        
        # Canvas area
        canvas_area = canvas_width_mm * max_y
        
        # Efficiency score (higher efficiency = lower score)
        if canvas_area > 0:
            efficiency = total_image_area / canvas_area
            efficiency_score = (1.0 - efficiency) * 1000  # Penalty for low efficiency
        else:
            efficiency_score = 1000
        
        # Height penalty (prefer shorter layouts)
        height_score = max_y * 0.1
        
        # Width utilization bonus (reward using full width)
        width_utilization = max_x / canvas_width_mm
        width_score = (1.0 - width_utilization) * 100
        
        # Compactness score (penalize scattered layouts)
        compactness_score = 0
        for p in placements:
            # Distance from origin
            distance_score = (p['x_mm'] + p['y_mm']) * 0.01
            compactness_score += distance_score
        
        total_score = efficiency_score + height_score + width_score + compactness_score
        return total_score
    
    def find_all_positions(w, h, placements, max_positions=100):
        """Find all valid positions for an image, sorted by preference."""
        positions = []
        
        # Determine search bounds
        if placements:
            max_y = max(p['y_mm'] + p['height_mm'] for p in placements)
            search_height = max_y + h + 100
        else:
            search_height = h + 50
        
        # Use fine step size for thorough search
        step = max(1, min(3, min(w, h) // 20))
        
        # Search all positions
        tested = 0
        for y in range(0, int(search_height), step):
            if tested >= max_positions:
                break
            for x in range(0, canvas_width_mm - w + 1, step):
                if tested >= max_positions:
                    break
                    
                if is_position_valid(x, y, w, h, placements):
                    # Calculate position score
                    score = y * 2.0 + x * 0.1  # Prefer bottom-left but not too aggressively
                    
                    # Bonus for edge contact
                    if x == 0:
                        score -= 20
                    if y == 0:
                        score -= 30
                        
                    # Bonus for touching existing images
                    for p in placements:
                        # Check adjacency
                        if (abs(x + w - p['x_mm']) <= spacing_mm + 1 or 
                            abs(x - (p['x_mm'] + p['width_mm'])) <= spacing_mm + 1) and \
                           not (y + h <= p['y_mm'] - spacing_mm or y >= p['y_mm'] + p['height_mm'] + spacing_mm):
                            score -= 15
                        if (abs(y + h - p['y_mm']) <= spacing_mm + 1 or 
                            abs(y - (p['y_mm'] + p['height_mm'])) <= spacing_mm + 1) and \
                           not (x + w <= p['x_mm'] - spacing_mm or x >= p['x_mm'] + p['width_mm'] + spacing_mm):
                            score -= 20  # Prefer vertical stacking
                    
                    positions.append((x, y, score))
                    tested += 1
        
        # Sort by score (best first)
        positions.sort(key=lambda p: p[2])
        return positions[:50]  # Return top 50 positions
    
    def try_placement_strategies(images):
        """Try multiple placement strategies and return the best one."""
        strategies = [
            ("largest_first", lambda x: -x['area_mm2']),
            ("tallest_first", lambda x: -x['height_mm']),
            ("widest_first", lambda x: -x['width_mm']),
            ("smallest_first", lambda x: x['area_mm2']),
            ("balanced", lambda x: (-max(x['width_mm'], x['height_mm']), -x['area_mm2']))
        ]
        
        best_layout = None
        best_score = float('inf')
        best_strategy_name = None
        
        for strategy_name, sort_func in strategies:
            log_debug(f"Trying packing strategy: {strategy_name}")
            sorted_images = sorted(images, key=sort_func)
            
            placements = []
            
            for img in sorted_images:
                best_placement = None
                best_placement_score = float('inf')
                
                # Try both orientations
                orientations = [
                    (img['width_mm'], img['height_mm'], False),
                    (img['height_mm'], img['width_mm'], True)
                ]
                
                for w, h, rotated in orientations:
                    if w > canvas_width_mm:
                        continue
                    
                    positions = find_all_positions(w, h, placements)
                    
                    # Try top 10 positions for this orientation
                    for x, y, pos_score in positions[:10]:
                        # Create temporary placement
                        temp_placement = {
                            'id': img['id'],
                            'path': img['path'],
                            'x_mm': x,
                            'y_mm': y,
                            'width_mm': w,
                            'height_mm': h,
                            'rotated': rotated
                        }
                        
                        # Test the layout with this placement
                        test_placements = placements + [temp_placement]
                        layout_score = calculate_layout_score(test_placements)
                        
                        if layout_score < best_placement_score:
                            best_placement_score = layout_score
                            best_placement = temp_placement
                
                if best_placement:
                    placements.append(best_placement)
                    log_debug(f"Placed {img['filename']} at ({best_placement['x_mm']:.1f}, {best_placement['y_mm']:.1f}) "
                             f"size {best_placement['width_mm']}x{best_placement['height_mm']} "
                             f"{'rotated' if best_placement['rotated'] else ''}")
            
            # Score this complete layout
            if placements:
                layout_score = calculate_layout_score(placements)
                log_info(f"Strategy {strategy_name} result", 
                         images_placed=len(placements), 
                         score=layout_score)
                
                if layout_score < best_score:
                    best_score = layout_score
                    best_layout = placements
                    best_strategy_name = strategy_name
        
        log_info(f"Selected best packing strategy", 
                 strategy=best_strategy_name, 
                 score=best_score)
        return best_layout if best_layout else []
    
    def optimize_layout(placements):
        """Post-process to optimize the layout by trying to rearrange items."""
        if len(placements) <= 1:
            return placements
            
        log_info("Starting layout optimization")
        improved = True
        iterations = 0
        max_iterations = 3
        
        while improved and iterations < max_iterations:
            improved = False
            iterations += 1
            
            # Try to move each image to a better position
            for i, placement in enumerate(placements):
                current_layout_score = calculate_layout_score(placements)
                
                # Remove this placement temporarily
                temp_placements = [p for j, p in enumerate(placements) if j != i]
                
                # Find better positions for this image
                w, h = placement['width_mm'], placement['height_mm']
                positions = find_all_positions(w, h, temp_placements, max_positions=50)
                
                # Try different orientations too
                orientations = [
                    (placement['width_mm'], placement['height_mm'], placement['rotated']),
                    (placement['height_mm'], placement['width_mm'], not placement['rotated'])
                ]
                
                best_new_placement = placement
                best_new_score = current_layout_score
                
                for test_w, test_h, test_rotated in orientations:
                    if test_w > canvas_width_mm:
                        continue
                        
                    test_positions = find_all_positions(test_w, test_h, temp_placements, max_positions=30)
                    
                    for x, y, _ in test_positions[:15]:  # Try top 15 positions
                        new_placement = {
                            'id': placement['id'],
                            'path': placement['path'],
                            'x_mm': x,
                            'y_mm': y,
                            'width_mm': test_w,
                            'height_mm': test_h,
                            'rotated': test_rotated
                        }
                        
                        test_layout = temp_placements + [new_placement]
                        test_score = calculate_layout_score(test_layout)
                        
                        if test_score < best_new_score:
                            best_new_score = test_score
                            best_new_placement = new_placement
                            improved = True
                
                # Update placement if improvement found
                if improved:
                    placements[i] = best_new_placement
                    log_debug(f"Moved {placement['id']} for better layout "
                             f"(score improved by {current_layout_score - best_new_score:.1f})")
        
        log_info(f"Layout optimization completed", iterations=iterations)
        return placements
    
    # Main packing logic
    log_info("Phase 1: Starting placement strategies")
    placements = try_placement_strategies(images)
    
    if placements:
        log_info("Phase 2: Starting layout optimization")
        placements = optimize_layout(placements)
    
    # Calculate final statistics
    if placements:
        final_height = max([p['y_mm'] + p['height_mm'] for p in placements]) + spacing_mm
        total_area = sum(p['width_mm'] * p['height_mm'] for p in placements)
        canvas_area = canvas_width_mm * final_height
        efficiency = (total_area / canvas_area) * 100 if canvas_area > 0 else 0
        
        log_info("Packing completed successfully", 
                 images_placed=len(placements),
                 total_images=len(images),
                 canvas_size=f"{canvas_width_mm}x{final_height:.1f}mm", 
                 efficiency=f"{efficiency:.1f}%")
    else:
        final_height = 10
        log_warning("Packing completed with no images placed")
    
    unplaced = [img for img in images if not any(p['id'] == img['id'] for p in placements)]
    
    return {
        'placements': placements,
        'unplaced_images': unplaced,
        'final_canvas_height_mm': final_height,
        'canvas_width_mm': canvas_width_mm,
        'image_data_map': {img['id']: img for img in images}
    }

def generate_outputs(pack_result, config, output_dir):
    import time
    
    placements = pack_result['placements']
    canvas_width_mm = pack_result['canvas_width_mm']
    final_canvas_height_mm = pack_result['final_canvas_height_mm']
    image_data_map = pack_result['image_data_map']
    
    pixels_per_mm_png = (config['png_dpi'] / 25.4)
    pdf_margin_cm = config.get('pdf_margin_cm', 1.0)
    output_formats = config.get('output_formats', {
        'generate_png': True,
        'generate_pdf': True,
        'generate_svg': True,
        'generate_report': True
    })
    
    outputs = {}
    timing_info = {
        'total_start': time.time(),
        'png_time': 0,
        'svg_time': 0,
        'pdf_time': 0,
        'report_time': 0,
        'zip_time': 0,
        'total_time': 0
    }
    
    log_info(f"Starting output generation", 
             image_count=len(placements), 
             canvas_size=f"{canvas_width_mm}x{final_canvas_height_mm}mm",
             formats=','.join([k for k, v in output_formats.items() if v]))
    
    # Generate PNG
    if output_formats.get('generate_png', True):
        png_start = time.time()
        try:
            log_info("Generating PNG output")
            canvas_width_px = int(canvas_width_mm * pixels_per_mm_png)
            canvas_height_px = int(final_canvas_height_mm * pixels_per_mm_png)
            
            final_png_canvas = Image.new('RGBA', (canvas_width_px, canvas_height_px), (0, 0, 0, 0))
        
            for i, p in enumerate(placements):
                if i % 10 == 0:  # Progress indicator
                    log_debug(f"Processing PNG image {i+1}/{len(placements)}")
                    
                img_data = image_data_map.get(p['id'])
                if not img_data:
                    continue
        
                try:
                    img_bgra_orig = img_data['img_bgra']
                    if img_bgra_orig is None:
                        continue
                         
                    img_rgba_pil = Image.fromarray(cv2.cvtColor(img_bgra_orig, cv2.COLOR_BGRA2RGBA))
        
                    if p['rotated']:
                        img_rgba_pil = img_rgba_pil.rotate(90, expand=True)
        
                    target_width_px = int(p['width_mm'] * pixels_per_mm_png)
                    target_height_px = int(p['height_mm'] * pixels_per_mm_png)
        
                    img_resized = img_rgba_pil.resize((target_width_px, target_height_px), Image.Resampling.LANCZOS)
        
                    pos_x_px = int(p['x_mm'] * pixels_per_mm_png)
                    pos_y_px = int(p['y_mm'] * pixels_per_mm_png)
        
                    final_png_canvas.paste(img_resized, (pos_x_px, pos_y_px), img_resized)
        
                except Exception as e:
                    log_error(f"Error processing image for PNG", image_id=p['id'], error=str(e))
        
            png_path = os.path.join(output_dir, 'packed_output.png')
            final_png_canvas.save(png_path)
            outputs['png'] = png_path
            timing_info['png_time'] = time.time() - png_start
            log_info(f"PNG generation completed", 
                     file_size=os.path.getsize(png_path), 
                     time_taken=f"{timing_info['png_time']:.2f}s")
        
        except Exception as e:
            timing_info['png_time'] = time.time() - png_start
            log_error(f"Error generating PNG output", error=str(e))
    else:
        log_info("Skipping PNG generation (not selected)")

    # Generate SVG for Illustrator
    if output_formats.get('generate_svg', True):
        svg_start = time.time()
        try:
            log_info("Generating SVG output")
            import base64
            
            svg_path = os.path.join(output_dir, 'packed_output.svg')
            
            # Convert mm to SVG units (1mm = 3.779528 SVG units)
            svg_scale = 3.779528
            svg_width = canvas_width_mm * svg_scale
            svg_height = final_canvas_height_mm * svg_scale
            
            svg_content = [
                f'<?xml version="1.0" encoding="UTF-8"?>',
                f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"',
                f'     width="{svg_width:.2f}" height="{svg_height:.2f}"',
                f'     viewBox="0 0 {svg_width:.2f} {svg_height:.2f}">',
                f'  <!-- DTF Layout: {canvas_width_mm}mm x {final_canvas_height_mm}mm -->',
                f'  <!-- Generated by DTF Packer - {len(placements)} images placed -->',
                ''
            ]
            
            # Add each image as embedded base64
            for i, p in enumerate(placements):
                if i % 10 == 0:  # Progress indicator
                    log_debug(f"Processing SVG image {i+1}/{len(placements)}")
                    
                img_data = image_data_map.get(p['id'])
                if not img_data:
                    continue
                    
                try:
                    img_bgra_orig = img_data['img_bgra']
                    if img_bgra_orig is None:
                        continue
                        
                    img_rgba_pil = Image.fromarray(cv2.cvtColor(img_bgra_orig, cv2.COLOR_BGRA2RGBA))
                    
                    if p['rotated']:
                        img_rgba_pil = img_rgba_pil.rotate(90, expand=True)
                    
                    # Convert to base64 for embedding
                    img_buffer = io.BytesIO()
                    img_rgba_pil.save(img_buffer, format='PNG', optimize=True)
                    img_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
                    img_buffer.close()
                    
                    # Calculate SVG positions and dimensions
                    x_svg = p['x_mm'] * svg_scale
                    y_svg = p['y_mm'] * svg_scale
                    width_svg = p['width_mm'] * svg_scale
                    height_svg = p['height_mm'] * svg_scale
                    
                    # Add image to SVG
                    svg_content.extend([
                        f'  <!-- {p["id"]} - {p["width_mm"]}x{p["height_mm"]}mm {"(rotated)" if p["rotated"] else ""} -->',
                        f'  <image x="{x_svg:.2f}" y="{y_svg:.2f}" width="{width_svg:.2f}" height="{height_svg:.2f}"',
                        f'         xlink:href="data:image/png;base64,{img_base64}"/>',
                        ''
                    ])
                    
                except Exception as e:
                    log_error(f"Error processing image for SVG", image_id=p['id'], error=str(e))
            
            svg_content.append('</svg>')
            
            # Write SVG file
            with open(svg_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(svg_content))
                
            outputs['svg'] = svg_path
            timing_info['svg_time'] = time.time() - svg_start
            log_info(f"SVG generation completed", 
                     file_size=os.path.getsize(svg_path), 
                     time_taken=f"{timing_info['svg_time']:.2f}s")
            
        except Exception as e:
            timing_info['svg_time'] = time.time() - svg_start
            log_error(f"Error generating SVG output", error=str(e))
    else:
        log_info("Skipping SVG generation (not selected)")

    # Generate PDF
    if output_formats.get('generate_pdf', True):
        pdf_start = time.time()
        try:
            log_info("Generating PDF output")
            pdf_width_pt = (canvas_width_mm + 2 * pdf_margin_cm * 10) * mm
            pdf_height_pt = (final_canvas_height_mm + 2 * pdf_margin_cm * 10) * mm
            pdf_margin_pt = pdf_margin_cm * cm

            pdf_path = os.path.join(output_dir, 'packed_output.pdf')
            c = rl_canvas.Canvas(pdf_path, pagesize=(pdf_width_pt, pdf_height_pt))

            for i, p in enumerate(placements):
                if i % 10 == 0:  # Progress indicator
                    log_debug(f"Processing PDF image {i+1}/{len(placements)}")
                    
                img_data = image_data_map.get(p['id'])
                if not img_data: 
                    continue

                try:
                    img_bgra_orig = img_data['img_bgra']
                    if img_bgra_orig is None:
                        continue
                        
                    img_rgba_pil = Image.fromarray(cv2.cvtColor(img_bgra_orig, cv2.COLOR_BGRA2RGBA))

                    if p['rotated']:
                        img_rgba_pil = img_rgba_pil.rotate(90, expand=True)

                    width_pt = p['width_mm'] * mm
                    height_pt = p['height_mm'] * mm
                    x_pt = p['x_mm'] * mm + pdf_margin_pt
                    y_pt = pdf_height_pt - (p['y_mm'] * mm + pdf_margin_pt + height_pt) 

                    img_buffer = io.BytesIO()
                    try:
                        img_rgba_pil.save(img_buffer, format='PNG', optimize=False)
                        img_buffer.seek(0)
                        img_reader = ImageReader(img_buffer)

                        c.drawImage(img_reader, x_pt, y_pt, width=width_pt, height=height_pt, mask='auto')
                    finally:
                        img_buffer.close()

                except Exception as e:
                    log_error(f"Error processing image for PDF", image_id=p['id'], error=str(e))

            c.save()
            outputs['pdf'] = pdf_path
            timing_info['pdf_time'] = time.time() - pdf_start
            log_info(f"PDF generation completed", 
                     file_size=os.path.getsize(pdf_path), 
                     time_taken=f"{timing_info['pdf_time']:.2f}s")

        except Exception as e:
            timing_info['pdf_time'] = time.time() - pdf_start
            log_error(f"Error generating PDF output", error=str(e))
    else:
        log_info("Skipping PDF generation (not selected)")
    
    # Generate placement report
    if output_formats.get('generate_report', True):
        report_start = time.time()
        try:
            log_info("Generating placement report")
            report_path = os.path.join(output_dir, 'placements.txt')
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write("Filename; X (mm); Y (mm); Width (mm); Height (mm); Rotated\n")
                for p in placements:
                    f.write(f"{p['id']}; {p['x_mm']:.2f}; {p['y_mm']:.2f}; {p['width_mm']:.2f}; {p['height_mm']:.2f}; {p['rotated']}\n")
            outputs['report'] = report_path
            timing_info['report_time'] = time.time() - report_start
            log_info(f"Report generation completed", 
                     file_size=os.path.getsize(report_path), 
                     time_taken=f"{timing_info['report_time']:.2f}s")
        except Exception as e:
            timing_info['report_time'] = time.time() - report_start
            log_error(f"Error generating report", error=str(e))
    else:
        log_info("Skipping report generation (not selected)")
    
    # Calculate total time and add timing info to outputs
    timing_info['total_time'] = time.time() - timing_info['total_start']
    outputs['timing'] = timing_info
    
    # Log comprehensive timing summary
    log_info("Output generation complete", 
             total_time=f"{timing_info['total_time']:.2f}s",
             png_time=f"{timing_info['png_time']:.2f}s" if 'png' in outputs else None,
             svg_time=f"{timing_info['svg_time']:.2f}s" if 'svg' in outputs else None,
             pdf_time=f"{timing_info['pdf_time']:.2f}s" if 'pdf' in outputs else None,
             report_time=f"{timing_info['report_time']:.2f}s" if 'report' in outputs else None)
    
    return outputs

@app.before_request
def check_session_expiry():
    """Check if session is expired before each request"""
    # Skip for static files and some endpoints
    if request.path.startswith('/static/') or request.path == '/':
        return
        
    if 'upload_id' in session:
        # Check if session is still valid
        if not session_manager.is_session_valid(session['upload_id']):
            # Session expired, clean up
            flash("Your session has expired. Please start a new session.", "warning")
            return redirect(url_for('cleanup_session'))
        else:
            # Track activity to refresh timeout
            session_manager.track_activity(session['upload_id'])

@app.route('/')
def index():
    # Track index visits even without session
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    if 'files[]' not in request.files:
        return jsonify({'error': 'No files selected'}), 400

    files = request.files.getlist('files[]')
    if not files or files[0].filename == '':
        return jsonify({'error': 'No files selected'}), 400

    # Clear previous session data
    session.pop('upload_id', None)
    session.pop('file_info', None)
    
    # Create new session
    upload_id = str(uuid.uuid4())
    session_manager.create_session(upload_id)
    session['upload_id'] = upload_id
    
    upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], upload_id)
    os.makedirs(upload_dir, exist_ok=True)

    file_info = []
    uploaded_files = []
    rejected_files = []
    
    log_info(f"Starting file upload process", 
             file_count=len(files), 
             session_id=upload_id)
    
    for file in files:
        # Comprehensive file validation
        is_valid, error_message = validate_file(file)
        
        if not is_valid:
            log_warning(f"Rejected file upload", 
                       filename=file.filename, 
                       reason=error_message)
            rejected_files.append({"filename": file.filename, "reason": error_message})
            continue
            
        # Securely handle the valid file
        filename = secure_filename(file.filename)
        filepath = os.path.join(upload_dir, filename)
        
        try:
            # Save the file safely
            file.save(filepath)
            uploaded_files.append(filepath)
            
            # Try to detect dimensions
            detection_info = {
                'filename': filename,
                'filepath': filepath,
                'auto_detected': False,
                'detected_width': None,
                'needs_manual_input': True,
                'status': 'uploaded'
            }
            
            # Attempt automatic detection
            detected_width = extract_dimensions_cm(filename)
            if detected_width:
                detection_info.update({
                    'auto_detected': True,
                    'detected_width': detected_width,
                    'needs_manual_input': False,
                    'status': 'detected'
                })
                
                # Get additional image info
                try:
                    img = cv2.imread(filepath, cv2.IMREAD_UNCHANGED)
                    if img is not None:
                        h, w = img.shape[:2]
                        aspect_ratio = h / w
                        detection_info.update({
                            'pixel_dimensions': f"{w}x{h}",
                            'aspect_ratio': aspect_ratio,
                            'calculated_height': detected_width * aspect_ratio
                        })
                except Exception as img_error:
                    log_warning(f"Could not read image dimensions", 
                               filename=filename, 
                               error=str(img_error))
            
            file_info.append(detection_info)
            log_info(f"File uploaded successfully", 
                    filename=filename, 
                    filesize=os.path.getsize(filepath), 
                    auto_detection=detection_info['auto_detected'])
            
        except Exception as e:
            log_error(f"Error saving uploaded file", 
                     filename=file.filename, 
                     error=str(e))
            # Clean up any partial file that might have been created
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except:
                    pass
            rejected_files.append({"filename": file.filename, "reason": f"Error saving file: {str(e)}"})

    # If no files were successfully uploaded
    if not uploaded_files:
        # Clean up the empty directory
        try:
            os.rmdir(upload_dir)
        except:
            pass
        
        if rejected_files:
            error_message = f"All {len(rejected_files)} files were rejected. First reason: {rejected_files[0]['reason']}"
            return jsonify({'error': error_message, 'rejected_files': rejected_files}), 400
        else:
            return jsonify({'error': 'No valid files were uploaded'}), 400

    # Store in session
    session['upload_id'] = upload_id
    session['file_info'] = file_info
    
    log_info(f"Upload process completed", 
            files_uploaded=len(uploaded_files), 
            files_rejected=len(rejected_files))
    
    response_data = {
        'message': f'{len(uploaded_files)} files uploaded successfully',
        'upload_id': upload_id,
        'file_info': file_info,
        'redirect': url_for('review_dimensions')
    }
    
    # Add rejected files info if any
    if rejected_files:
        response_data['warning'] = f"{len(rejected_files)} files were rejected"
        response_data['rejected_files'] = rejected_files
    
    return jsonify(response_data)

@app.route('/review-dimensions')
def review_dimensions():
    """New page to review and edit image dimensions."""
    if 'upload_id' not in session or 'file_info' not in session:
        flash('Please upload files first.', 'warning')
        return redirect(url_for('index'))
    
    file_info = session['file_info']
    
    # Categorize files
    detected_files = [f for f in file_info if f['auto_detected']]
    manual_files = [f for f in file_info if f['needs_manual_input']]
    
    return render_template('review_dimensions.html', 
                         detected_files=detected_files,
                         manual_files=manual_files,
                         total_files=len(file_info))

@app.route('/update-dimension', methods=['POST'])
def update_dimension():
    """API endpoint to update a file's dimensions."""
    data = request.get_json()
    
    if not data or 'filename' not in data or 'width_cm' not in data:
        return jsonify({'error': 'Missing filename or width_cm'}), 400
    
    try:
        width_cm = float(data['width_cm'])
        if width_cm <= 0 or width_cm > 100:
            return jsonify({'error': 'Width must be between 0.1 and 100 cm'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid width value'}), 400
    
    filename = data['filename']
    
    # Update session data
    if 'file_info' in session:
        for file_info in session['file_info']:
            if file_info['filename'] == filename:
                file_info.update({
                    'detected_width': width_cm,
                    'needs_manual_input': False,
                    'auto_detected': False,
                    'custom_width': True,
                    'status': 'manual'
                })
                
                # Recalculate height if we have aspect ratio
                if 'aspect_ratio' in file_info:
                    file_info['calculated_height'] = width_cm * file_info['aspect_ratio']
                
                session.modified = True
                
                return jsonify({
                    'success': True,
                    'message': f'Updated {filename} to {width_cm}cm width',
                    'calculated_height': file_info.get('calculated_height')
                })
    
    return jsonify({'error': 'File not found in session'}), 404

@app.route('/process-with-dimensions', methods=['POST'])
def process_with_dimensions():
    """Process images using the reviewed dimensions."""
    if 'upload_id' not in session or 'file_info' not in session:
        return jsonify({'error': 'No upload session found'}), 400
    
    # Check if all files have dimensions
    file_info = session['file_info']
    missing_dimensions = [f['filename'] for f in file_info if f['needs_manual_input']]
    
    if missing_dimensions:
        return jsonify({
            'error': 'Some files still need dimensions',
            'missing_files': missing_dimensions
        }), 400
    
    # Get configuration from form
    canvas_width_cm = float(request.form.get('canvas_width_cm', 60))
    spacing_mm = float(request.form.get('spacing_mm', 3))
    allow_rotation = request.form.get('allow_rotation') == 'on'
    png_dpi = int(request.form.get('png_dpi', 150))
    
    # Get output format selections
    output_formats = {
        'generate_png': request.form.get('generate_png') == 'on',
        'generate_pdf': request.form.get('generate_pdf') == 'on', 
        'generate_svg': request.form.get('generate_svg') == 'on',
        'generate_report': request.form.get('generate_report') == 'on'
    }
    
    # Validate that at least one format is selected
    if not any(output_formats.values()):
        return jsonify({'error': 'Please select at least one output format'}), 400
    
    upload_id = session['upload_id']
    
    try:
        # Create configuration for asynchronous processing
        config = {
            'canvas_width_cm': canvas_width_cm,
            'spacing_mm': spacing_mm,
            'allow_rotation': allow_rotation,
            'png_dpi': png_dpi,
            'pdf_margin_cm': 1.0,
            'output_formats': output_formats
        }
        
        # Import the Celery task
        from celery_tasks import process_designs
        
        # Try asynchronous processing first
        try:
            # Test if Celery is available by pinging it
            from celery.task.control import inspect
            insp = inspect()
            if insp.ping():
                # Celery is available, use async processing
                app.logger.info("Using asynchronous processing with Celery")
                task = process_designs.delay(upload_id, config, file_info)
                
                # Store task ID in session
                session['task_id'] = task.id
                
                # Return immediate response with task ID
                return jsonify({
                    'success': True,
                    'message': 'Processing started',
                    'task_id': task.id,
                    'redirect': url_for('task_status', task_id=task.id)
                })
            else:
                # Celery workers not available, fallback to synchronous
                app.logger.warning("Celery workers not available, falling back to synchronous processing")
                raise Exception("Celery workers not available")
        except Exception as e:
            # If Celery fails, fall back to synchronous processing
            app.logger.warning(f"Falling back to synchronous processing: {str(e)}")
            
            # Process images with custom dimensions (synchronous fallback)
            upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], upload_id)
            image_data_list = []
            
            log_info("Starting synchronous image processing", 
                     file_count=len(file_info), 
                     session_id=upload_id)
            
            for file_info_item in file_info:
                filepath = file_info_item['filepath']
                custom_width = file_info_item['detected_width']
                
                if custom_width:
                    image_data, detection_info = enhanced_get_image_data(filepath, spacing_mm, custom_width)
                    if image_data:
                        image_data_list.append(image_data)
                        log_debug(f"Processed image with dimensions", 
                                 filename=file_info_item['filename'], 
                                 width_cm=custom_width)
            
            if not image_data_list:
                log_warning("No valid images to process after processing", session_id=upload_id)
                return jsonify({'error': 'No valid images to process'}), 400
            
            # Pack images
            pack_result = simple_pack_images(image_data_list, int(canvas_width_cm * 10), spacing_mm)
            
            # Generate outputs
            outputs = generate_outputs(pack_result, config, upload_dir)
            
            # Calculate summary
            summary = {
                'total_images': len(image_data_list),
                'placed_images': len(pack_result['placements']),
                'unplaced_images': len(pack_result['unplaced_images']),
                'canvas_width_mm': pack_result['canvas_width_mm'],
                'canvas_height_mm': pack_result['final_canvas_height_mm'],
                'efficiency': 0
            }
            
            if pack_result['placements']:
                total_area = sum(p['width_mm'] * p['height_mm'] for p in pack_result['placements'])
                canvas_area = summary['canvas_width_mm'] * summary['canvas_height_mm']
                summary['efficiency'] = (total_area / canvas_area) * 100 if canvas_area > 0 else 0
            
            # Create a session-safe version of pack_result (without numpy arrays)
            session_pack_result = {
                'placements': pack_result['placements'],
                'unplaced_images': [{'filename': img['filename'], 'width_mm': img['width_mm'], 'height_mm': img['height_mm']} 
                                   for img in pack_result['unplaced_images']],
                'final_canvas_height_mm': pack_result['final_canvas_height_mm'],
                'canvas_width_mm': pack_result['canvas_width_mm']
            }
            
            # Store results in session (without image data)
            session['pack_result'] = session_pack_result
            session['outputs'] = outputs
            session['summary'] = summary
            session['config'] = config
            
            return jsonify({
                'success': True,
                'message': f'Successfully processed {len(pack_result["placements"])} images (synchronous mode)',
                'redirect': url_for('show_results')
            })
        
    except Exception as e:
        app.logger.error(f"Error starting processing task: {e}", exc_info=True)
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500

@app.route('/task-status/<task_id>')
def task_status(task_id):
    """Show the status of an asynchronous processing task."""
    # Import the task status checker
    from celery_tasks import get_task_status
    
    # Check if this is the current user's task
    if 'task_id' not in session or session['task_id'] != task_id:
        flash('Invalid task ID or session expired', 'warning')
        return redirect(url_for('index'))
    
    return render_template('task_status.html', task_id=task_id)

@app.route('/api/task-status/<task_id>')
def api_task_status(task_id):
    """API endpoint to get the current status of a task."""
    # Import the task status checker
    from celery_tasks import get_task_status
    
    # Check if this is the current user's task
    if 'task_id' not in session or session['task_id'] != task_id:
        return jsonify({'error': 'Invalid task ID or session expired'}), 403
    
    # Get task status
    status_data = get_task_status(task_id)
    
    if not status_data:
        return jsonify({'status': 'UNKNOWN', 'message': 'Task not found'}), 404
    
    # Check if task completed successfully
    if status_data.get('status') == 'SUCCESS' and status_data.get('result'):
        # Store results in session
        result = status_data['result']
        session['pack_result'] = result.get('pack_result')
        session['outputs'] = result.get('outputs')
        session['summary'] = result.get('summary')
        session['config'] = result.get('config')
        
        # Add redirect to results page
        status_data['redirect'] = url_for('show_results')
    
    pack_result = session['pack_result']
    outputs = session['outputs']
    summary = session.get('summary', {})
    config = session.get('config', {})
    
    return render_template('results.html', 
                         pack_result=pack_result,
                         outputs=outputs,
                         summary=summary,
                         config=config)

@app.route('/configure')
def configure():
    """Configuration page for DTF layout settings."""
    if 'upload_id' not in session or 'file_info' not in session:
        flash('Please upload files first.', 'warning')
        return redirect(url_for('index'))
    
    file_info = session['file_info']
    
    # Get list of filenames for display
    files = [f['filename'] for f in file_info]
    
    return render_template('configure.html', files=files)

@app.route('/process', methods=['POST'])
def process_images():
    """Legacy route - redirect to new flow."""
    return redirect(url_for('process_with_dimensions'))

@app.route('/download/<file_type>')
def download_individual(file_type):
    """Download individual files (pdf, png, or report)."""
    if 'upload_id' not in session or 'outputs' not in session:
        flash('No results to download')
        return redirect(url_for('show_results'))
    
    outputs = session['outputs']
    
    if file_type not in outputs:
        # Get configuration to check if this format was selected
        config = session.get('config', {})
        output_formats = config.get('output_formats', {})
        
        # Check if this format was deliberately not selected
        format_key = f'generate_{file_type}'
        if format_key in output_formats and not output_formats[format_key]:
            flash(f'{file_type.upper()} file was not generated because it was not selected in your configuration', 'warning')
        else:
            flash(f'{file_type.upper()} file not available', 'danger')
            
        return redirect(url_for('show_results'))
    
    filepath = outputs[file_type]
    if not os.path.exists(filepath):
        flash(f'{file_type.upper()} file not found on server', 'danger')
        return redirect(url_for('show_results'))
    
    # Set appropriate download name
    filename_map = {
        'pdf': 'packed_output.pdf',
        'png': 'packed_output.png',
        'svg': 'packed_output.svg',
        'report': 'placements.txt'
    }
    
    download_name = filename_map.get(file_type, os.path.basename(filepath))
    
    return send_file(filepath, as_attachment=True, download_name=download_name)

@app.route('/cleanup')
def cleanup_session():
    """Clean up session data and redirect to home."""
    try:
        # Use session manager to end the session
        if 'upload_id' in session:
            upload_id = session['upload_id']
            session_manager.end_session(upload_id)
        
        # Clear session data
        session.clear()
        flash('Session cleaned up successfully')
        
    except Exception as e:
        app.logger.error(f"Error during cleanup: {e}")
        flash('Cleanup completed with some errors')
    
    return redirect(url_for('index'))

@app.route('/preview/<upload_id>/<filename>')
@cache.cached(timeout=3600, query_string=True)  # Cache previews for 1 hour
def get_preview_image(upload_id, filename):
    """Serve full-size preview of the uploaded image for modal display."""
    try:
        # Security check
        filename = secure_filename(filename)
        
        # Check if upload_id matches current session
        if 'upload_id' not in session or session['upload_id'] != upload_id:
            return jsonify({'error': 'Invalid session'}), 403
        
        # Build file path
        upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], upload_id)
        filepath = os.path.join(upload_dir, filename)
        
        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404
        
        # Load image
        img = cv2.imread(filepath, cv2.IMREAD_UNCHANGED)
        if img is None:
            return jsonify({'error': 'Cannot read image'}), 400
        
        # Convert to PIL for processing
        if len(img.shape) == 2:  # Grayscale
            img_pil = Image.fromarray(img, mode='L')
            img_pil = img_pil.convert('RGBA')
        elif img.shape[2] == 3:  # BGR
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(img_rgb, mode='RGB')
            img_pil = img_pil.convert('RGBA')
        elif img.shape[2] == 4:  # BGRA
            img_rgba = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
            img_pil = Image.fromarray(img_rgba, mode='RGBA')
        else:
            return jsonify({'error': 'Unsupported image format'}), 400
        
        # Resize for preview if too large (max 800px on longest side)
        max_size = 800
        if max(img_pil.width, img_pil.height) > max_size:
            img_pil.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        # Convert to bytes
        img_buffer = io.BytesIO()
        img_pil.save(img_buffer, format='PNG', optimize=True)
        img_buffer.seek(0)
        
        return send_file(
            img_buffer,
            mimetype='image/png',
            as_attachment=False,
            download_name=f'preview_{filename}'
        )
        
    except Exception as e:
        print(f"Error generating preview for {filename}: {e}")
        return jsonify({'error': 'Preview generation failed'}), 500

@app.route('/thumbnail/<upload_id>/<filename>')
@cache.cached(timeout=3600, query_string=True)  # Cache thumbnails for 1 hour
def get_thumbnail(upload_id, filename):
    """Generate and serve a thumbnail of the uploaded image with transparent background."""
    try:
        # Security check - ensure filename is safe
        filename = secure_filename(filename)
        
        # Check if upload_id matches current session
        if 'upload_id' not in session or session['upload_id'] != upload_id:
            return jsonify({'error': 'Invalid session'}), 403
        
        # Build file path
        upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], upload_id)
        filepath = os.path.join(upload_dir, filename)
        
        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404
        
        # Load image
        img = cv2.imread(filepath, cv2.IMREAD_UNCHANGED)
        if img is None:
            return jsonify({'error': 'Cannot read image'}), 400
        
        # Convert to PIL for easier thumbnail generation
        if len(img.shape) == 2:  # Grayscale
            img_pil = Image.fromarray(img, mode='L')
            # Convert to RGBA to add transparency
            img_pil = img_pil.convert('RGBA')
        elif img.shape[2] == 3:  # BGR
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(img_rgb, mode='RGB')
            # Convert to RGBA and make white background transparent
            img_pil = img_pil.convert('RGBA')
            # Make white/light colors transparent for better display
            datas = img_pil.getdata()
            newData = []
            for item in datas:
                # Make near-white pixels transparent
                if item[0] > 240 and item[1] > 240 and item[2] > 240:
                    newData.append((255, 255, 255, 0))  # Transparent
                else:
                    newData.append(item)
            img_pil.putdata(newData)
        elif img.shape[2] == 4:  # BGRA
            img_rgba = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
            img_pil = Image.fromarray(img_rgba, mode='RGBA')
        else:
            return jsonify({'error': 'Unsupported image format'}), 400
        
        # Create thumbnail (80x80) while maintaining aspect ratio
        thumbnail_size = (80, 80)
        img_pil.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
        
        # Create a new image with transparent background
        thumbnail = Image.new('RGBA', thumbnail_size, (0, 0, 0, 0))
        
        # Calculate position to center the image
        paste_x = (thumbnail_size[0] - img_pil.width) // 2
        paste_y = (thumbnail_size[1] - img_pil.height) // 2
        
        # Paste the image onto the transparent background
        thumbnail.paste(img_pil, (paste_x, paste_y), img_pil if img_pil.mode == 'RGBA' else None)
        
        # Convert to bytes
        img_buffer = io.BytesIO()
        thumbnail.save(img_buffer, format='PNG', optimize=True)
        img_buffer.seek(0)
        
        return send_file(
            img_buffer,
            mimetype='image/png',
            as_attachment=False,
            download_name=f'thumb_{filename}'
        )
        
    except Exception as e:
        print(f"Error generating thumbnail for {filename}: {e}")
        return jsonify({'error': 'Thumbnail generation failed'}), 500

@app.route('/download')
def download_results():
    import time
    
    if 'upload_id' not in session or 'outputs' not in session:
        flash('No results to download')
        return redirect(url_for('show_results'))
    
    upload_id = session['upload_id']
    outputs = session['outputs']
    
    zip_path = os.path.join(app.config['OUTPUT_FOLDER'], f'{upload_id}_results.zip')
    
    try:
        zip_start = time.time()
        log_info("Generating ZIP file for download", session_id=upload_id)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
            for output_type, filepath in outputs.items():
                if output_type == 'timing':  # Skip timing info
                    continue
                    
                if os.path.exists(filepath):
                    archive_name = os.path.basename(filepath)
                    zipf.write(filepath, archive_name)
                    log_debug(f"Added {archive_name} to ZIP file", file_size=os.path.getsize(filepath))
        
        zip_time = time.time() - zip_start
        log_info(f"ZIP file created", 
                 time_taken=f"{zip_time:.2f}s", 
                 file_size=os.path.getsize(zip_path))
        
        # Update timing info in session if available
        if 'timing' in outputs:
            outputs['timing']['zip_time'] = zip_time
            session['outputs'] = outputs
        
        if not os.path.exists(zip_path):
            flash('Error creating download file')
            return redirect(url_for('show_results'))
            
        filename = f'packing_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        log_info(f"Sending download file to client", filename=filename, file_size=os.path.getsize(zip_path))
        return send_file(zip_path, as_attachment=True, download_name=filename)
        
    except Exception as e:
        log_error(f"Error creating ZIP file", error=str(e))
        flash('Error creating download file')
        return redirect(url_for('show_results'))

@app.route('/show-results')
def show_results():
    """Display the packing results with download options."""
    if 'pack_result' not in session or 'outputs' not in session:
        flash('No results found. Please process images first.', 'warning')
        return redirect(url_for('index'))
    
    pack_result = session['pack_result']
    outputs = session['outputs']
    summary = session.get('summary', {})
    config = session.get('config', {})
    
    return render_template('results.html', 
                         pack_result=pack_result,
                         outputs=outputs,
                         summary=summary,
                         config=config)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
    
# Test routes for error handlers (only available in debug mode)
@app.route('/test/error/<error_type>')
def test_error(error_type):
    """Test route to trigger various errors (only available in debug mode)."""
    if not app.debug:
        return redirect(url_for('index'))
        
    if error_type == '404':
        abort(404)
    elif error_type == '403':
        abort(403)
    elif error_type == '405':
        abort(405)
    elif error_type == '429':
        abort(429)
    elif error_type == '500':
        abort(500)
    elif error_type == 'exception':
        # Raise a custom exception
        raise Exception("This is a test exception")
    elif error_type == 'zerodivision':
        # Raise a zero division error
        return 1 / 0
    elif error_type == 'keyerror':
        # Raise a key error
        empty_dict = {}
        return empty_dict['nonexistent_key']
    else:
        return jsonify({'message': 'Unknown error type. Use: 404, 403, 500, exception, zerodivision, keyerror'})

@app.route('/admin/sessions')
def admin_sessions():
    """Admin route to view session statistics and management options."""
    # Only available in debug mode with admin password
    admin_password = os.environ.get('ADMIN_PASSWORD')
    provided_password = request.args.get('key')
    
    if not app.debug and (not admin_password or provided_password != admin_password):
        abort(403)
    
    # Get session statistics
    stats = session_manager.get_session_stats()
    
    # Add system information
    stats['upload_folder_size'] = get_directory_size(app.config['UPLOAD_FOLDER'])
    stats['output_folder_size'] = get_directory_size(app.config['OUTPUT_FOLDER'])
    stats['session_timeout'] = app.config['SESSION_TIMEOUT']
    stats['cleanup_interval'] = app.config['SESSION_CLEANUP_INTERVAL']
    
    # Get some active session details (limit to 10)
    session_data = session_manager._read_session_data()
    current_time = time.time()
    active_sessions = []
    
    for session_id, info in session_data.items():
        if (current_time - info['last_activity']) < app.config['SESSION_TIMEOUT']:
            active_sessions.append({
                'id': session_id,
                'age': format_time_delta(current_time - info['created']),
                'last_activity': format_time_delta(current_time - info['last_activity'])
            })
            if len(active_sessions) >= 10:
                break
    
    stats['active_session_details'] = active_sessions
    
    # Check if cleanup action was requested
    action = request.args.get('action')
    if action == 'cleanup':
        count = session_manager.cleanup_expired_sessions()
        flash(f'Cleaned up {count} expired sessions')
        return redirect(url_for('admin_sessions', key=provided_password))
    
    return render_template('admin_sessions.html', stats=stats)

def get_directory_size(path):
    """Get the size of a directory in bytes."""
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp):
                    total_size += os.path.getsize(fp)
    except Exception as e:
        app.logger.error(f"Error calculating directory size: {e}")
    
    # Convert to human-readable format
    for unit in ['B', 'KB', 'MB', 'GB']:
        if total_size < 1024.0:
            return f"{total_size:.2f} {unit}"
        total_size /= 1024.0
    return f"{total_size:.2f} TB"

def format_time_delta(seconds):
    """Format a time delta in seconds to a human-readable string."""
    if seconds < 60:
        return f"{int(seconds)} seconds"
    elif seconds < 3600:
        return f"{int(seconds / 60)} minutes"
    elif seconds < 86400:
        return f"{int(seconds / 3600)} hours"
    else:
        return f"{int(seconds / 86400)} days"