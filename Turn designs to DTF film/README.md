# Image Packer Web Application

A sophisticated web-based image packing tool that efficiently arranges images on a canvas with optimal space utilization. Originally a Python script, now converted to a user-friendly web application that runs locally.

## Features

- **Smart Packing Algorithm**: Uses advanced placement scoring with contact detection and gap filling
- **Rotation Support**: Optional 90-degree rotation for better space efficiency 
- **Transparency Handling**: Full support for PNG files with transparency
- **Multiple Output Formats**: Generates PDF (print-ready) and PNG (visual preview) files
- **Web Interface**: Easy-to-use browser-based interface with drag-and-drop file upload
- **Configurable Settings**: Extensive customization options for the packing algorithm
- **Real-time Processing**: Progress tracking and detailed results summary
- **Batch Processing**: Handle multiple images simultaneously

## Requirements

- Python 3.7 or higher
- Modern web browser (Chrome, Firefox, Safari, Edge)

## Installation

1. **Clone or download this repository**
```bash
   git clone <repository-url>
   cd image-packer-web
```

2. **Install Python dependencies**
```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python run.py
   ```
   
   Or alternatively:
   ```bash
   python app.py
   ```

4. **Open your browser**
   Navigate to: `http://localhost:5000`

## Usage

### 1. Upload Images
- Drag and drop images onto the upload area, or click to browse
- **Important**: Image filenames must contain dimensions using one of these formats:
  - `design_5cm.png` (dimension in filename with 'cm')
  - `design_5.20.png` (dimension as numeric extension)
  - `logo_8.5cm.jpg` (decimal dimensions supported)
  - Only the **width** is required - height is calculated from image aspect ratio
- Supported formats: PNG, JPG, JPEG
- Maximum total upload size: 100MB

### 2. Configure Settings
- **Canvas Width**: Target width for the packing canvas (default: 60cm)
- **Spacing**: Minimum distance between images (default: 3mm)
- **Rotation**: Enable 90-degree rotation for better packing (recommended)
- **Step Size**: Search granularity - smaller values = denser packing but slower processing
- **PNG DPI**: Output resolution for the visual preview (72-600 DPI)

### 3. Process and Download
- Click "Start Packing" to begin processing
- View the results summary showing placement efficiency
- Download the ZIP file containing:
  - `packed_output.pdf` - Print-ready PDF file
  - `packed_output.png` - Visual preview image
  - `placements.txt` - Detailed coordinate information

## File Naming Convention

Your image files **must** include dimensions in the filename for the tool to work properly:

✅ **Valid examples:**
- `logo_5cm_x_3cm.png`
- `design_12.5cm_x_8.2cm.jpg`
- `business_card_9cmx5cm.png`
- `main 9cm.png` (special case for 9x9cm squares)

❌ **Invalid examples:**
- `image.png` (no dimensions)
- `logo_5x3.png` (missing "cm")
- `design_large.jpg` (non-numeric dimensions)

## Configuration Options

| Setting | Description | Default | Range |
|---------|-------------|---------|-------|
| Canvas Width | Target packing width | 60.0 cm | 10-200 cm |
| Spacing | Distance between images | 3 mm | 0-20 mm |
| Rotation | Allow 90° rotation | Enabled | On/Off |
| Step Size | Placement search granularity | 5 mm | 1-20 mm |
| Max Attempts | Tries before giving up | 10 | 1-50 |
| PNG DPI | Output image resolution | 150 | 72-600 |

## Algorithm Details

The packing algorithm uses several strategies:

1. **Mask-based Collision Detection**: Uses actual image transparency for precise placement
2. **Scoring System**: Prioritizes top-left placement while rewarding contact with other images
3. **Gap Filling**: Attempts to fill empty spaces efficiently
4. **Rotation Optimization**: Tests both orientations when enabled
5. **Area Sorting**: Places larger images first for better overall packing

## Troubleshooting

### Images Not Being Processed
- Check that filenames include dimensions in the correct format
- Ensure file formats are PNG, JPG, or JPEG
- Verify total upload size is under 100MB

### Poor Packing Results
- Enable rotation for 15-30% better efficiency
- Reduce step size (1-3mm) for denser packing
- Increase canvas width if many images remain unplaced
- Reduce spacing if appropriate for your use case

### Performance Issues
- Increase step size (5-10mm) for faster processing
- Reduce image count per batch
- Lower PNG output DPI if large file sizes are problematic

## Technical Notes

- The web application creates temporary session folders to handle multiple users
- Files are automatically cleaned up when sessions end
- Processing is done server-side using the original optimized algorithm
- All uploads and outputs are handled locally - no data leaves your machine

## Session Management

The DTF Design Packer application includes a comprehensive session management system to efficiently handle user sessions and resources:

## Session Features

