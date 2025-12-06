# Running the Application with Gunicorn

This document explains how to run the Fundus Image Manager application using Gunicorn, which is the recommended way to run the application in production.

## Overview

Gunicorn is a WSGI HTTP Server for UNIX. It's a pre-fork worker model, ported from Ruby's Unicorn project. The Gunicorn server is broadly compatible with various web frameworks and is well-suited for production deployments.

## Files Added

1. **wsgi.py** - WSGI entry point for Gunicorn
2. **gunicorn_config.py** - Gunicorn configuration file
3. **run_with_gunicorn.sh** - Startup script for running with Gunicorn

## Quick Start

### Using the Startup Script (Recommended)

The easiest way to start the application with Gunicorn is to use the provided startup script:

```bash
./run_with_gunicorn.sh
```

This script will:
- Check for `.env` file and copy from `.env.example` if not found
- Load all environment variables from `.env` file
- Create the logs directory if it doesn't exist
- Set sensible defaults for Gunicorn configuration
- Start the Gunicorn server with the configuration

**Important**: The application requires a properly configured `.env` file to run correctly. The script will automatically create one from `.env.example` if it doesn't exist, but you should review and update the values for your specific environment.

### Manual Gunicorn Execution

If you prefer to run Gunicorn manually:

```bash
# Install dependencies first
uv pip install

# Run with Gunicorn using the configuration file
uv run gunicorn -c gunicorn_config.py wsgi:application
```

## Configuration

### Environment Variables

You can customize Gunicorn's behavior using these environment variables in your `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `GUNICORN_BIND` | `127.0.0.1:5001` | The socket to bind |
| `GUNICORN_WORKERS` | `CPU_COUNT * 2 + 1` | Number of worker processes |
| `GUNICORN_WORKER_CLASS` | `sync` | Worker type (sync, eventlet, gevent, etc.) |
| `GUNICORN_TIMEOUT` | `120` | Worker timeout in seconds |
| `GUNICORN_LOG_LEVEL` | `info` | Log level (debug, info, warning, error, critical) |
| `GUNICORN_ACCESS_LOG` | `logs/gunicorn_access.log` | Access log file path |
| `GUNICORN_ERROR_LOG` | `logs/gunicorn_error.log` | Error log file path |
| `GUNICORN_PID_FILE` | `logs/gunicorn.pid` | PID file path |

### Example .env Configuration

```bash
# Production settings
FLASK_ENV=production
FLASK_SECRET_KEY=your-very-secret-key-here

# Gunicorn settings
GUNICORN_BIND=0.0.0.0:5001
GUNICORN_WORKERS=4
GUNICORN_WORKER_CLASS=sync
GUNICORN_TIMEOUT=120
GUNICORN_LOG_LEVEL=info
```

## Worker Types

Gunicorn supports different worker types. Choose based on your application's needs:

### Sync Workers (Default)
- Good for CPU-bound applications
- Simple and reliable
- Each worker handles one request at a time

```bash
GUNICORN_WORKER_CLASS=sync
```

### Eventlet Workers
- Good for I/O-bound applications
- Handles many concurrent connections with fewer workers
- Requires eventlet package

```bash
GUNICORN_WORKER_CLASS=eventlet
```

### Gevent Workers
- Similar to eventlet but uses gevent
- Good for I/O-bound applications
- Requires gevent package

```bash
GUNICORN_WORKER_CLASS=gevent
```

## Performance Tuning

### Number of Workers

The default formula is `CPU_COUNT * 2 + 1`, but you may need to adjust based on:

- Available memory
- Application characteristics (CPU-bound vs I/O-bound)
- Expected load

For a server with 4 CPU cores:
```bash
GUNICORN_WORKERS=9  # (4 * 2 + 1)
```

### Timeout Settings

Increase the timeout if your application has long-running requests:

```bash
GUNICORN_TIMEOUT=300  # 5 minutes
```

### Max Requests

To prevent memory leaks, workers are restarted after handling a certain number of requests:

```python
# In gunicorn_config.py
max_requests = 1000
max_requests_jitter = 100
```

## Logging

Gunicorn provides separate access and error logs:

- **Access Log**: Records HTTP requests
- **Error Log**: Records server errors and application exceptions

