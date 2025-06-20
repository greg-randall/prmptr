"""
Logging configuration module for prmptr.

This module provides a centralized logging setup with support for:
- Multiple log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Console and file output
- Log rotation and management
- Structured logging options (plain text and JSON)
- Configurable formatters
"""

import logging
import logging.handlers
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


class JsonFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, 'extra_data'):
            log_data.update(record.extra_data)
            
        return json.dumps(log_data, ensure_ascii=False)


class ColoredConsoleFormatter(logging.Formatter):
    """Console formatter with color support."""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors for console output."""
        # Add color to level name
        level_color = self.COLORS.get(record.levelname, '')
        reset_color = self.COLORS['RESET']
        
        # Create colored level name
        colored_level = f"{level_color}{record.levelname}{reset_color}"
        
        # Replace the original levelname temporarily
        original_levelname = record.levelname
        record.levelname = colored_level
        
        # Format the message
        formatted = super().format(record)
        
        # Restore original levelname
        record.levelname = original_levelname
        
        return formatted


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    max_file_size: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    json_format: bool = False,
    console_output: bool = True
) -> logging.Logger:
    """
    Set up logging configuration for the application.
    
    Args:
        log_level: The minimum log level to capture (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file. If None, generates timestamp-based filename
        max_file_size: Maximum size of log file before rotation (in bytes)
        backup_count: Number of backup log files to keep
        json_format: If True, use JSON formatting for file logs
        console_output: If True, also output logs to console
    
    Returns:
        Configured logger instance
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create main logger
    logger = logging.getLogger('prmptr')
    logger.setLevel(numeric_level)
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Console handler setup
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        
        # Use colored formatter for console
        console_format = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
        console_formatter = ColoredConsoleFormatter(
            console_format,
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    # File handler setup
    if log_file is None:
        # Generate timestamp-based filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_file = f"prmptr_{timestamp}.log"
    
    # Ensure log directory exists
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Use rotating file handler for automatic log rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_file_size,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(numeric_level)
    
    # Choose formatter based on json_format flag
    if json_format:
        file_formatter = JsonFormatter()
    else:
        file_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s'
        file_formatter = logging.Formatter(
            file_format,
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str = 'prmptr') -> logging.Logger:
    """
    Get a logger instance with the specified name.
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def log_with_extra(logger: logging.Logger, level: int, message: str, **extra_data: Any) -> None:
    """
    Log a message with additional structured data.
    
    Args:
        logger: Logger instance
        level: Log level (e.g., logging.INFO)
        message: Log message
        **extra_data: Additional data to include in structured logs
    """
    # Create a LogRecord with extra data
    record = logger.makeRecord(
        logger.name, level, "", 0, message, (), None
    )
    record.extra_data = extra_data
    logger.handle(record)


def cleanup_old_logs(log_directory: str = ".", max_age_days: int = 30) -> None:
    """
    Clean up old log files to prevent disk space issues.
    
    Args:
        log_directory: Directory containing log files
        max_age_days: Maximum age of log files to keep (in days)
    """
    log_dir = Path(log_directory)
    if not log_dir.exists():
        return
    
    cutoff_time = datetime.now().timestamp() - (max_age_days * 24 * 60 * 60)
    
    # Find and remove old log files
    for log_file in log_dir.glob("*.log*"):
        if log_file.stat().st_mtime < cutoff_time:
            try:
                log_file.unlink()
                print(f"Cleaned up old log file: {log_file}")
            except OSError as e:
                print(f"Failed to remove old log file {log_file}: {e}")


# Convenience functions for different log levels
def setup_debug_logging(**kwargs) -> logging.Logger:
    """Set up logging with DEBUG level."""
    return setup_logging(log_level="DEBUG", **kwargs)


def setup_production_logging(**kwargs) -> logging.Logger:
    """Set up logging with INFO level and JSON formatting."""
    kwargs.setdefault('json_format', True)
    return setup_logging(log_level="INFO", **kwargs)