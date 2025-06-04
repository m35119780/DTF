# DTF Design Packer - Production Deployment Guide

This guide provides detailed instructions for deploying the DTF Design Packer application in a production environment using Gunicorn as the WSGI server and Nginx/Apache as the reverse proxy.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [WSGI Server Setup (Gunicorn)](#wsgi-server-setup)
4. [Redis Setup](#redis-setup)
5. [Reverse Proxy Configuration](#reverse-proxy-configuration)
   - [Nginx](#nginx-configuration)
   - [Apache](#apache-configuration)
6. [SSL Certificates](#ssl-certificates)
7. [Systemd Service Setup](#systemd-service-setup)
8. [Security Considerations](#security-considerations)
9. [Monitoring](#monitoring)
10. [Troubleshooting](#troubleshooting)

## Prerequisites

- Linux server (Ubuntu 20.04 LTS or newer recommended)
- Python 3.8+ with pip and venv
- Nginx or Apache web server
- Redis server (for Celery)
- Domain name with DNS configured (for production)

## Installation

1. **Create application directory**:
   ```bash
   sudo mkdir -p /opt/dtf-packer
   sudo chown -R $USER:$USER /opt/dtf-packer
   ```

2. **Clone repository**:
   ```bash
   git clone https://github.com/yourusername/dtf-design-packer.git /opt/dtf-packer
   cd /opt/dtf-packer
   ```

3. **Create virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install gunicorn  # Ensure Gunicorn is installed
   ```

5. **Create necessary directories**:
   ```bash
   mkdir -p logs uploads outputs
   chmod 755 logs uploads outputs
   ```

6. **Create environment file**:
   ```bash
   cat > .env << EOF
   SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')
   SESSION_COOKIE_SECURE=true
   SESSION_TIMEOUT=7200
   SESSION_CLEANUP_INTERVAL=1800
   REDIS_URL=redis://localhost:6379/0
   EOF
   ```

## WSGI Server Setup

Gunicorn is the recommended WSGI server for running Flask applications in production.

1. **Test Gunicorn setup**:
   ```bash
   gunicorn --bind 127.0.0.1:5000 wsgi:app
   ```

2. **Configure Gunicorn**:
   The `gunicorn.conf.py` file is already provided with optimal production settings.

   Key configuration points:
   - Worker count: `2 × num_cores + 1` (automatically set)
   - Timeout: 120 seconds (for long-running image processing)
   - Preloading: Enabled for better performance
   - Security settings: Appropriate request limits

## Redis Setup

Redis is required for Celery task queue and session management.

1. **Install Redis**:
   ```bash
   sudo apt update
   sudo apt install redis-server
   ```

2. **Configure Redis**:
   ```bash
   sudo nano /etc/redis/redis.conf
   ```
   
   Set these values:
   ```
   bind 127.0.0.1
   supervised systemd
   maxmemory 256mb
   maxmemory-policy allkeys-lru
   ```

3. **Enable and start Redis**:
   ```bash
   sudo systemctl enable redis-server
   sudo systemctl restart redis-server
   ```

## Reverse Proxy Configuration

### Nginx Configuration

1. **Install Nginx**:
   ```bash
   sudo apt update
   sudo apt install nginx
   ```

2. **Copy Nginx configuration**:
   ```bash
   sudo cp /opt/dtf-packer/deployment/nginx.conf /etc/nginx/sites-available/dtf-packer.conf
   ```

3. **Edit the configuration** to match your domain and paths:
   ```bash
   sudo nano /etc/nginx/sites-available/dtf-packer.conf
   ```

4. **Enable the site**:
   ```bash
   sudo ln -s /etc/nginx/sites-available/dtf-packer.conf /etc/nginx/sites-enabled/
   sudo rm /etc/nginx/sites-enabled/default  # Remove default site if needed
   ```

5. **Test configuration**:
   ```bash
   sudo nginx -t
   ```

6. **Reload Nginx**:
   ```bash
   sudo systemctl reload nginx
   ```

### Apache Configuration

1. **Install Apache and modules**:
   ```bash
   sudo apt update
   sudo apt install apache2 libapache2-mod-proxy-html libxml2-dev
   ```

2. **Enable required modules**:
   ```bash
   sudo a2enmod proxy proxy_http rewrite headers ssl expires
   ```

3. **Copy Apache configuration**:
   ```bash
   sudo cp /opt/dtf-packer/deployment/apache.conf /etc/apache2/sites-available/dtf-packer.conf
   ```

4. **Edit the configuration** to match your domain and paths:
   ```bash
   sudo nano /etc/apache2/sites-available/dtf-packer.conf
   ```

5. **Enable the site**:
   ```bash
   sudo a2ensite dtf-packer.conf
   sudo a2dissite 000-default.conf  # Disable default site if needed
   ```

6. **Test configuration**:
   ```bash
   sudo apache2ctl configtest
   ```

7. **Restart Apache**:
   ```bash
   sudo systemctl restart apache2
   ```

## SSL Certificates

For a production environment, SSL certificates are essential:

1. **Install Certbot**:
   ```bash
   sudo apt install certbot
   ```
   
   For Nginx:
   ```bash
   sudo apt install python3-certbot-nginx
   ```
   
   For Apache:
   ```bash
   sudo apt install python3-certbot-apache
   ```

2. **Obtain SSL certificate**:
   
   For Nginx:
   ```bash
   sudo certbot --nginx -d dtf-packer.example.com
   ```
   
   For Apache:
   ```bash
   sudo certbot --apache -d dtf-packer.example.com
   ```

3. **Set up auto-renewal**:
   ```bash
   sudo systemctl status certbot.timer  # Verify the timer is active
   ```

## Systemd Service Setup

1. **Copy service file**:
   ```bash
   sudo cp /opt/dtf-packer/deployment/dtf-packer.service /etc/systemd/system/
   ```

2. **Edit service file** to update paths and environment variables:
   ```bash
   sudo nano /etc/systemd/system/dtf-packer.service
   ```

3. **Create system user** (if not using existing user):
   ```bash
   sudo useradd -r -s /bin/false dtf-packer
   sudo chown -R dtf-packer:dtf-packer /opt/dtf-packer
   ```

4. **Update ownership of log directories**:
   ```bash
   sudo mkdir -p /var/log/dtf-packer
   sudo chown -R dtf-packer:dtf-packer /var/log/dtf-packer
   ```

5. **Enable and start the service**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable dtf-packer
   sudo systemctl start dtf-packer
   ```

6. **Check service status**:
   ```bash
   sudo systemctl status dtf-packer
   ```

## Security Considerations

1. **Firewall setup**:
   ```bash
   sudo apt install ufw
   sudo ufw allow ssh
   sudo ufw allow http
   sudo ufw allow https
   sudo ufw enable
   ```

2. **File permissions**:
   ```bash
   find /opt/dtf-packer -type d -exec chmod 755 {} \;
   find /opt/dtf-packer -type f -exec chmod 644 {} \;
   chmod 640 /opt/dtf-packer/gunicorn.conf.py
   chmod 640 /opt/dtf-packer/.env
   ```

3. **Regular updates**:
   ```bash
   sudo apt update && sudo apt upgrade
   pip install --upgrade -r requirements.txt
   ```

4. **Security headers**:
   The provided Nginx and Apache configurations include important security headers.

## Monitoring

1. **Log monitoring**:
   
   Gunicorn logs:
   ```bash
   tail -f /var/log/dtf-packer/error.log
   ```
   
   Application logs:
   ```bash
   tail -f /opt/dtf-packer/logs/dtf_packer.log | jq  # If jq is installed
   ```

2. **System monitoring**:
   ```bash
   sudo apt install htop
   sudo apt install netdata  # Optional real-time monitoring
   ```

3. **Service monitoring**:
   ```bash
   sudo systemctl status dtf-packer
   sudo journalctl -u dtf-packer -f
   ```

## Troubleshooting

### Common Issues

1. **Permissions issues**:
   ```bash
   sudo chown -R dtf-packer:dtf-packer /opt/dtf-packer
   sudo chown -R dtf-packer:dtf-packer /var/log/dtf-packer
   ```

2. **Worker timeouts**:
   Adjust timeout in `gunicorn.conf.py` for long-running operations.

3. **Redis connection errors**:
   ```bash
   sudo systemctl status redis-server
   redis-cli ping  # Should return PONG
   ```

4. **Reverse proxy issues**:
   Check Nginx/Apache error logs:
   ```bash
   sudo tail -f /var/log/nginx/error.log
   # or
   sudo tail -f /var/log/apache2/error.log
   ```

5. **Application errors**:
   Check application logs:
   ```bash
   tail -f /opt/dtf-packer/logs/dtf_packer.log
   ```

For more detailed troubleshooting, refer to the respective documentation for Gunicorn, Nginx/Apache, and Flask. 