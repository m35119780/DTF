# DTF Design Packer - PythonAnywhere Deployment Guide

This guide will help you deploy the DTF Design Packer application on PythonAnywhere.

## 📋 Prerequisites

1. **PythonAnywhere Account**: Sign up at [pythonanywhere.com](https://www.pythonanywhere.com)
   - Free account: Limited but good for testing
   - Hacker plan ($5/month): Recommended for production with Redis support
2. **GitHub Repository**: Your code should be in a GitHub repository

## 🚀 Step-by-Step Deployment

### Step 1: Upload Your Code

**Option A: Using Git (Recommended)**
```bash
# In PythonAnywhere console
cd ~
git clone https://github.com/Aliourrami/dtf-film-smart-packer.git
cd dtf-design-packer
```

**Option B: Upload via Files tab**
- Use the Files tab in PythonAnywhere dashboard
- Upload your project files

### Step 2: Create Virtual Environment

```bash
# In PythonAnywhere console
cd ~/dtf-design-packer
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables

Create a `.env` file:
```bash
# In PythonAnywhere console
cd ~/dtf-design-packer
cp env.sample .env
nano .env
```

**For Free Account (.env file):**
```bash
SECRET_KEY=your-generated-secret-key-here
SESSION_COOKIE_SECURE=true
SESSION_TIMEOUT=3600
DEBUG=false
UPLOAD_FOLDER=/home/ourrami/dtf-design-packer/uploads
OUTPUT_FOLDER=/home/ourrami/dtf-design-packer/outputs
LOGS_FOLDER=/home/ourrami/dtf-design-packer/logs
# Redis not available on free accounts
REDIS_URL=memory://
CACHE_TYPE=SimpleCache
```

**For Paid Account (.env file):**
```bash
SECRET_KEY=your-generated-secret-key-here
SESSION_COOKIE_SECURE=true
SESSION_TIMEOUT=3600
DEBUG=false
UPLOAD_FOLDER=/home/ourrami/dtf-design-packer/uploads
OUTPUT_FOLDER=/home/ourrami/dtf-design-packer/outputs
LOGS_FOLDER=/home/ourrami/dtf-design-packer/logs
REDIS_URL=redis://localhost:6379/0
CACHE_TYPE=RedisCache
```

Generate a secret key:
```bash
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"
```

### Step 4: Create Required Directories

```bash
mkdir -p uploads outputs logs static
chmod 755 uploads outputs logs
```

### Step 5: Configure Web App

1. Go to **Web** tab in PythonAnywhere dashboard
2. Click **"Add a new web app"**
3. Choose **"Manual configuration"**
4. Select **Python 3.10**
5. Click **"Next"**

### Step 6: Configure WSGI File

In the Web tab, click on the WSGI configuration file link and replace its contents:

```python
import sys
import os

# Add your project directory to sys.path
path = '/home/ourrami/dtf-design-packer'
if path not in sys.path:
    sys.path.insert(0, path)

# Set up virtual environment
activate_this = '/home/ourrami/dtf-design-packer/venv/bin/activate_this.py'
if os.path.exists(activate_this):
    exec(open(activate_this).read(), dict(__file__=activate_this))

# Load environment variables
from pathlib import Path
from dotenv import load_dotenv

env_path = Path('/home/ourrami/dtf-design-packer') / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

# Import your Flask application
from app import app as application

if __name__ == "__main__":
    application.run()
```

**Replace `ourrami` with your actual PythonAnywhere username!**

### Step 7: Configure Static Files

In the Web tab, scroll to **Static files** section:

| URL | Directory |
|-----|-----------|
| `/static/` | `/home/ourrami/dtf-design-packer/static/` |

### Step 8: Configure Source Code

In the Web tab, set **Source code** to:
```
/home/ourrami/dtf-design-packer
```

### Step 9: Set Working Directory

In the Web tab, set **Working directory** to:
```
/home/ourrami/dtf-design-packer
```

### Step 10: Create PythonAnywhere-specific Config

Create a PythonAnywhere-specific configuration file:

```bash
nano ~/dtf-design-packer/pythonanywhere_config.py
```

```python
"""
PythonAnywhere-specific configuration overrides
"""
import os

# PythonAnywhere specific paths
BASE_DIR = '/home/ourrami/dtf-design-packer'  # Replace with your username

# Override folder paths for PythonAnywhere
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'outputs')
LOGS_FOLDER = os.path.join(BASE_DIR, 'logs')

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(LOGS_FOLDER, exist_ok=True)

