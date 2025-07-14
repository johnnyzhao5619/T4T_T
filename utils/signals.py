# -*- coding: utf-8 -*-
"""
utils/signals.py

This module defines a centralized `GlobalSignals` class for managing custom
signals across the T4T application. Using a centralized signal management
system helps to decouple components, making the application more modular and
easier to maintain.
"""

from PyQt5.QtCore import QObject, pyqtSignal


class GlobalSignals(QObject):
    """
    A singleton class for application-wide signals.
    """
    # Task management signals
    task_manager_updated = pyqtSignal()
    task_status_changed = pyqtSignal(str, str)  # task_name, status
    task_renamed = pyqtSignal(str, str)  # old_name, new_name
    task_succeeded = pyqtSignal(str, str, str)  # task_name, timestamp, msg
    task_failed = pyqtSignal(str, str, str)  # task_name, timestamp, error

    # Logging signal
    log_message = pyqtSignal(str, str)  # task_name, message

    # UI-related signals
    theme_changed = pyqtSignal(str)  # theme_name
    language_changed = pyqtSignal(str)  # language_code
    modules_updated = pyqtSignal()

    # Message bus signals
    message_bus_status_changed = pyqtSignal(str, str)  # status, message
    message_published = pyqtSignal(str, str)  # topic, payload
    message_received = pyqtSignal(str, str)  # topic, payload

    # Service manager signals
    service_state_changed = pyqtSignal(str, object)  # service_name, state
    mqtt_stats_updated = pyqtSignal(dict)  # stats dictionary

    # Signal to request execution in the main GUI thread
    execute_in_main_thread = pyqtSignal(str)  # task_name


# Global singleton instance of the signals
global_signals = GlobalSignals()
