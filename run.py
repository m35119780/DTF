#!/usr/bin/env python3
"""
DTF Design Packer - Production Runner
This script provides options to run the app with or without workers
"""

import os
import sys
import subprocess
import argparse
from app import app

def run_flask():
    """Run the Flask application"""
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    host = os.environ.get('HOST', '0.0.0.0')
    
    print(f"Starting Flask app on {host}:{port} (debug={debug})")
    app.run(host=host, port=port, debug=debug)

def run_celery_worker():
    """Run a Celery worker"""
    from celery_tasks import celery
    argv = ['worker', '--loglevel=info', '-E', '--concurrency=4']
    celery.worker_main(argv)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run DTF Design Packer application')
    parser.add_argument('--worker', action='store_true', help='Run as Celery worker')
    parser.add_argument('--web', action='store_true', help='Run as Flask web server')
    parser.add_argument('--both', action='store_true', help='Run both Flask and Celery (development only)')
    
    args = parser.parse_args()
    
    if args.worker:
        run_celery_worker()
    elif args.both:
        # Start celery worker in a separate process
        print("Starting Celery worker...")
        celery_process = subprocess.Popen([sys.executable, 'run.py', '--worker'])
        
        try:
            # Run Flask in the main process
            run_flask()
        finally:
            # Ensure celery worker is terminated when Flask exits
            celery_process.terminate()
    else:
        # Default is to run the web server
        run_flask() 