- **Automatic Timeouts**: Sessions expire after a configurable period of inactivity (default: 60 minutes)
- **Resource Cleanup**: All uploaded files, results, and temporary files are automatically cleaned up when sessions expire
- **Background Maintenance**: A dedicated maintenance thread periodically checks for and cleans up expired sessions
- **Activity Tracking**: User activity is tracked to extend session lifetime when users are active
- **Persistent Storage**: Session data is stored persistently to survive application restarts
- **Admin Dashboard**: Session statistics and management controls are available via an admin interface

## Configuration Options

Session behavior can be customized through environment variables:

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| SESSION_TIMEOUT | Session expiration time in seconds | 3600 (1 hour) | 7200 |
| SESSION_CLEANUP_INTERVAL | Interval in seconds between cleanup runs | 3600 (1 hour) | 1800 |
| ADMIN_PASSWORD | Password for accessing admin controls | None | secretpass123 |
| PERMANENT_SESSION_LIFETIME | Flask's session cookie lifetime | 3600 (1 hour) | 86400 |

## Admin Interface

An administrative interface is available at `/admin/sessions?key=YOUR_ADMIN_PASSWORD` (only when DEBUG=True or with valid ADMIN_PASSWORD) where you can:

- View active and expired session statistics
- See disk usage for upload and output folders
- Manually trigger cleanup of expired sessions
- Monitor current session activity

## Security Considerations

The session management system implements several security features:

- **Secure Cookies**: Session cookies are configured with HttpOnly, Secure (in production), and SameSite attributes
- **Resource Isolation**: Each session's files are isolated in separate directories
- **Garbage Collection**: Expired sessions and their resources are automatically removed
- **Activity Validation**: Each request validates that the session is still active

## Best Practices

For optimal performance and security:

1. Set reasonable session timeouts based on your use case (shorter for public deployments)
2. Configure proper cleanup intervals (balance between resource usage and performance impact)
3. Use HTTPS in production to ensure secure session cookies
4. Set an ADMIN_PASSWORD when deploying to production
5. Regularly monitor session usage via the admin interface

## Stopping the Application

Press `Ctrl+C` in the terminal where the application is running to stop the web server.

---

**Note**: This web application runs entirely on your local machine. No data is sent to external servers, ensuring privacy and security of your images.

# Performance Optimizations

The DTF Design Packer application includes several performance optimizations to ensure efficient operation even with large designs and high user load:

## Caching

- **Static Resource Caching**: All static resources (CSS, JS, images) are cached with appropriate cache headers and versioning for optimal browser caching.
  
- **Server-Side Caching**: The application uses Flask-Caching to store computationally expensive results such as image processing operations. This significantly reduces processing time for repeated operations.

- **Cache Busting**: Static resources include version parameters to ensure users always get the latest versions after updates.

## Asynchronous Processing

- **Task Queue**: Heavy processing operations (image processing, packing, and output generation) are handled asynchronously using Celery with Redis as the message broker.

- **Background Processing**: Time-consuming tasks run in the background, allowing the web interface to remain responsive.

- **Real-time Progress Updates**: Users receive real-time progress updates during processing via AJAX polling.

- **Automatic Fallback**: The system gracefully degrades to synchronous processing if the async workers are unavailable.

## Resource Optimization

- **Thumbnail Generation**: Images are efficiently resized and cached for thumbnail display.

- **Lazy Loading**: Resources are loaded on-demand to minimize initial page load times.

- **Memory Management**: Large image processing operations are optimized to minimize memory usage.

## Scaling

- **Worker Pool**: Multiple Celery workers can be deployed to handle increased processing load.

- **Concurrency Control**: Task concurrency is managed to prevent resource exhaustion.

- **Stateless Design**: The application is designed to work with load balancers for horizontal scaling.

# Running with Performance Optimizations

To run the application with all performance optimizations enabled:

1. Start Redis (required for Celery):
   ```
   redis-server
   ```

2. Start Celery worker(s):
   ```
   python run.py --worker
   ```

3. Start the web application:
   ```
   python run.py --web
   ```

For development, you can run both in a single command:
```
python run.py --both
``` 

# Environment Variables

The DTF Design Packer application is fully configurable through environment variables. This allows for easy deployment in different environments without code changes.

## Setting Environment Variables

You can set environment variables in several ways:

1. **System environment variables**:
   ```bash
   export SECRET_KEY="your-secure-key"
   python run.py
   ```

2. **Using a .env file**:
   - Copy `env.sample` to `.env` in the project root
   - Edit values as needed
   - The application will automatically load these values at startup

3. **Docker environment variables**:
   - Set in docker-compose.yml or use `-e` flag with docker run
   - See the deployment/docker-compose.yml file for examples

## Available Variables

