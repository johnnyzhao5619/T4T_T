# -*- coding: utf-8 -*-
"""
utils/signals.py

This module defines a centralized `Signals` class for managing custom signals
across the T4T application. Using a centralized signal management system
helps to decouple components, making the application more modular and easier
to maintain.

The signals defined here are used to communicate events between different parts
of the application, such as between the core logic (e.g., `TaskManager`) and
the UI (e.g., `TaskListWidget`).

Key Signals:
- `task_status_changed`: Emitted when a task's status changes (e.g., from
  'stopped' to 'running').
- `task_renamed`: Emitted when a task is successfully renamed.
- `theme_changed`: Emitted when the application's theme is changed.
- `language_changed`: Emitted when the application's language is changed.
"""

from PyQt5.QtCore import QObject, pyqtSignal


class Signals(QObject):
    """
    A class to hold all global signals for the application.
    """
    # Task-related signals
    task_status_changed = pyqtSignal(str, str)  # task_name, new_status
    task_renamed = pyqtSignal(str, str)  # old_name, new_name
    task_manager_updated = pyqtSignal()
    log_message = pyqtSignal(str, str)  # task_name, message

    # UI-related signals
    theme_changed = pyqtSignal(str)  # theme_name
    language_changed = pyqtSignal(str)  # language_code
    modules_updated = pyqtSignal()

    # Signal to execute a function in the main GUI thread
    execute_in_main_thread = pyqtSignal(str)  # The task_name to execute


# Create a global instance of the Signals class to be used
# across the application
a_signal = Signals()
