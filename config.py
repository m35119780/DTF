"""
Configuration module for DTF Design Packer

This module centralizes configuration settings loaded from environment variables
with sensible defaults when environment variables are not set.
"""
import os
import secrets

# Try to detect PythonAnywhere environment and load specific config
PYTHONANYWHERE_DETECTED = False
try:
    # Check if we're running on PythonAnywhere
    if ('pythonanywhere.com' in os.environ.get('SERVER_NAME', '') or 
        '/home/' in os.environ.get('PWD', '') and 'pythonanywhere.com' in str(os.environ.get('PWD', ''))):
        PYTHONANYWHERE_DETECTED = True
        try:
            from pythonanywhere_config import *
            print("Loaded PythonAnywhere-specific configuration")
        except ImportError:
            print("PythonAnywhere detected but no specific config found, using defaults")
except Exception as e:
    print(f"Error detecting PythonAnywhere environment: {e}")

# Application secret key
SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Session settings
SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
PERMANENT_SESSION_LIFETIME = int(os.environ.get('PERMANENT_SESSION_LIFETIME', 3600))  # 1 hour default
SESSION_TIMEOUT = int(os.environ.get('SESSION_TIMEOUT', 3600))  # 1 hour default
SESSION_CLEANUP_INTERVAL = int(os.environ.get('SESSION_CLEANUP_INTERVAL', 3600))  # 1 hour default

# File storage settings (can be overridden by PythonAnywhere config)
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
OUTPUT_FOLDER = os.environ.get('OUTPUT_FOLDER', 'outputs')
LOGS_FOLDER = os.environ.get('LOGS_FOLDER', 'logs')
MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 100 * 1024 * 1024))  # 100MB default

# Static files
SEND_FILE_MAX_AGE_DEFAULT = int(os.environ.get('SEND_FILE_MAX_AGE_DEFAULT', 31536000))  # 1 year in seconds

# Redis and Celery
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

# Cache configuration
CACHE_CONFIG = {
    'CACHE_TYPE': os.environ.get('CACHE_TYPE', 'SimpleCache'),
    'CACHE_DEFAULT_TIMEOUT': int(os.environ.get('CACHE_DEFAULT_TIMEOUT', 300)),  # 5 minutes default
    'CACHE_THRESHOLD': int(os.environ.get('CACHE_THRESHOLD', 500)),  # Maximum items in cache
}

# Security settings
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', None)

# Debug settings
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

# CSRF protection
WTF_CSRF_TIME_LIMIT = int(os.environ.get('WTF_CSRF_TIME_LIMIT', 3600))  # 1 hour CSRF token expiry

# Application defaults
DEFAULT_CANVAS_WIDTH_CM = float(os.environ.get('DEFAULT_CANVAS_WIDTH_CM', 60.0))
DEFAULT_SPACING_MM = float(os.environ.get('DEFAULT_SPACING_MM', 3.0))
DEFAULT_PNG_DPI = int(os.environ.get('DEFAULT_PNG_DPI', 150))
DEFAULT_PDF_MARGIN_CM = float(os.environ.get('DEFAULT_PDF_MARGIN_CM', 1.0)) 