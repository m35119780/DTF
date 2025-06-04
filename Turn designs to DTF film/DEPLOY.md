# DTF Design Packer - Production Deployment Guide

This guide provides instructions for deploying the DTF Design Packer application to a production server securely.

## Prerequisites

- Python 3.8+
- Nginx or Apache for reverse proxy
- A Linux server (Ubuntu/Debian recommended)

## Security Settings

### Environment Variables

Set the following environment variables for secure operation:

| Variable Name | Description | Default | Recommended |
|---------------|-------------|---------|------------|
| SECRET_KEY | Flask secret key for sessions and CSRF | Random generated | Strong random string |
| DEBUG | Run in debug mode | False | False in production |
| HOST | Host to bind to | 0.0.0.0 | 0.0.0.0 or 127.0.0.1 |
| PORT | Port to bind to | 5000 | 80, 443, or 8000+ |
| SESSION_COOKIE_SECURE | Require HTTPS for session cookies | False | True in production |
| SESSION_TIMEOUT | Session expiration time in seconds | 3600 (1 hour) | 7200 (2 hours) |
| SESSION_CLEANUP_INTERVAL | Interval in seconds between cleanup runs | 3600 (1 hour) | 1800 (30 minutes) |
| ADMIN_PASSWORD | Password for accessing admin controls | None | Strong random string |
| REDIS_URL | URL for Redis connection (Celery) | redis://localhost:6379/0 | redis://username:password@host:port/db |

# Managing Sessions

Session management is critical for a production deployment. Consider the following:

1. **Set appropriate timeouts**: For public deployments, shorter timeouts (30-60 minutes) are recommended. For internal tools with trusted users, longer timeouts (2-8 hours) may be appropriate.

2. **Configure cleanup intervals**: The cleanup interval determines how often the system checks for and removes expired sessions. A shorter interval (15-30 minutes) ensures quicker resource cleanup but adds more processing overhead.

3. **Monitor session usage**: The admin interface at `/admin/sessions?key=YOUR_ADMIN_PASSWORD` provides valuable insights into session usage and resource consumption. Check it regularly.

4. **Implement load balancing**: If deploying with multiple worker instances, ensure session persistence by using a shared Redis instance for session storage.

Example configuration in a `.env` file:

```
SECRET_KEY=your-secret-key-here
SESSION_TIMEOUT=7200
SESSION_CLEANUP_INTERVAL=1800
ADMIN_PASSWORD=your-admin-password
SESSION_COOKIE_SECURE=True
```

## Installation Steps

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/dtf-design-packer.git
   cd dtf-design-packer
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create necessary directories with proper permissions:
   ```bash
   mkdir -p uploads outputs
   chmod 755 uploads outputs
   ```

5. Test the application with Gunicorn:
   ```bash
   gunicorn --bind 0.0.0.0:5000 "app:app" --workers 4
   ```

## Running as a Service (Systemd)

Create a systemd service file to run the application as a service:

1. Create `/etc/systemd/system/dtf-design-packer.service`:

```ini
[Unit]
Description=DTF Design Packer Web Application
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/dtf-design-packer
Environment="PATH=/path/to/dtf-design-packer/venv/bin"
Environment="SECRET_KEY=your-secure-secret-key"
Environment="SESSION_COOKIE_SECURE=true"
ExecStart=/path/to/dtf-design-packer/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 "app:app"
Restart=always

[Install]
WantedBy=multi-user.target
```

2. Enable and start the service:
```bash
sudo systemctl enable dtf-design-packer
sudo systemctl start dtf-design-packer
```

## Nginx Configuration

Create an Nginx configuration for reverse proxy:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # Redirect HTTP to HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.com;
    
    # SSL configuration
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    
    # Security headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; style-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; img-src 'self' data:;" always;
    
    # Upload size
    client_max_body_size 100M;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Security Recommendations