# Free account limitations
FREE_ACCOUNT = True  # Set to False if you have a paid account

if FREE_ACCOUNT:
    # Disable Celery for free accounts
    REDIS_URL = 'memory://'
    CACHE_TYPE = 'SimpleCache'
    # Smaller file limits for free accounts
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB instead of 100MB
else:
    # Paid account can use Redis
    REDIS_URL = 'redis://localhost:6379/0'
    CACHE_TYPE = 'RedisCache'
```

Update your `config.py` to use PythonAnywhere settings:

```python
# Add this to the top of config.py after imports
import os

# Try to load PythonAnywhere specific config
try:
    if 'pythonanywhere.com' in os.environ.get('SERVER_NAME', ''):
        from pythonanywhere_config import *
except ImportError:
    pass  # Not on PythonAnywhere, use regular config
```

### Step 11: Test Your Application

1. Click **"Reload"** button in the Web tab
2. Visit your app at `https://ourrami.pythonanywhere.com`

## 🔧 Troubleshooting

### Common Issues

**1. Import Errors**
- Check that all requirements are installed in the virtual environment
- Verify the WSGI file paths are correct

**2. File Permission Issues**
```bash
chmod -R 755 ~/dtf-design-packer
chmod -R 777 ~/dtf-design-packer/uploads
chmod -R 777 ~/dtf-design-packer/outputs
```

**3. Environment Variables Not Loading**
- Check the `.env` file exists and has correct syntax
- Verify the path in WSGI file is correct

**4. Static Files Not Loading**
- Verify static files mapping in Web tab
- Check file permissions

### Checking Logs

View error logs in PythonAnywhere:
1. Go to **Web** tab
2. Click on **"Error log"** link
3. Or use console: `tail -f /var/log/ourrami.pythonanywhere.com.error.log`

View application logs:
```bash
tail -f ~/dtf-design-packer/logs/dtf_packer.log
```

## 📈 Upgrading to Paid Account Benefits

**Free Account Limitations:**
- No Redis (async processing disabled)
- Smaller storage quota
- Limited CPU seconds

**Paid Account ($5/month) Benefits:**
- Redis support (full async processing)
- More storage and CPU
- Custom domains
- SSH access
- Always-on tasks

## 🔄 Updating Your Application

To update your deployed app:

```bash
# In PythonAnywhere console
cd ~/dtf-design-packer
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
```

Then click **"Reload"** in the Web tab.

## 🔒 Security Considerations

1. **Always use HTTPS** (automatic on PythonAnywhere)
2. **Set strong SECRET_KEY** (generate new one for production)
3. **Don't commit .env file** to Git
4. **Regularly update dependencies**

## 📊 Monitoring

Monitor your app:
1. **Web tab**: Shows reload status and errors
2. **CPU usage**: Monitor in account dashboard
3. **File usage**: Check storage quota
4. **Error logs**: Regular monitoring

## 🎯 Production Checklist

- [ ] Generated strong SECRET_KEY
- [ ] Set SESSION_COOKIE_SECURE=true
- [ ] Set DEBUG=false
- [ ] Configured proper file paths
- [ ] Set up error monitoring
- [ ] Tested file uploads
- [ ] Tested image processing
- [ ] Tested download functionality
- [ ] Configured static files properly
- [ ] Set up regular backups

## 💡 Tips for Success

1. **Start with free account** to test everything
2. **Use paid account** for production (Redis support)
3. **Monitor CPU usage** to avoid hitting limits
4. **Keep files organized** in proper directories
5. **Regular backups** of uploaded files
6. **Monitor logs** for issues

Your DTF Design Packer should now be live at `https://ourrami.pythonanywhere.com`! 🎉 