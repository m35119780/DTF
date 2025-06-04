"""
Gunicorn configuration file for DTF Design Packer
This configuration is optimized for production deployments
"""
import os
import multiprocessing

# Server socket settings
bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:5000')
backlog = 2048

# Worker processes
workers = os.environ.get('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1)
worker_class = 'sync'  # Use 'gevent' or 'eventlet' for async workers if needed
worker_connections = 1000
timeout = 120  # Increased timeout for long-running image processing
keepalive = 2
max_requests = 1000
max_requests_jitter = 50

# Process naming
proc_name = 'dtf_packer'
pythonpath = '.'

# SSL Settings (enable in production)
# keyfile = '/path/to/key.pem'
# certfile = '/path/to/cert.pem'
# ca_certs = '/path/to/ca.pem'

# Security settings
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# Logging
errorlog = os.environ.get('GUNICORN_ERROR_LOG', '-')  # '-' for stderr
accesslog = os.environ.get('GUNICORN_ACCESS_LOG', '-')  # '-' for stderr
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')
access_log_format = '%({X-Forwarded-For}i)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)s'

# Server mechanics
preload_app = True
daemon = False  # Set to True if not managed by systemd
pidfile = None  # Set to a file path when using daemon mode
user = os.environ.get('GUNICORN_USER', None)
group = os.environ.get('GUNICORN_GROUP', None)
umask = 0o027  # Recommended production umask
tmp_upload_dir = None

# Server hooks
def on_starting(server):
    """Log when server starts."""
    print(f"Starting Gunicorn server with {workers} workers")

def on_reload(server):
    """Log when server reloads."""
    print("Reloading Gunicorn server")

def pre_fork(server, worker):
    """Pre-fork customizations."""
    pass

def post_fork(server, worker):
    """Post-fork customizations."""
    server.log.info(f"Worker spawned (pid: {worker.pid})")

def worker_int(worker):
    """Handle SIGINT cleanly."""
    worker.log.info(f"Worker interrupted (pid: {worker.pid})")

def worker_abort(worker):
    """Handle worker abort."""
    worker.log.info(f"Worker aborted (pid: {worker.pid})")

def worker_exit(server, worker):
    """Clean up when a worker exits."""
    server.log.info(f"Worker exited (pid: {worker.pid})")

# Add custom server header
def post_request(worker, req, environ, resp):
    """Post-request actions."""
    resp.headers['Server'] = 'DTF-Packer-Server' 