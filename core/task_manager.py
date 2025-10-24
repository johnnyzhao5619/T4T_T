import os
import logging
import shutil
import importlib.util
import time
from copy import deepcopy
from typing import Any, Callable
from datetime import datetime
from types import SimpleNamespace

from core.context import TaskContext, TaskContextFilter

from apscheduler.jobstores.base import ConflictingIdError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from core.module_manager import ModuleManager
from core.scheduler import SchedulerManager
from core.state_manager import StateManager
from utils.config import ConfigManager, load_yaml, save_yaml
from utils.signals import global_signals
from utils.message_bus import message_bus_manager

logger = logging.getLogger(__name__)


SCHEDULED_TRIGGER_TYPES = frozenset({'cron', 'interval', 'date'})


class TaskExecutionError(RuntimeError):
    """Base exception for recoverable task execution failures."""


class TaskExecutableNotFoundError(TaskExecutionError):
    """Raised when a task script does not expose a callable ``run`` function."""

    def __init__(self, task_name: str, script_path: str):
        message = ("Task '%s' cannot be executed because script '%s' does not "
                   "define a callable 'run' function." % (task_name,
                                                           script_path))
        super().__init__(message)
        self.task_name = task_name
        self.script_path = script_path


def is_scheduled_trigger(trigger_type: str | None) -> bool:
    """Return True when the trigger type should be handled by APScheduler."""
    return trigger_type in SCHEDULED_TRIGGER_TYPES


