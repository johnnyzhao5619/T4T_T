# -*- coding: utf-8 -*-
"""
core/scheduler.py

This module defines the SchedulerManager class, which now acts as a
general-purpose background task executor for the T4T application. It uses a
concurrent.futures.ThreadPoolExecutor to manage a pool of worker threads,
allowing for non-blocking execution of tasks.

Key Features:
- Provides a simple interface to submit functions for concurrent execution.
- Manages the lifecycle of the thread pool, including graceful shutdown.
- Designed for seamless integration with a PyQt5-based UI and other core
  components.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Any
from functools import wraps

from utils.i18n import _
from utils.logger import RedirectStdout


class SchedulerManager:
    """
    Manages a thread pool for executing background tasks.

    This class provides a high-level API to submit functions to a
    ThreadPoolExecutor, abstracting the complexity of managing futures and
    threads. It is designed to be thread-safe and to run in the background
    without blocking the main application thread.
    """

    def __init__(self):
        """
        Initializes the SchedulerManager and the thread pool.
        """
        self.logger = logging.getLogger(__name__)
        # Max 10 concurrent threads
        self._executor = ThreadPoolExecutor(max_workers=10)
        self.logger.info(_('scheduler_initialized'))

    def submit(self, func: Callable, *args: Any, **kwargs: Any) -> Future:
        """
        Submits a function to be executed in the thread pool.
        It wraps the function to redirect stdout for capturing
        print statements.

        Args:
            func (Callable): The function to execute.
            *args: Positional arguments to pass to the function.
            **kwargs: Keyword arguments to pass to the function.
                      It's expected that a 'context' object is passed
                      for stdout redirection.

        Returns:
            A Future object representing the execution of the callable.
        """
        context = kwargs.get('context')
        task_name = context.task_name if context else 'unknown_task'
        self.logger.debug(f"Submitting task '{task_name}' to the executor.")

        @wraps(func)
        def wrapper(*w_args, **w_kwargs):
            with RedirectStdout(task_name=task_name):
                return func(*w_args, **w_kwargs)

        future = self._executor.submit(wrapper, *args, **kwargs)
        return future

    def shutdown(self, wait: bool = True):
        """
        Shuts down the thread pool executor.

        Args:
            wait (bool): If True, waits for all pending futures to complete
                         before shutting down.
        """
        try:
            self.logger.info(_('scheduler_shutdown'))
            self._executor.shutdown(wait=wait)
        except Exception as e:
            self.logger.error(
                _('scheduler_shutdown_failed').format(error=str(e)))
