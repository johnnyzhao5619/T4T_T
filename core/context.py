import logging
from typing import Any, Optional

# Assuming StateManager is in a separate file and needs to be imported
from .state_manager import StateManager


class TaskContext:
    """
    Provides execution context for a task, including a dedicated logger,
    configuration, and state management via a StateManager.
    """

    def __init__(self, task_name: str, logger: logging.Logger,
                 config: Optional[dict], task_path: str,
                 state_manager: StateManager):
        self.task_name = task_name
        self.logger = logger
        self.config = config if config is not None else {}
        self.task_path = task_path
        self.state_manager = state_manager
        self._persist = self.config.get('persist_state', False)

    def get_state(self, key: str, default: Any = None) -> Any:
        """
        Retrieves a value from the task's in-memory state.
        """
        return self.state_manager.get_state(self.task_name, key, default)

    def update_state(self, key: str, value: Any):
        """
        Updates a value in the task's in-memory state and persists it to disk
        if the task is configured to do so.
        """
        self.state_manager.update_state(self.task_name, key, value)
        if self._persist:
            self.state_manager.save_state(self.task_name, self.task_path)


class TaskContextFilter(logging.Filter):
    """
    A logging filter that injects the task_name into log records.
    """

    def __init__(self, task_name: str):
        super().__init__()
        self.task_name = task_name

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Adds the task_name to the log record.

        Args:
            record (logging.LogRecord): The log record to be processed.

        Returns:
            bool: Always True to allow the record to be processed.
        """
        record.task_name = self.task_name
        return True