class TaskManager:
    """
    Manages task instances, including creation, modification,
    deletion, and scheduling. Integrates with ModuleManager for
    task creation and TaskScheduler for execution.
    """

    DEFAULT_EVENT_MAX_HOPS = 5
    DEFAULT_RETRY_POLICY = {
        'max_attempts': 1,
        'strategy': 'fixed',
        'interval': 0.0,
        'max_interval': None,
        'multiplier': 2.0,
    }

    def __init__(self,
                 scheduler_manager: SchedulerManager,
                 tasks_dir='tasks',
                 modules_dir='modules',
                 config_manager: ConfigManager | None = None):
        """
        Initialize the TaskManager with directories for tasks and modules.

        Args:
            scheduler_manager (SchedulerManager): The application's scheduler
                instance.
            tasks_dir (str): Directory path where task instances are stored.
            modules_dir (str): Directory path where module templates
                are stored.
            config_manager (ConfigManager | None): Optional configuration
                manager used for resolving global task defaults.
        """
        self.tasks_dir = tasks_dir
        resolved_modules_dir = os.path.abspath(modules_dir)
        self.module_manager = ModuleManager()
        self.module_manager.set_module_path(resolved_modules_dir)
        self.scheduler_manager = scheduler_manager
        self.state_manager = StateManager()
        self.apscheduler = BackgroundScheduler()
        self.tasks = {}
        self._event_task_topics: dict[str, str] = {}
        self.config_manager = config_manager
        self._script_cache: dict[str, tuple[float, Callable]] = {}

        try:
            self.apscheduler.start()
            logger.info("APScheduler started.")
        except Exception as e:
            logger.error(f"Failed to start APScheduler: {e}")

        self.load_tasks()
        logger.info(
            f"TaskManager initialized with tasks directory: {tasks_dir}")

    def load_tasks(self):
        """
        Load all task instances from the tasks directory.
        Each task is expected to have a subfolder with main.py and config.yaml.
        """
        # Ensure existing event subscriptions are cleaned up before reloading
        for existing_task in list(self._event_task_topics.keys()):
            self._unsubscribe_event_task(existing_task, emit_status=False)

        # Stop and remove any scheduled jobs before reloading configuration
        existing_jobs = list(self.apscheduler.get_jobs())
        if existing_jobs:
            for job in existing_jobs:
                task_name = job.id
                task_info = self.tasks.get(task_name)
                if task_info and task_info.get('status') in {'running', 'paused'}:
                    task_info['status'] = 'stopped'
                    global_signals.task_status_changed.emit(task_name, 'stopped')
            try:
                self.apscheduler.remove_all_jobs()
                logger.debug("Cleared %d existing scheduled jobs before reload.",
                             len(existing_jobs))
            except Exception as exc:
                logger.error("Failed to clear existing scheduled jobs: %s", exc)

        self.tasks.clear()
        self._event_task_topics.clear()
        if not os.path.exists(self.tasks_dir):
            os.makedirs(self.tasks_dir)
            logger.info(f"Tasks directory created at '{self.tasks_dir}'")
            return

        for task_name in os.listdir(self.tasks_dir):
            task_path = os.path.join(self.tasks_dir, task_name)
            if os.path.isdir(task_path):
                script_file = os.path.join(task_path, "main.py")
                config_file = os.path.join(task_path, "config.yaml")

                if os.path.exists(script_file) and os.path.exists(config_file):
                    try:
                        config_data = load_yaml(config_file)
                        config_data = self._prepare_loaded_task_config(
                            task_path, config_data)

                        # Create a dedicated logger for the task
                        task_logger = logging.getLogger(f"task.{task_name}")

                        # Set logger level based on task's debug setting
                        debug_mode = config_data.get('debug', False)
                        level = logging.DEBUG if debug_mode else logging.INFO
                        task_logger.setLevel(level)

                        # Add a filter to inject task_name into log records
                        # for the SignalHandler.
                        if not any(
                                isinstance(f, TaskContextFilter)
                                for f in task_logger.filters):
                            context_filter = TaskContextFilter(
                                task_name=task_name)
                            task_logger.addFilter(context_filter)

                        self.tasks[task_name] = {
                            'path': task_path,
                            'script': script_file,
                            'config': config_file,
                            'config_data': config_data,
                            'status': 'stopped',
                            'logger': task_logger
                        }
                        # Load state into memory
                        if config_data.get('persist_state', False):
                            self.state_manager.load_state(task_name, task_path)
                        logger.info(
                            f"Task '{task_name}' loaded and logger configured."
                        )
                    except Exception as e:
                        logger.error(f"Failed to load task '{task_name}': {e}")
                else:
                    logger.warning(f"Task '{task_name}' is missing main.py or "
                                   "config.yaml.")
        logger.info(f"Loaded {len(self.tasks)} tasks.")
        self._initialize_tasks()

    def _parse_trigger(self, config: dict) -> tuple[str | None, dict]:
        """Extracts the trigger type and its configuration from a task."""
        trigger_section = config.get('trigger', {})
        if not isinstance(trigger_section, dict):
            return None, {}

        trigger_type: str | None = None
        trigger_params: dict[str, Any] = {}

        trigger_type_value = trigger_section.get('type')
        if trigger_type_value:
            trigger_type = str(trigger_type_value).lower()
            raw_params = trigger_section.get('config') or {}
            trigger_params = dict(raw_params) if isinstance(raw_params, dict) else {}

            if trigger_type == 'schedule':
                inner_type = trigger_params.pop('type', None)
                trigger_type = str(inner_type).lower() if inner_type else None
                if not trigger_params:
                    trigger_params = {
                        key: value
                        for key, value in trigger_section.items()
                        if key not in {'type', 'config'}
                    }
            elif trigger_type == 'event':
                if 'topic' in trigger_section and 'topic' not in trigger_params:
                    trigger_params['topic'] = trigger_section['topic']
            else:
                if not trigger_params:
                    trigger_params = {
                        key: value
                        for key, value in trigger_section.items()
                        if key != 'type'
                    }
        elif 'schedule' in trigger_section:
            schedule_conf = trigger_section.get('schedule') or {}
            inner_type = schedule_conf.get('type')
            trigger_type = str(inner_type).lower() if inner_type else None
            trigger_params = {
                key: value
                for key, value in schedule_conf.items()
                if key != 'type'
            }
        elif 'event' in trigger_section:
            trigger_type = 'event'
            event_conf = trigger_section.get('event') or {}
            if isinstance(event_conf, dict):
                trigger_params = dict(event_conf)

        if trigger_type == 'cron':
            cron_expression = trigger_params.pop('cron_expression', None)
            if not cron_expression:
                cron_expression = trigger_params.pop('expression', None)
            if cron_expression:
                trigger_params['cron_expression'] = cron_expression

        return trigger_type, trigger_params

    def _get_event_topic(self, config: dict) -> tuple[bool, str | None]:
        """Returns whether the task is an active event task and its topic."""
        trigger_type, trigger_params = self._parse_trigger(config)
        topic = trigger_params.get('topic') if trigger_type == 'event' else None
        is_enabled = bool(config.get('enabled') and topic)
        return is_enabled, topic

    def _register_event_subscription(self, task_name: str, topic: str,
                                     callback: Callable[[dict], None]):
        self._event_task_topics[task_name] = topic
        self.tasks[task_name]['event_wrapper'] = callback

    def _unsubscribe_event_task(self, task_name: str, emit_status: bool = True):
        task_info = self.tasks.get(task_name)
        topic = self._event_task_topics.pop(task_name, None)
        wrapper = task_info.get('event_wrapper') if task_info else None

        if topic:
            if wrapper:
                message_bus_manager.unsubscribe(topic, wrapper)
            else:
                message_bus_manager.unsubscribe(topic)

        if not task_info:
            return
        task_info.pop('event_wrapper', None)
        task_info['status'] = 'stopped'
        if emit_status:
            global_signals.task_status_changed.emit(task_name, 'stopped')

    def _subscribe_event_task(self, task_name: str, topic: str,
                              emit_status: bool = True):
        wrapper_func = self._create_event_wrapper(task_name)
        self._register_event_subscription(task_name, topic, wrapper_func)

        try:
            message_bus_manager.subscribe(topic, wrapper_func)
        except Exception:
            self._event_task_topics.pop(task_name, None)
            task_info = self.tasks.get(task_name)
            if task_info:
                task_info.pop('event_wrapper', None)
                task_info['status'] = 'stopped'
            raise

        self.tasks[task_name]['status'] = 'listening'
        if emit_status:
            global_signals.task_status_changed.emit(task_name, 'listening')

    def _update_event_subscription(self, task_name: str, enabled: bool,
                                   topic: str | None,
                                   emit_status: bool = True):
        existing_topic = self._event_task_topics.get(task_name)

        if not enabled or not topic:
            if existing_topic:
                self._unsubscribe_event_task(task_name, emit_status=emit_status)
            return

        if existing_topic == topic and 'event_wrapper' in self.tasks[task_name]:
            self.tasks[task_name]['status'] = 'listening'
            if emit_status:
                global_signals.task_status_changed.emit(task_name, 'listening')
            return

        if existing_topic:
            self._unsubscribe_event_task(task_name, emit_status=emit_status)

        self._subscribe_event_task(task_name, topic, emit_status=emit_status)

    def _initialize_tasks(self):
        """
        Initializes loaded tasks, scheduling them or subscribing to events
        based on their trigger configuration.
        """
        for task_name, task_info in self.tasks.items():
            config = task_info.get('config_data', {})
            if not config.get('enabled', False):
                logger.debug(f"Task '{task_name}' is disabled, skipping.")
                continue

            trigger_type, trigger_params = self._parse_trigger(config)

            if is_scheduled_trigger(trigger_type):
                # For scheduled tasks, use the existing start_task method
                self.start_task(task_name)
            elif trigger_type == 'event':
                if not self.start_task(task_name):
                    logger.error(
                        "Failed to start event-driven task '%s' during initialization.",
                        task_name)
            else:
                logger.warning(
                    f"Task '{task_name}' has an unknown trigger type: "
                    f"'{trigger_type}'.")

    def _create_event_wrapper(self, task_name: str) -> Callable[[dict], None]:
        """
        Creates a callback function that wraps the actual task execution.
        This wrapper includes pre-execution checks for safety.
        """

        def wrapper(payload: dict):
            logger.info(
                f"Event received for task '{task_name}', processing...")
            task_info = self.tasks.get(task_name)
            if not task_info:
                logger.warning(
                    f"Event received for removed task '{task_name}', ignoring.")
                return

            config = task_info.get('config_data', {})
            if not config.get('enabled', False):
                logger.info(
                    f"Task '{task_name}' is disabled, ignoring incoming event.")
                return

            # 1. Cycle detection
            hops = payload.get('__hops', 0)
            max_hops = self._get_event_max_hops(config)
            if hops > max_hops:
                logger.error(
                    f"Task '{task_name}' stopped: max hop count ({max_hops}) "
                    "exceeded. Possible infinite loop.")
                return

            # 2. Input validation
            payload_with_defaults = dict(payload)
            inputs_schema = config.get('inputs', [])

            if isinstance(inputs_schema, dict):
                schema_iterable = inputs_schema.items()
            else:
                schema_iterable = []
                if isinstance(inputs_schema, list):
                    schema_iterable = (
                        (item.get('name'), item)
                        for item in inputs_schema
                        if isinstance(item, dict))

            for item_name, item_def in schema_iterable:
                if not item_name or not isinstance(item_def, dict):
                    continue

                if item_def.get('required') and item_name not in payload_with_defaults:
                    logger.error(
                        f"Task '{task_name}' execution stopped: missing "
                        f"required input '{item_name}'.")
                    return

                if item_name not in payload_with_defaults and 'default' in item_def:
                    payload_with_defaults[item_name] = item_def['default']

            # 3. Submit task for execution
            self.run_task(task_name, payload_with_defaults)

        return wrapper

    @staticmethod
    def _to_non_negative_int(value: Any) -> int | None:
        """Safely convert a value to a non-negative integer."""
        if isinstance(value, bool):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    @staticmethod
    def _to_non_negative_number(value: Any) -> float | None:
        """Safely convert a value to a non-negative float."""
        if isinstance(value, bool):
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    def _get_event_max_hops(self, config: dict) -> int:
        """Resolve the max hops threshold for an event payload."""

        trigger_section = config.get('trigger')
        if isinstance(trigger_section, dict):
            # Prefer values defined under the event trigger configuration
            event_conf = trigger_section.get('event')
            if isinstance(event_conf, dict):
                candidate = self._to_non_negative_int(event_conf.get('max_hops'))
                if candidate is not None:
                    return candidate

            direct_candidate = self._to_non_negative_int(
                trigger_section.get('max_hops'))
            if direct_candidate is not None:
                return direct_candidate

            config_section = trigger_section.get('config')
            if isinstance(config_section, dict):
                config_candidate = self._to_non_negative_int(
                    config_section.get('max_hops'))
                if config_candidate is not None:
                    return config_candidate

        config_manager = getattr(self, 'config_manager', None)
        if config_manager is not None:
            raw_global = config_manager.get('TaskDefaults',
                                            'event_max_hops',
                                            fallback=None)
            global_candidate = self._to_non_negative_int(raw_global)
            if global_candidate is not None:
                return global_candidate

        return self.DEFAULT_EVENT_MAX_HOPS

    def _prepare_and_run_task(self,
                              task_name: str,
                              inputs: dict | None = None,
                              *,
                              attempt: int = 1,
                              total_attempts: int = 1,
                              retry_policy: dict | None = None,
                              log_emitter: Callable[[str], None] | None = None,
                              context=None):
        """Load the task script, construct the context, and execute it."""
        task_info = self.tasks[task_name]
        task_logger = task_info.get('logger', logger)
        executable_func = self._load_task_executable(task_info['script'])
        if not executable_func:
            error_message = (
                "Task '%s' execution aborted: missing callable 'run' in script '%s'."
                % (task_name, task_info['script'])
            )
            task_logger.error(error_message)
            if task_logger is not logger:
                logger.error(error_message)
            raise TaskExecutableNotFoundError(task_name, task_info['script'])

        task_context = TaskContext(
            task_name=task_name,
            logger=task_logger,
            config=task_info['config_data'],
            task_path=task_info['path'],
            state_manager=self.state_manager,
            attempt=attempt,
            total_attempts=total_attempts,
            retry_policy=retry_policy,
            log_emitter=log_emitter,
            parent_context=context
        )

        prepared_inputs = inputs if inputs is not None else {}
        task_context.log_progress("开始执行任务")

        try:
            result = executable_func(context=task_context, inputs=prepared_inputs)
        except TaskExecutionError as exc:
            task_context.log_progress(f"任务执行失败: {exc}", logging.WARNING)
            raise
        except Exception as exc:
            task_context.log_progress(f"任务执行异常: {exc}", logging.ERROR)
            raise

        if isinstance(result, TaskExecutionError):
            task_context.log_progress(f"任务返回失败结果: {result}", logging.WARNING)
        else:
            task_context.log_progress("任务执行成功", logging.INFO)

        return result

    def _resolve_retry_policy(self, config: dict) -> dict[str, Any]:
        """Merge retry configuration with global defaults."""
        policy = dict(self.DEFAULT_RETRY_POLICY)
        retry_section = config.get('retry')

        if isinstance(retry_section, dict):
            max_attempts = self._to_non_negative_int(
                retry_section.get('max_attempts'))
            if max_attempts is not None and max_attempts >= 1:
                policy['max_attempts'] = max_attempts

            strategy_value = retry_section.get('backoff_strategy')
            if isinstance(strategy_value, str):
                normalized_strategy = strategy_value.strip().lower()
                if normalized_strategy in {'fixed', 'exponential'}:
                    policy['strategy'] = normalized_strategy

            interval = self._to_non_negative_number(
                retry_section.get('backoff_interval_seconds'))
            if interval is not None:
                policy['interval'] = interval

            max_interval = self._to_non_negative_number(
                retry_section.get('backoff_max_interval_seconds'))
            if max_interval is not None:
                policy['max_interval'] = max_interval

            multiplier = self._to_non_negative_number(
                retry_section.get('backoff_multiplier'))
            if multiplier is not None and multiplier >= 1:
                policy['multiplier'] = multiplier

        config_manager = getattr(self, 'config_manager', None)
        if config_manager is not None:
            if policy['max_attempts'] == self.DEFAULT_RETRY_POLICY['max_attempts']:
                raw_max = config_manager.get('TaskDefaults',
                                             'retry_max_attempts',
                                             fallback=None)
                parsed_max = self._to_non_negative_int(raw_max)
                if parsed_max is not None and parsed_max >= 1:
                    policy['max_attempts'] = parsed_max

            if policy['strategy'] == self.DEFAULT_RETRY_POLICY['strategy']:
                raw_strategy = config_manager.get('TaskDefaults',
                                                  'retry_backoff_strategy',
                                                  fallback=None)
                if isinstance(raw_strategy, str):
                    normalized_strategy = raw_strategy.strip().lower()
                    if normalized_strategy in {'fixed', 'exponential'}:
                        policy['strategy'] = normalized_strategy

            if policy['interval'] == self.DEFAULT_RETRY_POLICY['interval']:
                raw_interval = config_manager.get(
                    'TaskDefaults', 'retry_backoff_interval_seconds',
                    fallback=None)
                parsed_interval = self._to_non_negative_number(raw_interval)
                if parsed_interval is not None:
                    policy['interval'] = parsed_interval

            if policy['max_interval'] == self.DEFAULT_RETRY_POLICY['max_interval']:
                raw_max_interval = config_manager.get(
                    'TaskDefaults', 'retry_backoff_max_interval_seconds',
                    fallback=None)
                parsed_max_interval = self._to_non_negative_number(
                    raw_max_interval)
                if parsed_max_interval is not None:
                    policy['max_interval'] = parsed_max_interval

            if policy['multiplier'] == self.DEFAULT_RETRY_POLICY['multiplier']:
                raw_multiplier = config_manager.get(
                    'TaskDefaults', 'retry_backoff_multiplier',
                    fallback=None)
                parsed_multiplier = self._to_non_negative_number(
                    raw_multiplier)
                if parsed_multiplier is not None and parsed_multiplier >= 1:
                    policy['multiplier'] = parsed_multiplier

        max_interval = policy['max_interval']
        if max_interval is not None and max_interval < policy['interval']:
            policy['max_interval'] = policy['interval']

        return policy

    def _compute_retry_delay(self, retry_policy: dict, attempt: int) -> float:
        """Compute backoff delay for the next attempt."""
        base_interval = float(retry_policy.get('interval', 0.0) or 0.0)
        strategy = retry_policy.get('strategy', 'fixed')

        if strategy == 'exponential':
            multiplier = retry_policy.get('multiplier',
                                          self.DEFAULT_RETRY_POLICY['multiplier'])
            if multiplier < 1:
                multiplier = self.DEFAULT_RETRY_POLICY['multiplier']
            delay = base_interval * (multiplier ** (attempt - 1))
        else:
            delay = base_interval

        max_interval = retry_policy.get('max_interval')
        if isinstance(max_interval, (int, float)):
            delay = min(delay, max_interval)

        return delay if delay >= 0 else 0.0

    def _log_retry_schedule(self,
                            task_name: str,
                            attempt: int,
                            total_attempts: int,
                            delay: float,
                            error: Exception,
                            log_emitter: Callable[[str], None] | None) -> None:
        task_logger = self.tasks.get(task_name, {}).get('logger', logger)
        next_attempt = min(attempt + 1, total_attempts)
        if delay <= 0:
            message = (f"[attempt {attempt}/{total_attempts}] 任务失败，将立即重试第 "
                       f"{next_attempt} 次。原因: {error}")
        else:
            message = (f"[attempt {attempt}/{total_attempts}] 任务失败，将在 {delay:.2f} 秒后"
                       f"重试第 {next_attempt} 次。原因: {error}")
        task_logger.warning(message)
        if log_emitter is not None:
            log_emitter(message)

    def _log_final_failure(self,
                           task_name: str,
                           attempt: int,
                           total_attempts: int,
                           error: Exception,
                           log_emitter: Callable[[str], None] | None) -> None:
        task_logger = self.tasks.get(task_name, {}).get('logger', logger)
        message = (f"[attempt {attempt}/{total_attempts}] 任务在达到最大重试次数后失败: {error}")
        task_logger.error(message)
        if log_emitter is not None:
            log_emitter(message)

    def _execute_with_retries(self,
                              task_name: str,
                              base_inputs: dict | None,
                              *,
                              log_emitter: Callable[[str], None] | None = None,
                              retry_policy: dict | None = None,
                              context=None):
        """Execute a task with retry semantics."""
        policy = retry_policy or self._resolve_retry_policy(
            self.tasks.get(task_name, {}).get('config_data', {}))
        total_attempts = max(int(policy.get('max_attempts', 1)), 1)
        normalized_inputs = base_inputs if isinstance(base_inputs, dict) else {}
        last_error: TaskExecutionError | None = None

        for attempt in range(1, total_attempts + 1):
            attempt_inputs = deepcopy(normalized_inputs)
            try:
                result = self._prepare_and_run_task(
                    task_name,
                    attempt_inputs,
                    attempt=attempt,
                    total_attempts=total_attempts,
                    retry_policy=policy,
                    log_emitter=log_emitter,
                    context=context)
            except TaskExecutionError as exc:
                last_error = exc
                if attempt < total_attempts:
                    delay = self._compute_retry_delay(policy, attempt)
                    self._log_retry_schedule(task_name, attempt, total_attempts,
                                             delay, exc, log_emitter)
                    if delay > 0:
                        self._sleep(delay)
                    continue

                final_error = TaskExecutionError(
                    f"Task '{task_name}' failed after {total_attempts} attempts. "
                    f"Last error: {exc}")
                self._log_final_failure(task_name, attempt, total_attempts,
                                        final_error, log_emitter)
                raise final_error from exc
            except Exception:
                raise

            if isinstance(result, TaskExecutionError):
                last_error = result
                if attempt < total_attempts:
                    delay = self._compute_retry_delay(policy, attempt)
                    self._log_retry_schedule(task_name, attempt, total_attempts,
                                             delay, result, log_emitter)
                    if delay > 0:
                        self._sleep(delay)
                    continue

                final_error = TaskExecutionError(
                    f"Task '{task_name}' failed after {total_attempts} attempts. "
                    f"Last error: {result}")
                self._log_final_failure(task_name, attempt, total_attempts,
                                        final_error, log_emitter)
                raise final_error

            return result

        if last_error is not None:
            final_error = TaskExecutionError(
                f"Task '{task_name}' failed after {total_attempts} attempts. "
                f"Last error: {last_error}")
            self._log_final_failure(task_name, total_attempts, total_attempts,
                                    final_error, log_emitter)
            raise final_error

        raise TaskExecutionError(
            f"Task '{task_name}' failed after {total_attempts} attempts.")

    @staticmethod
    def _sleep(seconds: float) -> None:
        if seconds <= 0:
            return
        time.sleep(seconds)

    def _execute_task_logic(self,
                            task_name: str,
                            inputs: dict,
                            log_emitter: Callable[[str], None] | None = None):
        """
        Handles the asynchronous submission of a task and dispatches
        completion signals when it finishes.
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        task_info = self.tasks[task_name]
        retry_policy = self._resolve_retry_policy(
            task_info.get('config_data', {}))
        normalized_inputs = inputs if isinstance(inputs, dict) else {}
        base_inputs = deepcopy(normalized_inputs)

        try:
            future = self.scheduler_manager.submit(
                self._execute_with_retries,
                task_name,
                base_inputs,
                retry_policy=retry_policy,
                log_emitter=log_emitter,
                context=SimpleNamespace(task_name=task_name)
            )

            def task_done_callback(fut):
                try:
                    result = fut.result()
                except TaskExecutionError as exc:
                    error_msg = str(exc)
                    global_signals.task_failed.emit(task_name, timestamp, error_msg)
                    logger.error(f"Task '{task_name}' failed: {exc}", exc_info=True)
                    return
                except Exception as e:
                    error_msg = f"Task execution failed: {e}"
                    global_signals.task_failed.emit(task_name, timestamp, error_msg)
                    logger.error(f"Task '{task_name}' failed: {e}", exc_info=True)
                    return

                if isinstance(result, TaskExecutionError):
                    error_msg = str(result)
                    global_signals.task_failed.emit(task_name, timestamp, error_msg)
                    logger.error(
                        f"Task '{task_name}' reported failure result: {result}")
                    return

                msg = f"Task completed successfully. Result: {result}"
                global_signals.task_succeeded.emit(task_name, timestamp, msg)
                logger.info(f"Task '{task_name}' finished successfully.")

            future.add_done_callback(task_done_callback)
            return future

        except Exception as e:
            error_msg = f"Failed to submit task to executor: {e}"
            global_signals.task_failed.emit(task_name, timestamp, error_msg)
            logger.error(f"Error submitting task '{task_name}': {e}",
                         exc_info=True)
            return None

    def run_task(self,
                 task_name: str,
                 inputs: dict | None = None,
                 *,
                 use_executor: bool = True,
                 log_emitter: Callable[[str], None] | None = None):
        """Execute a task either asynchronously or synchronously."""
        if task_name not in self.tasks:
            logger.error(f"Task '{task_name}' not found.")
            return None

        normalized_inputs = inputs if isinstance(inputs, dict) else {}
        prepared_inputs = deepcopy(normalized_inputs)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if use_executor:
            if log_emitter is not None:
                return self._execute_task_logic(task_name, prepared_inputs,
                                                log_emitter=log_emitter)
            return self._execute_task_logic(task_name, prepared_inputs)

        try:
            retry_policy = self._resolve_retry_policy(
                self.tasks[task_name].get('config_data', {}))
            result = self._execute_with_retries(
                task_name,
                prepared_inputs,
                retry_policy=retry_policy,
                log_emitter=log_emitter,
                context=SimpleNamespace(task_name=task_name))
        except TaskExecutionError as exc:
            error_msg = str(exc)
            global_signals.task_failed.emit(task_name, timestamp, error_msg)
            logger.error(f"Task '{task_name}' failed during synchronous execution: {exc}",
                         exc_info=True)
            raise
        except Exception as e:
            error_msg = f"Task execution failed: {e}"
            global_signals.task_failed.emit(task_name, timestamp, error_msg)
            logger.error(f"Task '{task_name}' failed during synchronous execution: {e}",
                         exc_info=True)
            raise

        if isinstance(result, TaskExecutionError):
            error_msg = str(result)
            global_signals.task_failed.emit(task_name, timestamp, error_msg)
            logger.error(f"Task '{task_name}' reported failure result: {result}")
            return result

        msg = f"Task completed successfully. Result: {result}"
        global_signals.task_succeeded.emit(task_name, timestamp, msg)
        logger.info(f"Task '{task_name}' finished successfully.")
        return result

    def get_task_list(self):
        """
        Get a list of all task names.

        Returns:
            list: List of task names.
        """
        return list(self.tasks.keys())

    def get_task_count(self):
        """
        Get the total number of managed tasks.

        Returns:
            int: The number of tasks.
        """
        return len(self.tasks)

    def get_running_task_count(self) -> int:
        """
        Get the number of tasks that are currently running.

        Returns:
            int: The number of running tasks.
        """
        running_count = 0
        for task_name in self.tasks:
            if self.get_task_status(task_name) == 'running':
                running_count += 1
        return running_count

    def get_task_info(self, task_name):
        """
        Get detailed information about a specific task.

        Args:
            task_name (str): Name of the task.

        Returns:
            dict: Task information dictionary, or empty dict if not found.
        """
        return self.tasks.get(task_name, {})

    def validate_task_name(self, task_name: str) -> tuple[bool, str | None]:
        """Validate a task name and return an error code when invalid.

        Args:
            task_name: Proposed task name.

        Returns:
            Tuple containing a boolean indicating validity and an optional
            error code string when invalid. Possible error codes are:
            ``'empty'``, ``'separator'``, and ``'outside'``.
        """

        if not task_name:
            return False, 'empty'

        separators = {os.sep}
        if os.altsep:
            separators.add(os.altsep)

        for separator in separators:
            if separator and separator in task_name:
                return False, 'separator'

        if os.path.isabs(task_name):
            return False, 'outside'

        normalized_tasks_dir = os.path.abspath(self.tasks_dir)
        candidate_path = os.path.abspath(os.path.join(self.tasks_dir,
                                                      task_name))
        try:
            common_path = os.path.commonpath([normalized_tasks_dir,
                                              candidate_path])
        except ValueError:
            return False, 'outside'

        if common_path != normalized_tasks_dir:
            return False, 'outside'

        if task_name in {'.', '..'}:
            return False, 'outside'

        return True, None

    def create_task(self, task_name: str, module_type: str) -> bool:
        """
        Creates a new task instance from a module template.

        Args:
            task_name (str): The name for the new task. Must be unique.
            module_type (str): The module type to use as a template.

        Returns:
            bool: True if creation was successful, False otherwise.
        """
        is_valid_name, error_code = self.validate_task_name(task_name)
        if not is_valid_name:
            error_reasons = {
                'empty': "Task name cannot be empty.",
                'separator': ("Task name contains path separator characters "
                              "and was rejected."),
                'outside': ("Task name resolves outside the tasks directory "
                            "after normalization."),
            }
            reason = error_reasons.get(error_code, "Invalid task name.")
            logger.warning("Rejected task creation for name '%s': %s",
                           task_name, reason)
            return False

        task_path = os.path.join(self.tasks_dir, task_name)
        if os.path.exists(task_path):
            logger.error(
                f"Task '{task_name}' already exists at '{task_path}'.")
            return False

        templates = self.module_manager.get_module_templates(module_type)
        if not templates:
            logger.error(f"Module type '{module_type}' not found.")
            return False

        try:
            os.makedirs(task_path)

            # Define destination paths
            script_dest = os.path.join(task_path, "main.py")
            config_dest = os.path.join(task_path, "config.yaml")

            # Copy and rename templates
            shutil.copy(templates['py_template'], script_dest)

            # Read the original config, add name and module_type, then write
            config_data = load_yaml(templates['manifest_path'])

            config_data['name'] = task_name
            config_data['module_type'] = module_type
            config_data = self._prepare_module_config(module_type, config_data)

            save_yaml(config_dest, config_data)

            # Copy declared asset files or directories, if any
            module_dir = os.path.dirname(templates['py_template'])

            def _collect_assets(values):
                collected: list[str] = []
                if isinstance(values, str):
                    collected.append(values)
                elif isinstance(values, (list, tuple, set)):
                    for item in values:
                        if isinstance(item, str):
                            collected.append(item)
                return collected

            assets_to_copy: list[str] = []

            assets_section = config_data.get('assets')
            if isinstance(assets_section, dict):
                assets_to_copy.extend(_collect_assets(
                    assets_section.get('copy_files')))
            else:
                assets_to_copy.extend(_collect_assets(assets_section))

            assets_to_copy.extend(_collect_assets(
                config_data.get('copy_files')))

            normalized_assets: list[str] = []
            seen: set[str] = set()
            for asset_entry in assets_to_copy:
                normalized = os.path.normpath(asset_entry)
                if not normalized or normalized == '.':
                    continue
                if os.path.isabs(normalized) or normalized.startswith('..'):
                    logger.warning(
                        "Skipping asset '%s' for task '%s' because it is not a"
                        " relative path.", asset_entry, task_name)
                    continue
                if normalized not in seen:
                    normalized_assets.append(normalized)
                    seen.add(normalized)

            for relative_path in normalized_assets:
                source_path = os.path.join(module_dir, relative_path)
                destination_path = os.path.join(task_path, relative_path)

                if not os.path.exists(source_path):
                    logger.warning(
                        "Asset '%s' declared in module '%s' was not found at"
                        " '%s'. Skipping.", relative_path, module_type,
                        source_path)
                    continue

                try:
                    if os.path.isdir(source_path):
                        shutil.copytree(source_path, destination_path)
                    else:
                        os.makedirs(os.path.dirname(destination_path),
                                    exist_ok=True)
                        shutil.copy2(source_path, destination_path)
                except Exception as copy_error:
                    logger.error(
                        "Failed to copy asset '%s' for task '%s': %s",
                        relative_path, task_name, copy_error)
                    raise

            self._post_process_module_creation(module_type, module_dir,
                                               task_path, config_data)

            logger.info(f"Task '{task_name}' created successfully"
                        f" from module '{module_type}'.")
            self.load_tasks()  # Refresh task list
            global_signals.task_manager_updated.emit()
            return True
        except Exception as e:
            logger.error(f"Failed to create task '{task_name}': {e}")
            if os.path.exists(task_path):
                shutil.rmtree(task_path)  # Cleanup
            return False

    def _prepare_module_config(self, module_type: str,
                               config_data: dict) -> dict:
        if module_type == 'google_sheet_sync':
            return self._normalize_google_sheet_config(config_data)
        return config_data

    def _post_process_module_creation(self, module_type: str,
                                       module_dir: str,
                                       task_path: str,
                                       config_data: dict) -> None:
        if module_type == 'google_sheet_sync':
            self._ensure_google_sheet_oauth_assets(module_dir, task_path,
                                                   config_data)

    def _normalize_google_sheet_config(self, config_data: dict) -> dict:
        oauth_section = config_data.get('oauth', {})
        if not isinstance(oauth_section, dict):
            raise ValueError("Google Sheet 模块的 manifest 缺少 oauth 配置。")

        scopes = oauth_section.get('scopes')
        if isinstance(scopes, str):
            normalized_scopes = [scopes.strip()] if scopes.strip() else []
        elif isinstance(scopes, (list, tuple, set)):
            normalized_scopes = []
            for scope in scopes:
                scope_str = str(scope).strip()
                if scope_str and scope_str not in normalized_scopes:
                    normalized_scopes.append(scope_str)
        else:
            raise ValueError("Google Sheet 模块的 oauth.scopes 必须为字符串或列表。")

        if not normalized_scopes:
            raise ValueError("Google Sheet 模块的 oauth.scopes 不能为空。")

        oauth_section['scopes'] = normalized_scopes
        for field in ('credentials_file', 'token_file', 'credentials_template'):
            value = oauth_section.get(field)
            if not value or not isinstance(value, str):
                raise ValueError(
                    f"Google Sheet 模块的 oauth.{field} 必须为非空字符串。")

        config_data['oauth'] = oauth_section
        return config_data

    def _ensure_google_sheet_oauth_assets(self, module_dir: str,
                                          task_path: str,
                                          config_data: dict) -> None:
        oauth_section = config_data.get('oauth', {})
        credentials_template = oauth_section.get('credentials_template')
        credentials_file = oauth_section.get('credentials_file')
        token_file = oauth_section.get('token_file')

        if not all(isinstance(value, str) and value.strip()
                   for value in (credentials_template,
                                 credentials_file,
                                 token_file)):
            raise ValueError("Google Sheet 模块的 oauth 配置缺少必填字段。")

        template_source = os.path.join(module_dir, credentials_template)
        if not os.path.exists(template_source):
            raise FileNotFoundError(
                f"无法在模块目录中找到 OAuth 样板文件: {template_source}")

        template_destination = os.path.join(task_path, credentials_template)
        os.makedirs(os.path.dirname(template_destination), exist_ok=True)
        if not os.path.exists(template_destination):
            shutil.copy2(template_source, template_destination)
        else:
            logger.debug("OAuth 样板文件已存在，跳过复制: %s",
                         template_destination)

        credentials_destination = os.path.join(task_path, credentials_file)
        os.makedirs(os.path.dirname(credentials_destination), exist_ok=True)
        if not os.path.exists(credentials_destination):
            shutil.copy2(template_source, credentials_destination)
            logger.info("已生成默认 OAuth 凭据占位文件: %s",
                        credentials_destination)

        token_destination = os.path.join(task_path, token_file)
        os.makedirs(os.path.dirname(token_destination), exist_ok=True)

    def _prepare_loaded_task_config(self, task_path: str,
                                    config_data: dict | None) -> dict:
        if not isinstance(config_data, dict):
            return {}

        module_type = config_data.get('module_type')
        if not module_type:
            return config_data

        if module_type == 'google_sheet_sync':
            config_data = self._normalize_google_sheet_config(config_data)
            templates = self.module_manager.get_module_templates(module_type)
            if templates:
                module_dir = os.path.dirname(templates['py_template'])
                self._ensure_google_sheet_oauth_assets(
                    module_dir, task_path, config_data)

        return config_data

    def delete_task(self, task_name):
        """
        Delete a task instance and its associated files.

        Args:
            task_name (str): Name of the task to delete.

        Returns:
            bool: True if task deletion was successful, False otherwise.
        """
        if task_name not in self.tasks:
            logger.error(f"Task {task_name} not found.")
            return False

        try:
            task_info = self.tasks[task_name]
            task_path = task_info['path']
            config_data = task_info.get('config_data', {})

            job = self.apscheduler.get_job(task_name)
            if job:
                try:
                    self.apscheduler.remove_job(task_name)
                    logger.info(
                        f"Task '{task_name}' removed from scheduler before deletion.")
                except Exception as exc:
                    logger.error(
                        f"Failed to remove scheduled job for task '{task_name}': {exc}")

            task_info['status'] = 'stopped'

            trigger_type, _ = self._parse_trigger(config_data)
            if trigger_type == 'event':
                self._unsubscribe_event_task(task_name)
            else:
                global_signals.task_status_changed.emit(task_name, 'stopped')

            shutil.rmtree(task_path)
            del self.tasks[task_name]
            logger.info(f"Task {task_name} deleted.")
            global_signals.task_manager_updated.emit()
            return True
        except Exception as e:
            logger.error(f"Failed to delete task {task_name}: {str(e)}")
            return False

    def rename_task(self, old_name: str, new_name: str) -> bool:
        """
        Renames a task folder and updates the internal state.
        This method assumes the task is not running.

        Args:
            old_name (str): The current name of the task.
            new_name (str): The new name for the task.

        Returns:
            bool: True if successful, False otherwise.
        """
        job = self.apscheduler.get_job(old_name)

        if old_name not in self.tasks:
            logger.error(f"Cannot rename: Task '{old_name}' not found.")
            return False
        if new_name in self.tasks or os.path.exists(
                os.path.join(self.tasks_dir, new_name)):
            logger.error(f"Cannot rename: Task '{new_name}' already exists.")
            return False

        old_path = self.tasks[old_name]['path']
        new_path = os.path.join(self.tasks_dir, new_name)

        try:
            os.rename(old_path, new_path)
            logger.info(
                f"Renamed task folder from '{old_path}' to '{new_path}'.")

            # Update the internal dictionary
            task_data = self.tasks.pop(old_name)
            task_data['path'] = new_path
            task_data['config'] = os.path.join(new_path, "config.yaml")
            task_data['script'] = os.path.join(new_path, "main.py")

            config_data = task_data.get('config_data')
            if isinstance(config_data, dict):
                config_data['name'] = new_name
            else:
                config_data = {'name': new_name}
                task_data['config_data'] = config_data

            save_yaml(task_data['config'], config_data)

            old_logger = task_data.get('logger')
            if isinstance(old_logger, logging.Logger):
                for existing_filter in list(getattr(old_logger, 'filters', [])):
                    if isinstance(existing_filter, TaskContextFilter):
                        old_logger.removeFilter(existing_filter)

                new_logger = logging.getLogger(f"task.{new_name}")
                new_logger.setLevel(old_logger.level)
                new_logger.propagate = old_logger.propagate

                for handler in getattr(old_logger, 'handlers', []):
                    if handler not in new_logger.handlers:
                        new_logger.addHandler(handler)

                for existing_filter in list(getattr(new_logger, 'filters', [])):
                    if isinstance(existing_filter, TaskContextFilter):
                        new_logger.removeFilter(existing_filter)

                new_logger.addFilter(TaskContextFilter(new_name))
                task_data['logger'] = new_logger
            else:
                task_logger = logging.getLogger(f"task.{new_name}")
                for existing_filter in list(getattr(task_logger, 'filters', [])):
                    if isinstance(existing_filter, TaskContextFilter):
                        task_logger.removeFilter(existing_filter)
                task_logger.addFilter(TaskContextFilter(new_name))
                task_data['logger'] = task_logger

            event_topic = None
            if old_name in self._event_task_topics:
                event_topic = self._event_task_topics.pop(old_name)
                wrapper = task_data.get('event_wrapper')
                if wrapper:
                    message_bus_manager.unsubscribe(event_topic, wrapper)
                else:
                    message_bus_manager.unsubscribe(event_topic)
                task_data.pop('event_wrapper', None)

            self.tasks[new_name] = task_data

            # Ensure the in-memory state follows the renamed task
            self.state_manager.rename_task(old_name, new_name)

            if job:
                try:
                    self.apscheduler.remove_job(old_name)
                    logger.debug("Removed old scheduler job for task '%s' during rename.",
                                 old_name)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error("Failed to remove old scheduler job for task '%s': %s",
                                 old_name, exc)

                job_restarted = False
                config_for_schedule = task_data.get('config_data', {})
                trigger_type, _ = self._parse_trigger(config_for_schedule)

                if config_for_schedule.get('enabled') and is_scheduled_trigger(trigger_type):
                    if self.start_task(new_name):
                        job_restarted = True
                    else:
                        logger.warning("Failed to restart scheduler job for task '%s' after rename.",
                                       new_name)

                if not job_restarted:
                    task_data['status'] = 'stopped'
                    global_signals.task_status_changed.emit(new_name, 'stopped')

            if event_topic:
                enabled, topic = self._get_event_topic(task_data.get(
                    'config_data', {}))
                if enabled and topic:
                    self._subscribe_event_task(new_name, topic)

            logger.info(
                f"Task '{old_name}' successfully renamed to '{new_name}'.")
            global_signals.task_renamed.emit(old_name, new_name)
            return True
        except Exception as e:
            logger.error(f"Failed to rename task '{old_name}': {e}")
            # Attempt to rollback if rename failed
            if not os.path.exists(old_path) and os.path.exists(new_path):
                os.rename(new_path, old_path)
            return False

    def get_task_config(self, task_name):
        """
        Get the configuration data for a specific task.

        Args:
            task_name (str): Name of the task.

        Returns:
            dict: Configuration data, or None if task not found.
        """
        if task_name not in self.tasks:
            logger.error(f"Task '{task_name}' not found.")
            return None

        # Return a deep copy to prevent modification of the in-memory cache
        return deepcopy(self.tasks[task_name].get('config_data', {}))

    def get_task_schema(self, task_name: str) -> dict:
        """
        Loads the schema for a given task from the module's manifest.yaml.

        Args:
            task_name (str): The name of the task.

        Returns:
            dict: The loaded schema, or an empty dict if not found or on error.
        """
        if task_name not in self.tasks:
            logger.error(f"Cannot get schema: Task '{task_name}' not found.")
            return {}

        module_type = self.tasks[task_name].get('config_data',
                                                {}).get('module_type')
        if not module_type:
            return {}

        templates = self.module_manager.get_module_templates(module_type)
        if not templates or 'manifest_path' not in templates:
            return {}

        # The schema is now part of the manifest
        manifest_data = load_yaml(templates['manifest_path'])
        return manifest_data.get('schema', {})

    def save_task_config(self, task_name, config_data):
        """
        Update the configuration of a task. If the 'name' parameter is changed,
        it triggers the task renaming process.

        Args:
            task_name (str): Name of the task to update.
            config_data (dict): New configuration data to save.

        Returns:
            tuple[bool, str]: A tuple containing a boolean for success and the
                             final task name (which may have changed).
        """
        if task_name not in self.tasks:
            logger.error(f"Task '{task_name}' not found.")
            return False, task_name

        final_task_name = task_name
        # Check if the task name is being changed
        new_name = config_data.get("name")
        if new_name and new_name != task_name:
            if self.rename_task(task_name, new_name):
                final_task_name = new_name
                task_name = new_name
            else:
                # If renaming fails, abort the save.
                return False, task_name

        try:
            previous_config = deepcopy(
                self.tasks[final_task_name].get('config_data', {}))

            # Use the potentially new task name to get the config file path
            config_file = self.tasks[final_task_name]['config']
            save_yaml(config_file, config_data)

            # Update the in-memory cache
            self.tasks[final_task_name]['config_data'] = config_data

            trigger_type, trigger_params = self._parse_trigger(config_data)
            previous_trigger_type, previous_trigger_params = self._parse_trigger(
                previous_config)

            enabled, topic = self._get_event_topic(config_data)
            self._update_event_subscription(final_task_name, enabled, topic)

            job = self.apscheduler.get_job(final_task_name)

            if not is_scheduled_trigger(trigger_type) and job is not None:
                try:
                    self.apscheduler.remove_job(final_task_name)
                    logger.info(
                        "Cleared scheduled job for task '%s' after trigger change.",
                        final_task_name)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error(
                        "Failed to clear job for task '%s' when trigger changed: %s",
                        final_task_name, exc)

            if is_scheduled_trigger(trigger_type):
                job_exists = job is not None
                enabled_now = bool(config_data.get('enabled'))
                enabled_before = bool(previous_config.get('enabled'))
                schedule_changed = (
                    trigger_type != previous_trigger_type or
                    trigger_params != previous_trigger_params
                )

                if not enabled_now and job_exists:
                    try:
                        self.apscheduler.remove_job(final_task_name)
                        logger.info(
                            "Task '%s' removed from scheduler after disable.",
                            final_task_name)
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.error(
                            "Failed to remove job for task '%s': %s",
                            final_task_name, exc)
                    self.tasks[final_task_name]['status'] = 'stopped'
                    global_signals.task_status_changed.emit(
                        final_task_name, 'stopped')
                elif enabled_now and (
                        schedule_changed or not enabled_before or not job_exists):
                    if job_exists:
                        try:
                            self.apscheduler.remove_job(final_task_name)
                            logger.debug(
                                "Removed existing schedule for task '%s' before "
                                "rebuilding.", final_task_name)
                        except Exception as exc:  # pragma: no cover - defensive
                            logger.error(
                                "Failed to clear existing job for task '%s': %s",
                                final_task_name, exc)
                    try:
                        if not self.start_task(final_task_name):
                            logger.warning(
                                "Task '%s' schedule rebuild did not succeed.",
                                final_task_name)
                    except ConflictingIdError as exc:
                        logger.error(
                            "Conflicting job id encountered when scheduling "
                            "task '%s': %s", final_task_name, exc)
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.error(
                            "Unexpected error when rebuilding schedule for task "
                            "'%s': %s", final_task_name, exc)

            # Update logger level if debug setting changed
            task_logger = self.tasks[final_task_name].get('logger')
            if task_logger:
                debug_mode = config_data.get('debug', False)
                new_level = logging.DEBUG if debug_mode else logging.INFO
                if task_logger.level != new_level:
                    task_logger.setLevel(new_level)
                    logger.info(f"Logger level for task "
                                f"'{final_task_name}' set to {new_level}.")

            logger.info(f"Task '{final_task_name}' configuration updated.")
            return True, final_task_name
        except Exception as e:
            logger.error(
                f"Failed to update config for task '{final_task_name}': {e}")
            return False, final_task_name

    def shutdown(self, wait: bool = True):
        """
        Shuts down all background services managed by the TaskManager.

        Args:
            wait (bool): If True, waits for all pending futures to complete
                         before shutting down.
        """
        logger.info("Shutting down TaskManager services...")
        # Save all persistent states before shutting down
        self.state_manager.save_all_states(self.tasks)

        if self.apscheduler.running:
            try:
                # Shutdown APScheduler, but don't wait for its jobs here.
                # The wait happens in the SchedulerManager's thread pool.
                self.apscheduler.shutdown(wait=False)
                logger.info("APScheduler has been shut down.")
            except Exception as e:
                logger.error(f"Error shutting down APScheduler: {e}")

        try:
            # The main wait for running tasks happens here.
            self.scheduler_manager.shutdown(wait=wait)
            logger.info(f"SchedulerManager (ThreadPool) has been shut down "
                        f"(wait={wait}).")
        except Exception as e:
            logger.error(f"Error shutting down SchedulerManager: {e}")

    def _load_task_executable(self, script_path: str):
        """
        Dynamically loads a 'run' function from a given script file.
        """
        cached_entry = self._script_cache.get(script_path)

        try:
            current_mtime = os.path.getmtime(script_path)
        except OSError as exc:
            if cached_entry:
                self._script_cache.pop(script_path, None)
            logger.error(
                f"Failed to load task module from '{script_path}': {exc}")
            return None

        if cached_entry and cached_entry[0] == current_mtime:
            return cached_entry[1]

        try:
            spec = importlib.util.spec_from_file_location(
                "task_module", script_path)
            if spec is None or spec.loader is None:
                raise ImportError("Unable to create module spec or loader is missing")

            task_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(task_module)

            run_callable = getattr(task_module, 'run', None)
            if callable(run_callable):
                self._script_cache[script_path] = (current_mtime, run_callable)
                return run_callable

            self._script_cache.pop(script_path, None)
            logger.error(f"Script '{script_path}' does not have a callable"
                         " 'run' function.")
            return None
        except Exception as e:
            self._script_cache.pop(script_path, None)
            logger.error(
                f"Failed to load task module from '{script_path}': {e}")
            return None

    def start_task(self, task_name: str):
        """
        Starts a scheduled task by adding it to the internal APScheduler.
        The actual task execution is submitted to the ThreadPoolExecutor.
        """
        if task_name not in self.tasks:
            logger.error(f"Task '{task_name}' not found.")
            return False

        if self.apscheduler.get_job(task_name):
            logger.warning(f"Task '{task_name}' is already scheduled.")
            return True

        task_info = self.tasks[task_name]
        config = task_info['config_data']
        trigger_type, trigger_params = self._parse_trigger(config)

        def emit_schedule_failure(message: str,
                                  *,
                                  exc: Exception | None = None) -> bool:
            """Emit a scheduling failure message and keep the task stopped."""
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if exc is not None:
                logger.error(message, exc_info=True)
            else:
                logger.error(message)
            global_signals.task_failed.emit(task_name, timestamp, message)
            task_info['status'] = 'stopped'
            return False

        if not is_scheduled_trigger(trigger_type):
            if trigger_type == 'event':
                topic = trigger_params.get('topic')
                if not topic:
                    message = (
                        f"Task '{task_name}' is configured as event-driven but lacks "
                        "a 'topic' value."
                    )
                    logger.error(message)
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    global_signals.task_failed.emit(task_name, timestamp, message)
                    task_info['status'] = 'stopped'
                    return False

                existing_topic = self._event_task_topics.get(task_name)
                already_listening = (
                    existing_topic == topic and
                    'event_wrapper' in task_info and
                    task_info.get('status') == 'listening'
                )

                if already_listening:
                    logger.info(
                        "Task '%s' is already listening on topic '%s'.",
                        task_name,
                        topic)
                    return True

                if existing_topic and existing_topic != topic:
                    self._unsubscribe_event_task(task_name, emit_status=False)

                try:
                    self._subscribe_event_task(task_name, topic)
                except Exception as exc:
                    message = (
                        f"Failed to subscribe task '{task_name}' to topic '{topic}': {exc}"
                    )
                    logger.error(message, exc_info=True)
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    global_signals.task_failed.emit(task_name, timestamp, message)
                    task_info['status'] = 'stopped'
                    self._event_task_topics.pop(task_name, None)
                    task_info.pop('event_wrapper', None)
                    return False

                logger.info(
                    f"Task '{task_name}' is now listening on topic: '{topic}'")
                return True

            logger.error(
                f"Task '{task_name}' uses a '{trigger_type}' trigger that "
                "cannot be scheduled with APScheduler.")
            return False

        # Load the actual function to be executed
        executable_func = self._load_task_executable(task_info['script'])
        if not executable_func:
            logger.error(
                f"Could not start task '{task_name}': script load failed.")
            return False

        # This wrapper will be called by APScheduler, and it submits the real
        # job
        def job_wrapper():
            logger.info(f"'{trigger_type}' trigger for task '{task_name}'. "
                        "Submitting to executor.")
            self.run_task(task_name, inputs={})

        try:
            params = dict(trigger_params)
            scheduler_option_keys = {
                'misfire_grace_time', 'max_instances', 'jitter',
                'next_run_time', 'jobstore', 'executor',
                'replace_existing', 'coalesce', 'start_date', 'end_date'
            }

            job_kwargs = {}
            for key in list(params):
                if key in scheduler_option_keys:
                    job_kwargs[key] = params.pop(key)

            trigger = trigger_type
            trigger_kwargs_for_add_job = dict(params)

            if trigger_type == 'cron':
                raw_expression = params.get('cron_expression')
                if raw_expression is None:
                    raw_expression = params.get('expression')

                cron_expression = None
                if isinstance(raw_expression, str):
                    cron_expression = raw_expression.strip()
                elif raw_expression is not None:
                    cron_expression = str(raw_expression).strip()

                if raw_expression is not None and not cron_expression:
                    message = (
                        f"Task '{task_name}' cron_expression is missing or empty. "
                        "Please provide a valid cron expression."
                    )
                    return emit_schedule_failure(message)

                used_cron_expression = bool(cron_expression)

                if used_cron_expression:
                    timezone = params.get('timezone')
                    try:
                        if timezone:
                            trigger = CronTrigger.from_crontab(
                                cron_expression, timezone=timezone)
                        else:
                            trigger = CronTrigger.from_crontab(cron_expression)
                    except Exception as exc:
                        message = (
                            f"Failed to parse cron expression for task "
                            f"'{task_name}': {exc}"
                        )
                        return emit_schedule_failure(message, exc=exc)

                    trigger_kwargs_for_add_job.clear()

                trigger_kwargs_for_add_job.pop('cron_expression', None)
                trigger_kwargs_for_add_job.pop('expression', None)
                if used_cron_expression:
                    trigger_kwargs_for_add_job.pop('timezone', None)
            else:
                trigger_kwargs_for_add_job.pop('cron_expression', None)
                trigger_kwargs_for_add_job.pop('expression', None)

            add_job_kwargs = {**trigger_kwargs_for_add_job, **job_kwargs}

            self.apscheduler.add_job(job_wrapper,
                                     id=task_name,
                                     name=task_name,
                                     trigger=trigger,
                                     **add_job_kwargs)
            self.tasks[task_name]['status'] = 'running'
            logger.info(
                f"Task '{task_name}' scheduled with trigger type '{trigger_type}' "
                f"and parameters {job_kwargs}.")
            global_signals.task_status_changed.emit(task_name, 'running')
            return True
        except Exception as e:
            task_info['status'] = 'stopped'
            logger.error(f"Failed to schedule task '{task_name}': {e}")
            return False

    def stop_task(self, task_name: str):
        """
        Stops a scheduled task by removing it from the APScheduler.

        Args:
            task_name (str): Name of the task to stop.

        Returns:
            bool: True if task was stopped successfully, False otherwise.
        """
        if task_name not in self.tasks:
            logger.error(f"Task '{task_name}' not found.")
            return False

        try:
            task_info = self.tasks[task_name]
            trigger_type, _ = self._parse_trigger(
                task_info.get('config_data', {}))
            if trigger_type == 'event':
                self._unsubscribe_event_task(task_name, emit_status=False)
                task_info['status'] = 'stopped'
                global_signals.task_status_changed.emit(task_name, 'stopped')
                return True

            job = self.apscheduler.get_job(task_name)
            if job:
                self.apscheduler.remove_job(task_name)
                logger.info(f"Task '{task_name}' removed from scheduler.")
            else:
                logger.warning(
                    f"Task '{task_name}' was not found in scheduler, could "
                    "not stop.")

            self.tasks[task_name]['status'] = 'stopped'
            global_signals.task_status_changed.emit(task_name, 'stopped')
            return True
        except Exception as e:
            logger.error(f"Failed to stop task '{task_name}': {e}")
            return False

    def resume_task(self, task_name: str):
        """
        Resumes a paused task in the APScheduler.

        Args:
            task_name (str): Name of the task to resume.

        Returns:
            bool: True if task was resumed successfully, False otherwise.
        """
        if task_name not in self.tasks:
            logger.error(f"Task '{task_name}' not found.")
            return False

        try:
            self.apscheduler.resume_job(task_name)
            self.tasks[task_name]['status'] = 'running'
            logger.info(f"Task '{task_name}' resumed.")
            global_signals.task_status_changed.emit(task_name, 'running')
            return True
        except Exception as e:
            logger.error(f"Failed to resume task '{task_name}': {e}")
            return False

    def pause_task(self, task_name: str):
        """
        Pauses a task in the APScheduler.

        Args:
            task_name (str): Name of the task to pause.

        Returns:
            bool: True if task was paused successfully, False otherwise.
        """
        if task_name not in self.tasks:
            logger.error(f"Task '{task_name}' not found.")
            return False

        try:
            self.apscheduler.pause_job(task_name)
            self.tasks[task_name]['status'] = 'paused'
            logger.info(f"Task '{task_name}' paused.")
            global_signals.task_status_changed.emit(task_name, 'paused')
            return True
        except Exception as e:
            logger.error(f"Failed to pause task '{task_name}': {e}")
            return False

    def start_all_tasks(self):
        """
        Starts all enabled tasks that are not currently running or listening.
        """
        for task_name, task_info in self.tasks.items():
            config = task_info.get('config_data', {})
            if not config.get('enabled', False):
                continue

            trigger_type, trigger_params = self._parse_trigger(config)

            if is_scheduled_trigger(trigger_type):
                if self.get_task_status(task_name) != 'running':
                    self.start_task(task_name)
            elif trigger_type == 'event':
                if self.get_task_status(task_name) == 'listening':
                    continue

                self.start_task(task_name)
            else:
                logger.warning(
                    "Task '%s' has an unknown trigger type: '%s'.",
                    task_name,
                    trigger_type)

    def pause_all_tasks(self):
        """
        Pauses all currently running scheduled tasks.
        """
        self.apscheduler.pause()
        for task_name in self.tasks:
            if self.get_task_status(task_name) == 'running':
                self.tasks[task_name]['status'] = 'paused'
                global_signals.task_status_changed.emit(task_name, 'paused')
        logger.info("All scheduled tasks paused.")

    def stop_all_tasks(self):
        """
        Stops all currently running or paused scheduled tasks.
        """
        self.apscheduler.remove_all_jobs()
        for task_name, task_info in self.tasks.items():
            trigger_type, _ = self._parse_trigger(
                task_info.get('config_data', {}))
            current_status = task_info.get('status')

            if trigger_type == 'event' or current_status == 'listening':
                # Ensure event-driven tasks are unsubscribed and emit stopped.
                self._unsubscribe_event_task(task_name, emit_status=True)
                continue

            if current_status in ['running', 'paused']:
                task_info['status'] = 'stopped'
                global_signals.task_status_changed.emit(task_name, 'stopped')
        logger.info("All scheduled tasks stopped.")

    def get_task_status(self, task_name: str) -> str:
        """
        Get the current status of a task.

        Args:
            task_name (str): Name of the task.

        Returns:
            str: Status of the task ('running', 'paused', 'stopped',
            'listening', 'not found').
        """
        if task_name not in self.tasks:
            return 'not found'

        task_info = self.tasks[task_name]
        trigger_type, _ = self._parse_trigger(
            task_info.get('config_data', {}))

        if trigger_type == 'event':
            return task_info.get('status', 'stopped')

        job = self.apscheduler.get_job(task_name)
        if not job:
            return 'stopped'

        if job.next_run_time is None:
            return 'paused'
        else:
            return 'running'

    def refresh(self):
        """
        Refresh the list of tasks by reloading from the directory.
        """
        logger.info("Refreshing task list.")
        self.load_tasks()


# TODO: Add support for data sync tasks with Google Sheet templates and
# authorization files
# TODO: Implement task execution logic with error handling and retry options
