"""
WSGI configuration for DTF Design Packer on PythonAnywhere

Copy this content to your WSGI configuration file in PythonAnywhere Web tab.
Replace 'yourusername' with your actual PythonAnywhere username.
"""

import sys
import os

# IMPORTANT: Replace 'yourusername' with your actual PythonAnywhere username
USERNAME = 'yourusername'  # <-- CHANGE THIS!

# Add your project directory to sys.path
path = f'/home/{USERNAME}/dtf-design-packer'
if path not in sys.path:
    sys.path.insert(0, path)

# Set up virtual environment
activate_this = f'/home/{USERNAME}/dtf-design-packer/venv/bin/activate_this.py'
if os.path.exists(activate_this):
    exec(open(activate_this).read(), dict(__file__=activate_this))

# Set working directory
os.chdir(path)

# Load environment variables from .env file
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(path) / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    print(f"Loaded environment variables from {env_path}")
else:
    print(f"Warning: .env file not found at {env_path}")

# Import your Flask application
try:
    from app import app as application
    print("Successfully imported Flask application")
except Exception as e:
    print(f"Error importing Flask application: {e}")
    raise

# For debugging - remove in production
if __name__ == "__main__":
    application.run(debug=True) 