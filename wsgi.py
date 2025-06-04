"""
WSGI Entry Point for DTF Design Packer
This file serves as the entry point for WSGI servers like Gunicorn
"""
import os
from app import app

if __name__ == "__main__":
    # This block only executes when this script is run directly
    # It will not run when imported by a WSGI server
    app.run(
        host=os.environ.get('HOST', '0.0.0.0'),
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('DEBUG', 'False').lower() == 'true'
    ) 