1. **Regular Updates**: Keep the system and dependencies updated
   ```bash
   pip install -U -r requirements.txt
   ```

2. **File Permissions**: Ensure proper file permissions
   ```bash
   find . -type d -exec chmod 755 {} \;
   find . -type f -exec chmod 644 {} \;
   chmod 640 *.py
   ```

3. **Automatic Cleanup**: Set up a cron job to clean old files
   ```bash
   0 3 * * * find /path/to/dtf-design-packer/uploads -mtime +7 -type d -exec rm -rf {} \; 2>/dev/null
   0 3 * * * find /path/to/dtf-design-packer/outputs -mtime +7 -type d -exec rm -rf {} \; 2>/dev/null
   ```

4. **Monitoring**: Set up monitoring for the application
   ```bash
   # Example for logging to a file
   gunicorn --bind 0.0.0.0:5000 "app:app" --workers 4 --log-file /var/log/dtf-packer.log --log-level warning
   ```

5. **Backup**: Regularly backup important data

## Troubleshooting

- Check logs: `sudo journalctl -u dtf-design-packer`
- Restart service: `sudo systemctl restart dtf-design-packer`
- Check status: `sudo systemctl status dtf-design-packer`

## Additional Resources

- [Flask Production Deployment](https://flask.palletsprojects.com/en/2.3.x/deploying/)
- [Gunicorn Documentation](https://docs.gunicorn.org/en/latest/settings.html)
- [Nginx Documentation](https://nginx.org/en/docs/)

# Logging Configuration

The application uses a comprehensive logging system that automatically adapts to the environment:

## Logging Features

- **JSON Structured Logging**: In production mode, logs are formatted as JSON for better parsing by log management tools
- **Contextual Information**: Each log entry includes relevant context (session ID, request path, IP address, etc.)
- **Log Rotation**: Log files are automatically rotated to prevent disk space issues (10MB max file size, 10 backup files)
- **Different Log Levels**: DEBUG, INFO, WARNING, ERROR with appropriate filtering based on environment
- **Console Logging**: In debug mode, logs are output to the console in a human-readable format

## Configuration Options

| Variable | Description | Default | Recommended |
|----------|-------------|---------|------------|
| DEBUG | Controls log verbosity and format | False | False in production |
| LOG_LEVEL | Override the default log level | INFO in prod, DEBUG in dev | INFO |
| LOG_DIR | Directory for log files | logs/ | /var/log/dtf-packer |

## Log File Location

- Default: `logs/dtf_packer.log` in the application directory
- Production: Consider changing this to a standard log location like `/var/log/dtf-packer/`

## Viewing Logs

- Development: Logs are printed to the console when in DEBUG mode
- Production: Logs are written to the log file in JSON format
- You can use tools like `jq` to parse the JSON logs:
  ```bash
  tail -f logs/dtf_packer.log | jq
  ```

## Log Format

In production, logs are formatted as JSON with the following structure:

```json
{
  "timestamp": "2023-07-21 12:34:56,789",
  "level": "INFO",
  "name": "app",
  "message": "File uploaded successfully",
  "pathname": "/path/to/app.py",
  "lineno": 123,
  "process_id": 1234,
  "context": {
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "filename": "design.png",
    "filesize": 12345,
    "ip": "127.0.0.1",
    "path": "/upload"
  }
}
```

## Log Integration

The structured JSON logs can be easily integrated with:

- ELK Stack (Elasticsearch, Logstash, Kibana)
- Graylog
- AWS CloudWatch Logs
- Datadog
- Prometheus with Loki

Example Logstash configuration for parsing these logs:

```conf
input {
  file {
    path => "/var/log/dtf-packer/dtf_packer.log"
    codec => "json"
  }
}

filter {
  # Any additional processing
}

output {
  elasticsearch {
    hosts => ["localhost:9200"]
    index => "dtf-packer-%{+YYYY.MM.dd}"
  }
}
``` 