import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from PyQt5.QtWidgets import QMessageBox
from utils.signals import a_signal


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
        The record's name is assumed to be the task_name.
        """
        log_message = self.format(record)
        # The record.name is set by get_logger(task_name)
        a_signal.log_message.emit(record.name, log_message)


class LoggerManager:
    """
    Manages the application's logging configuration.
    It sets up structured logging to console, files,
    and a custom signal handler.
    """

    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir
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
