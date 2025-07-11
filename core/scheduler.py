# -*- coding: utf-8 -*-
"""
core/scheduler.py

This module defines the SchedulerManager class, which encapsulates the task
scheduling logic for the T4T application. It uses
apscheduler's BackgroundScheduler to manage cron-based tasks in a
non-blocking manner, with support for internationalization and
configurable logging.

Key Features:
- Wraps apscheduler for simplified task management.
- Supports adding, removing, starting, and stopping tasks.
- Uses ThreadPoolExecutor for concurrent task execution.
- Integrates with the application's configuration for language settings.
- Provides internationalized logging for key events.
- Designed for seamless integration with a PyQt5-based UI.
"""

import logging
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from pytz import utc

from utils.config import ConfigManager
from utils.i18n import _


class SchedulerManager:
    """
    Manages the lifecycle of scheduled tasks using apscheduler.

    This class provides a high-level API to add, remove, and manage
    tasks, abstracting the underlying complexity of the apscheduler
    library. It is designed to be thread-safe and to run in the background
    without blocking the main application thread, making it suitable for
    use in a GUI application.
    """

    def __init__(self, config_manager: ConfigManager):
        """
        Initializes the SchedulerManager.

        Args:
            config_manager (ConfigManager): The application's configuration
                manager.
        """
        self.config_manager = config_manager
        self.logger = logging.getLogger(__name__)

        executors = {
            'default': ThreadPoolExecutor(10)  # Max 10 concurrent threads
        }
        self.scheduler = BackgroundScheduler(executors=executors, timezone=utc)
        self.logger.info(_('scheduler_initialized'))

    def add_task(self, task_id: str, func, schedule_config: dict):
        """
        Adds a new task to the scheduler based on a schedule configuration 
        object.

        Args:
            task_id (str): A unique identifier for the task.
            func (callable): The function to execute when the task is
            triggered.
            schedule_config (dict): A dictionary defining the schedule.
            Example for cron: {'trigger': 'cron', 'expression': '0 * * * *'}
            Example for interval: {'trigger': 'interval', 'seconds': 30}

        Returns:
            bool: True if the task was added successfully, False otherwise.
        """
        trigger_type = schedule_config.get('trigger', 'cron')
        self.logger.info(
            f"Adding task '{task_id}' with trigger type: {trigger_type}")

        try:
            if trigger_type == 'interval':
                # For interval-based scheduling
                interval_kwargs = {
                    key: val
                    for key, val in schedule_config.items()
                    if key in ['weeks', 'days', 'hours', 'minutes', 'seconds']
                }
                if not interval_kwargs:
                    self.logger.error(
                        f"Task '{task_id}' has no interval parameters "
                        "(e.g., seconds, minutes).")
                    return False
                trigger = IntervalTrigger(**interval_kwargs)
                log_msg = (f"Task '{task_id}' added with interval: "
                           f"{interval_kwargs}")

            elif trigger_type == 'cron':
                # For cron-based scheduling
                cron_expression = schedule_config.get('expression')
                if not cron_expression:
                    self.logger.error(
                        f"Task '{task_id}' is missing cron 'expression'.")
                    return False
                trigger = CronTrigger.from_crontab(cron_expression)
                log_msg = (f"Task '{task_id}' added with cron: "
                           f"{cron_expression}")

            else:
                self.logger.error(f"Unsupported trigger type '{trigger_type}'"
                                  f" for task '{task_id}'.")
                return False

            self.scheduler.add_job(func,
                                   trigger=trigger,
                                   id=task_id,
                                   misfire_grace_time=60,
                                   replace_existing=True)
            self.logger.info(log_msg)
            return True

        except Exception as e:
            self.logger.error(
                _('task_add_failed').format(task_id=task_id, error=str(e)))
            return False

    def remove_task(self, task_id: str):
        """
        Removes a task from the scheduler.

        Args:
            task_id (str): The unique identifier of the task to remove.

        Returns:
            bool: True if the task was removed successfully, False otherwise.
        """
        try:
            self.scheduler.remove_job(task_id)
            self.logger.info(_('task_removed').format(task_id=task_id))
            # TODO: Implement a signal to notify the UI that a task has
            #       been removed.
            return True
        except Exception as e:
            self.logger.error(
                _('task_remove_failed').format(task_id=task_id, error=str(e)))
            return False

    def pause_task(self, task_id: str):
        """
        Pauses a task in the scheduler.

        Args:
            task_id (str): The unique identifier of the task to pause.

        Returns:
            bool: True if the task was paused successfully, False otherwise.
        """
        try:
            self.scheduler.pause_job(task_id)
            self.logger.info(_('task_paused').format(task_id=task_id))
            return True
        except Exception as e:
            self.logger.error(
                _('task_pause_failed').format(task_id=task_id, error=str(e)))
            return False

    def resume_task(self, task_id: str):
        """
        Resumes a paused task in the scheduler.

        Args:
            task_id (str): The unique identifier of the task to resume.

        Returns:
            bool: True if the task was resumed successfully, False otherwise.
        """
        try:
            self.scheduler.resume_job(task_id)
            self.logger.info(_('task_resumed').format(task_id=task_id))
            return True
        except Exception as e:
            self.logger.error(
                _('task_resume_failed').format(task_id=task_id, error=str(e)))
            return False

    def get_task_status(self, task_id: str):
        """
        Gets the status of a task from the scheduler.

        Args:
            task_id (str): The unique identifier of the task.

        Returns:
            str: 'running', 'paused', or 'stopped'.
        """
        job = self.scheduler.get_job(task_id)
        if job is None:
            return 'stopped'

        # A more robust check for paused status due to observed API
        # inconsistencies. Directly accessing job.next_run_time caused an
        # AttributeError. The string representation of a paused job
        # typically contains '(paused)'.
        if '(paused)' in str(job):
            return 'paused'
        else:
            return 'running'

    def start(self):
        """
        Starts the scheduler, allowing it to begin executing tasks.
        """
        try:
            self.scheduler.start()
            self.logger.info(_('scheduler_started'))
        except Exception as e:
            self.logger.error(_('scheduler_start_failed').format(error=str(e)))

    def shutdown(self):
        """
        Shuts down the scheduler, stopping all scheduled tasks.
        """
        try:
            self.scheduler.shutdown()
            self.logger.info(_('scheduler_shutdown'))
        except Exception as e:
            self.logger.error(
                _('scheduler_shutdown_failed').format(error=str(e)))


# --- Documentation for Configuration and Internationalization ---
"""
## Configuration (`config/config.ini`)

The `SchedulerManager` relies on `config.ini` for its setup. The file
should be structured as follows to ensure proper functionality:

```ini
[general]
# Specifies the language for log messages. Must match a .json file in
# the i18n dir.
# Example: 'en', 'zh-CN', 'fr'
language = en

[paths]
# Defines the base directories for logs and internationalization files.
logs = logs
i18n = i18n
```

## Internationalization (`i18n/`)

Log messages are translated based on the language specified in `config.ini`.
Each language requires a corresponding JSON file in the `i18n/` directory
(e.g., `en.json`, `zh-CN.json`).

The JSON files should contain a `scheduler_log` object with key-value
pairs for each log message. Placeholders like `{task_id}` are supported.

### Example: `i18n/en.json`

```json
{
  "scheduler_log": {
    "scheduler_initialized": "Scheduler initialized.",
    "scheduler_started": "Scheduler started successfully.",
    "scheduler_shutdown": "Scheduler shut down.",
    "scheduler_start_failed": "Scheduler start failed: {error}"
  }
}
```
"""