Logs are stored in the `logs/` directory by default.

## Process Management

### Using systemd (Recommended for Production)

For production deployment, using systemd is the recommended approach for process management. The project includes a pre-configured systemd service file and installation script.

#### Quick Installation

Use the provided installation script:

```bash
# Navigate to the systemd directory
cd systemd

# Run the installation script (requires sudo)
sudo ./install_service.sh
```

This script will:
- Prompt for installation directory
- Update the service file with correct paths
- Create necessary log directories
- Install and enable the systemd service
- Set proper permissions

#### Manual Installation

If you prefer to install manually, use the provided service file:

```bash
# Copy the service file
sudo cp systemd/fundus-img-xtract.service /etc/systemd/system/

# Update paths in the service file to match your installation
sudo nano /etc/systemd/system/fundus-img-xtract.service

# Reload systemd
sudo systemctl daemon-reload

# Enable and start the service
sudo systemctl enable fundus-img-xtract
sudo systemctl start fundus-img-xtract
```

#### Service Management Commands

```bash
# Start the service
sudo systemctl start fundus-img-xtract

# Stop the service
sudo systemctl stop fundus-img-xtract

# Restart the service
sudo systemctl restart fundus-img-xtract

# Check the service status
sudo systemctl status fundus-img-xtract

# View real-time logs
sudo journalctl -u fundus-img-xtract -f

# View recent logs
sudo journalctl -u fundus-img-xtract --since "1 hour ago"
```

#### Service Configuration

The systemd service includes:
- Automatic restart on failure
- Proper user/group permissions (www-data)
- Environment file loading (.env)
- Security hardening (NoNewPrivileges, PrivateTmp)
- Log management
- Graceful reload support

### Using Supervisor

Create a supervisor configuration at `/etc/supervisor/conf.d/fundus-img-xtract.conf`:

```ini
[program:fundus-img-xtract]
command=/path/to/fundus_img_xtract/.venv/bin/gunicorn -c gunicorn_config.py wsgi:application
directory=/path/to/fundus_img_xtract
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/path/to/fundus_img_xtract/logs/supervisor.log
```

## SSL/TLS Configuration

For HTTPS, you can use Gunicorn with SSL certificates:

```bash
uv run gunicorn -c gunicorn_config.py --keyfile /path/to/key.pem --certfile /path/to/cert.pem wsgi:application
```

Or set in the configuration:

```python
# In gunicorn_config.py
keyfile = '/path/to/key.pem'
certfile = '/path/to/cert.pem'
```

## Monitoring

### Health Check

The application provides a health check endpoint:

```bash
curl http://localhost:5001/healthz
```

### Process Monitoring

Check running processes:

```bash
ps aux | grep gunicorn
```

### Log Monitoring

Monitor logs in real-time:

```bash
tail -f logs/gunicorn_access.log
tail -f logs/gunicorn_error.log
```

## Troubleshooting

### Common Issues

1. **Permission Errors**: Ensure the logs directory is writable by the user running Gunicorn
2. **Port Already in Use**: Check if another process is using the configured port
3. **Worker Timeouts**: Increase timeout if your application has long-running operations
4. **Memory Issues**: Reduce the number of workers or increase available memory

### Debug Mode

For debugging, you can run with increased logging:

```bash
GUNICORN_LOG_LEVEL=debug ./run_with_gunicorn.sh
```

## Development vs Production

### Development
- Use `uv run app.py` for development with Flask's built-in server
- Provides auto-reloading and better debugging experience

### Production
- Use Gunicorn for production deployment
- Better performance, stability, and process management
- Can handle multiple concurrent requests efficiently

## Migration from Flask Development Server

To migrate from the Flask development server to Gunicorn:

1. Install dependencies: `uv pip install`
2. Update your `.env` file with production settings
3. Run with Gunicorn: `./run_with_gunicorn.sh`
4. Set up process management (systemd, supervisor, etc.)
5. Configure reverse proxy (nginx, apache) if needed

## Additional Resources

- [Gunicorn Documentation](https://docs.gunicorn.org/)
- [Flask Deployment with Gunicorn](https://flask.palletsprojects.com/en/latest/deploying/gunicorn/)
- [WSGI Server Comparison](https://www.palletsprojects.com/p/wsgi/)