Here are the key environment variables you can configure:

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| SECRET_KEY | Secret key for sessions and CSRF | Generated random key | "your-secure-key" |
| SESSION_TIMEOUT | Session expiration time (seconds) | 3600 (1 hour) | 7200 |
| SESSION_CLEANUP_INTERVAL | Time between cleanup runs (seconds) | 3600 (1 hour) | 1800 |
| REDIS_URL | URL for Redis connection | redis://localhost:6379/0 | redis://user:pass@host:port/db |
| DEBUG | Enable debug mode | false | true |
| UPLOAD_FOLDER | Directory for uploaded files | uploads | /data/uploads |
| OUTPUT_FOLDER | Directory for output files | outputs | /data/outputs |
| LOGS_FOLDER | Directory for log files | logs | /var/log/dtf-packer |
| MAX_CONTENT_LENGTH | Maximum upload size in bytes | 100MB | 200000000 |
| ADMIN_PASSWORD | Password for admin access | None | "secure-password" |

For a complete list with detailed descriptions, see the `env.sample` file.

# Logging System

The DTF Design Packer application includes a production-ready logging system with the following features:

## Logging Features

- **Structured JSON Logging**: In production, logs are formatted as JSON for easy parsing and analysis
- **Contextual Information**: Logs include context such as session IDs, request details, and operation-specific data
- **Log Rotation**: Automatic log rotation prevents disk space issues (10MB max file size, 10 backups)
- **Environment-Aware**: Different formats and verbosity in development vs. production environments
- **Performance Metrics**: Key operations include timing information for performance monitoring

## Log Levels

The application uses four primary log levels:

1. **DEBUG**: Detailed information for development and troubleshooting
2. **INFO**: General operational information about system activities
3. **WARNING**: Potential issues that don't prevent normal operation
4. **ERROR**: Critical issues that require attention

## Log File Location

By default, logs are written to the `logs/dtf_packer.log` file in the application directory. This can be customized in production deployments.

## Viewing Logs

- **Development**: When running in debug mode, logs are printed to the console in a human-readable format
- **Production**: Logs are written to the log file in JSON format
- To view logs with proper formatting:
  ```bash
  tail -f logs/dtf_packer.log | jq
  ```

See the [DEPLOY.md](./DEPLOY.md) file for more details on configuring and integrating the logging system in production environments.

# Production Deployment

The DTF Design Packer application can be deployed in production using several methods:

## 🐍 PythonAnywhere (Recommended for beginners)

**Quick deployment to PythonAnywhere:**

1. **Sign up** at [pythonanywhere.com](https://www.pythonanywhere.com)
2. **Clone your repository** in PythonAnywhere console:
   ```bash
   git clone https://github.com/yourusername/dtf-design-packer.git
   cd dtf-design-packer
   ```
3. **Follow the detailed guide**: See [PYTHONANYWHERE_DEPLOYMENT.md](PYTHONANYWHERE_DEPLOYMENT.md)

**Benefits:**
- ✅ Easy setup with web interface
- ✅ Automatic HTTPS
- ✅ Free tier available
- ✅ $5/month for Redis support
- ✅ No server management needed

## 1. WSGI Server with Reverse Proxy (Advanced)

The application includes configuration for Gunicorn (WSGI server) with Nginx or Apache as a reverse proxy:

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install gunicorn
   ```

2. **Run with Gunicorn**:
   ```bash
   gunicorn -c gunicorn.conf.py wsgi:app
   ```

3. **Use a reverse proxy**:
   - Nginx configuration: `deployment/nginx.conf`
   - Apache configuration: `deployment/apache.conf`

See the [deployment guide](deployment/README.md) for detailed instructions.

## 2. Docker Deployment

For containerized deployment, use the included Docker Compose configuration:

1. **Build and start containers**:
   ```bash
   cd deployment
   cp env.sample .env  # Edit .env with your settings
   docker-compose up -d
   ```

2. **Scale workers as needed**:
   ```bash
   docker-compose up -d --scale worker=3
   ```

The Docker setup includes:
- Web service (Flask + Gunicorn)
- Worker service (Celery)
- Redis service (for Celery and caching)
- Nginx service (reverse proxy)

## 3. Systemd Service

For direct installation on a Linux server, use the systemd service file:

1. **Copy service file**:
   ```bash
   sudo cp deployment/dtf-packer.service /etc/systemd/system/
   ```

2. **Enable and start the service**:
   ```bash
   sudo systemctl enable dtf-packer
   sudo systemctl start dtf-packer
   ```

## Production Considerations

1. **Environment Variables**: Configure using environment variables instead of hardcoded values:
   - `SECRET_KEY`: Set a secure random key
   - `SESSION_COOKIE_SECURE`: Set to `true` for HTTPS
   - `SESSION_TIMEOUT`: Set session timeout in seconds
   - `REDIS_URL`: Configure Redis connection

2. **HTTPS**: Always use HTTPS in production with proper certificates.

3. **File Storage**: Consider using a persistent storage solution for uploads and outputs.

4. **Memory Optimization**: Adjust Gunicorn and Celery worker settings based on available memory.

For more details, see the [deployment documentation](deployment/README.md). 