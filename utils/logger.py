import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from PyQt5.QtWidgets import QMessageBox
from utils.signals import global_signals


class SignalHandler(logging.Handler):
    """
    A custom logging handler that emits a PyQt signal for each log record.
    This allows decoupling the logging mechanism from the UI.
    """

    def __init__(self):
        super().__init__()

    def emit(self, record):
        """
        Emits a signal with the log message.
        It checks for a 'task_name' attribute on the record, which is injected
        by the TaskContextFilter.
        """
        log_message = self.format(record)
        task_name = getattr(record, 'task_name', 'general')
        global_signals.log_message.emit(task_name, log_message)


class RedirectStdout:
    """
    A context manager for redirecting stdout to a custom write function.
    This is used to capture output from print() statements within tasks.
    """

    def __init__(self, task_name):
        self.task_name = task_name
        self._original_stdout = sys.stdout
        self._buffer = ""

    def write(self, text):
        # Buffer text until a newline is encountered
        self._buffer += text
        if '\n' in self._buffer:
            # Emit the buffered text line by line
            lines = self._buffer.split('\n')
            for line in lines[:-1]:
                if line.strip():  # Avoid sending empty lines
                    global_signals.log_message.emit(self.task_name, line)
            self._buffer = lines[-1]  # Keep the last partial line

    def flush(self):
        # When flush is called, emit any remaining text in the buffer
        if self._buffer.strip():
            global_signals.log_message.emit(self.task_name, self._buffer)
        self._buffer = ""

    def __enter__(self):
        sys.stdout = self
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.flush()  # Ensure any remaining buffer is flushed on exit
        sys.stdout = self._original_stdout


class LoggerManager:
    """
    Manages the application's logging configuration.
    It sets up structured logging to console, files,
    and a custom signal handler.
    """

    def __init__(self, log_dir="logs"):
        # Get the absolute path to the directory of the current script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Go up one level to the project root from 'utils'
        project_root = os.path.dirname(script_dir)
        # Construct the absolute path to the logs directory
        self.log_dir = os.path.join(project_root, log_dir)
        self.setup_logging()

    def setup_logging(self):
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        log_file = os.path.join(
            self.log_dir, f"log_{datetime.now().strftime('%Y-%m-%d')}.txt")
        log_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s')

        file_handler = RotatingFileHandler(log_file,
                                           maxBytes=5 * 1024 * 1024,
                                           backupCount=5,
                                           encoding='utf-8')
        file_handler.setFormatter(log_formatter)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(log_formatter)

        # Add the custom signal handler
        signal_handler = SignalHandler()
        signal_handler.setFormatter(log_formatter)

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        if root_logger.hasHandlers():
            root_logger.handlers.clear()

        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(signal_handler)  # Add our new handler

        logging.info("LoggerManager initialized and logging is configured.")


def get_logger(task_name="T4T_App"):
    """
    Returns a logger instance for a specific part of the application.
    """
    return logging.getLogger(task_name)


def handle_global_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger = get_logger("GlobalExceptionHandler")

    logger.critical(
        "An unhandled exception occurred! Application may be unstable.",
        exc_info=(exc_type, exc_value, exc_traceback))

    QMessageBox.critical(
        None, "Unhandled Application Error",
        "An unexpected error occurred, which has been logged.\n\n"
        f"<b>Error:</b> {exc_value}\n\n"
        "Please check the log file for more technical details. "
        "It's recommended to save your work and restart the application.")


def setup_exception_hook():
    sys.excepthook = handle_global_exception
    logging.info("Global exception hook has been set.")
