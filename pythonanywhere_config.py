"""
PythonAnywhere-specific configuration for DTF Design Packer

This file should be created in your PythonAnywhere environment.
Customize the settings below for your specific account.
"""
import os

# IMPORTANT: Replace 'yourusername' with your actual PythonAnywhere username
USERNAME = 'yourusername'  # <-- CHANGE THIS!

# PythonAnywhere specific paths
BASE_DIR = f'/home/{USERNAME}/dtf-design-packer'

# Override folder paths for PythonAnywhere
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'outputs')
LOGS_FOLDER = os.path.join(BASE_DIR, 'logs')

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(LOGS_FOLDER, exist_ok=True)

# Account type configuration
# Set this to False if you have a paid PythonAnywhere account (Hacker plan or higher)
FREE_ACCOUNT = True  # <-- CHANGE THIS if you have a paid account

if FREE_ACCOUNT:
    print("PythonAnywhere: Using FREE account configuration")
    
    # Free account limitations
    REDIS_URL = 'memory://'  # No Redis on free accounts
    CACHE_TYPE = 'SimpleCache'
    
    # Smaller file limits for free accounts (50MB instead of 100MB)
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    
    # Reduced session timeout to save memory
    SESSION_TIMEOUT = 1800  # 30 minutes
    SESSION_CLEANUP_INTERVAL = 1800  # 30 minutes
    
    # Smaller cache settings
    CACHE_CONFIG = {
        'CACHE_TYPE': 'SimpleCache',
        'CACHE_DEFAULT_TIMEOUT': 300,  # 5 minutes
        'CACHE_THRESHOLD': 100,  # Smaller cache for free accounts
    }
    
else:
    print("PythonAnywhere: Using PAID account configuration")
    
    # Paid account benefits
    REDIS_URL = 'redis://localhost:6379/0'  # Redis available on paid accounts
    CACHE_TYPE = 'RedisCache'
    
    # Standard file limits
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
    
    # Standard session settings
    SESSION_TIMEOUT = 3600  # 1 hour
    SESSION_CLEANUP_INTERVAL = 3600  # 1 hour
    
    # Redis cache configuration
    CACHE_CONFIG = {
        'CACHE_TYPE': 'RedisCache',
        'CACHE_REDIS_URL': REDIS_URL,
        'CACHE_DEFAULT_TIMEOUT': 300,
        'CACHE_KEY_PREFIX': 'dtf_cache_',
    }

# PythonAnywhere specific settings
PYTHONANYWHERE_DOMAIN = f'{USERNAME}.pythonanywhere.com'

# Security settings for PythonAnywhere
SESSION_COOKIE_SECURE = True  # Always use HTTPS on PythonAnywhere
SESSION_COOKIE_DOMAIN = f'.{USERNAME}.pythonanywhere.com'

# Logging configuration for PythonAnywhere
import logging
import json

class PythonAnywhereFormatter(logging.Formatter):
    """Custom formatter for PythonAnywhere logs"""
    def format(self, record):
        log_entry = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.module,
            'line': record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
            
        return json.dumps(log_entry)

# Override logging configuration for PythonAnywhere
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'pythonanywhere': {
            '()': PythonAnywhereFormatter,
        },
        'simple': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        }
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOGS_FOLDER, 'dtf_packer.log'),
            'maxBytes': 5 * 1024 * 1024,  # 5MB max file size
            'backupCount': 3,
            'formatter': 'simple' if FREE_ACCOUNT else 'pythonanywhere',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['file', 'console'],
    }
}

print(f"PythonAnywhere config loaded for user: {USERNAME}")
print(f"Base directory: {BASE_DIR}")
print(f"Account type: {'FREE' if FREE_ACCOUNT else 'PAID'}")
print(f"Redis URL: {REDIS_URL}")
print(f"Upload folder: {UPLOAD_FOLDER}")
print(f"Max content length: {MAX_CONTENT_LENGTH / (1024*1024):.0f}MB") 