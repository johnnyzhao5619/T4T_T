import logging
from typing import Any, Callable, Optional

from .state_manager import StateManager


class TaskContext:
    """
    Provides execution context for a task, including a dedicated logger,
    configuration, and state management via a StateManager.
    """

    def __init__(self, task_name: str, logger: logging.Logger,
                 config: Optional[dict], task_path: str,
                 state_manager: StateManager,
                 *,
                 attempt: int = 1,
                 total_attempts: int = 1,
                 retry_policy: Optional[dict] = None,
                 log_emitter: Optional[Callable[[str], None]] = None,
                 parent_context: Any = None):
        self.task_name = task_name
        self.logger = logger
        self.config = config if config is not None else {}
        self.task_path = task_path
        self.state_manager = state_manager
        self._persist = self.config.get('persist_state', False)
        self.attempt = attempt if attempt >= 1 else 1
        self.total_attempts = total_attempts if total_attempts >= 1 else 1
        self.retry_policy = retry_policy or {}
        self.log_emitter: Optional[Callable[[str], None]] = log_emitter
        self.parent_context = parent_context

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

    def log_progress(self, message: str, level: int = logging.INFO) -> None:
        """Log retry-aware progress messages for UI consumption."""
        prefix = f"[attempt {self.attempt}/{self.total_attempts}]"
        formatted = f"{prefix} {message}" if message else prefix
        self.logger.log(level, formatted)
        if self.log_emitter is not None:
            try:
                self.log_emitter(formatted)
            except Exception:  # pragma: no cover - defensive guard for emitters
                self.logger.debug("Log emitter failed while logging '%s'.",
                                  formatted)


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
