import os
import logging
import shutil
import importlib.util
from typing import Callable
from datetime import datetime
from functools import partial

from core.context import TaskContext, TaskContextFilter

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from core.module_manager import ModuleManager
from core.scheduler import SchedulerManager
from core.state_manager import StateManager
from utils.config import load_yaml, save_yaml
from utils.signals import global_signals
from utils.message_bus import message_bus_manager

logger = logging.getLogger(__name__)


class TaskManager:
    """
    Manages task instances, including creation, modification,
    deletion, and scheduling. Integrates with ModuleManager for
    task creation and TaskScheduler for execution.
    """

    def __init__(self,
                 scheduler_manager: SchedulerManager,
                 tasks_dir='tasks',
                 modules_dir='modules'):
        """
        Initialize the TaskManager with directories for tasks and modules.

        Args:
            scheduler_manager (SchedulerManager): The application's scheduler
                instance.
            tasks_dir (str): Directory path where task instances are stored.
            modules_dir (str): Directory path where module templates
                are stored.
        """
        self.tasks_dir = tasks_dir
        self.module_manager = ModuleManager(modules_dir)
        self.scheduler_manager = scheduler_manager
        self.state_manager = StateManager()
        self.apscheduler = BackgroundScheduler()
        self.tasks = {}

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
        self.tasks.clear()
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

            trigger_config = config.get('trigger', {})
            trigger_type = trigger_config.get('type')

            if trigger_type in ['cron', 'interval', 'date']:
                # For scheduled tasks, use the existing start_task method
                self.start_task(task_name)
            elif trigger_type == 'event':
                # For event-driven tasks, subscribe to the message bus
                topic = trigger_config.get('topic')
                if not topic:
                    msg = ("Event task '%s' is enabled but missing a 'topic' "
                           "in its trigger configuration.")
                    logger.error(msg, task_name)
                    continue

                wrapper_func = self._create_event_wrapper(task_name)
                message_bus_manager.subscribe(topic, wrapper_func)
                self.tasks[task_name]['status'] = 'listening'
                logger.info(
                    f"Task '{task_name}' is now listening on topic: '{topic}'")
                global_signals.task_status_changed.emit(task_name, 'listening')
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
            task_info = self.tasks[task_name]
            config = task_info['config_data']

            # 1. Cycle detection
            hops = payload.get('__hops', 0)
            max_hops = 5  # Define a reasonable threshold
            if hops > max_hops:
                logger.error(
                    f"Task '{task_name}' stopped: max hop count ({max_hops}) "
                    "exceeded. Possible infinite loop.")
                return

            # 2. Input validation
            inputs_schema = config.get('inputs', [])
            for item in inputs_schema:
                item_name = item.get('name')
                if item.get('required') and item_name not in payload:
                    logger.error(
                        f"Task '{task_name}' execution stopped: missing "
                        f"required input '{item_name}'.")
                    return

            # 3. Submit task for execution
            self._execute_task_logic(task_name, payload)

        return wrapper

    def _execute_task_logic(self, task_name: str, inputs: dict):
        """
        Handles the actual loading and execution of a task, including
        result signal emission.
        """
        task_info = self.tasks[task_name]
        executable_func = self._load_task_executable(task_info['script'])
        if not executable_func:
            return

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            task_logger = task_info.get('logger', logger)
            context = TaskContext(
                task_name=task_name,
                logger=task_logger,
                config=task_info['config_data'],
                task_path=task_info['path'],
                state_manager=self.state_manager  # Inject StateManager
            )

            # Using partial to prepare the function call for the executor
            task_callable = partial(executable_func)

            # Submit to the thread pool and get a future
            future = self.scheduler_manager.submit(task_callable,
                                                   context=context,
                                                   inputs=inputs)

            def task_done_callback(fut):
                try:
                    # Check if the task raised an exception
                    result = fut.result()
                    msg = f"Task completed successfully. Result: {result}"
                    global_signals.task_succeeded.emit(task_name, timestamp,
                                                       msg)
                    logger.info(f"Task '{task_name}' finished successfully.")
                except Exception as e:
                    error_msg = f"Task execution failed: {e}"
                    global_signals.task_failed.emit(task_name, timestamp,
                                                    error_msg)
                    logger.error(f"Task '{task_name}' failed: {e}",
                                 exc_info=True)

            future.add_done_callback(task_done_callback)

        except Exception as e:
            # This catches errors during submission itself
            error_msg = f"Failed to submit task to executor: {e}"
            global_signals.task_failed.emit(task_name, timestamp, error_msg)
            logger.error(f"Error submitting task '{task_name}': {e}",
                         exc_info=True)

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

    def create_task(self, task_name: str, module_type: str) -> bool:
        """
        Creates a new task instance from a module template.

        Args:
            task_name (str): The name for the new task. Must be unique.
            module_type (str): The module type to use as a template.

        Returns:
            bool: True if creation was successful, False otherwise.
        """
        if not task_name:
            logger.error("Task name cannot be empty.")
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

            save_yaml(config_dest, config_data)

            # Special handling for 'DataSync' module type
            if module_type == "DataSync":
                # These files should exist in a predefined location, e.g.,
                # 'templates/auth', For now, we'll assume they are in the
                # module directory for simplicity
                module_dir = os.path.dirname(templates['py_template'])
                creds_src = os.path.join(module_dir, "credentials.json")
                token_src = os.path.join(module_dir, "token.json")
                if os.path.exists(creds_src):
                    shutil.copy(creds_src,
                                os.path.join(task_path, "credentials.json"))
                if os.path.exists(token_src):
                    shutil.copy(token_src,
                                os.path.join(task_path, "token.json"))

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
            task_path = self.tasks[task_name]['path']
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
            self.tasks[new_name] = task_data

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

        # Return a copy to prevent modification of the in-memory cache
        return self.tasks[task_name].get('config_data', {}).copy()

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
            else:
                # If renaming fails, abort the save.
                return False, task_name

        try:
            # Use the potentially new task name to get the config file path
            config_file = self.tasks[final_task_name]['config']
            save_yaml(config_file, config_data)

            # Update the in-memory cache
            self.tasks[final_task_name]['config_data'] = config_data

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
        try:
            spec = importlib.util.spec_from_file_location(
                "task_module", script_path)
            task_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(task_module)

            if hasattr(task_module, 'run') and callable(
                    getattr(task_module, 'run')):
                return getattr(task_module, 'run')
            else:
                logger.error(f"Script '{script_path}' does not have a callable"
                             " 'run' function.")
                return None
        except Exception as e:
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
        trigger_config = config.get('trigger', {})
        trigger_type = trigger_config.get('type')
        trigger_params = trigger_config.get('config', {})

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
            self._execute_task_logic(task_name, inputs={})

        try:
            # Special handling for cron triggers to support cron_expression
            if trigger_type == 'cron' and 'cron_expression' in trigger_params:
                cron_expr = trigger_params.pop('cron_expression')
                if cron_expr:
                    trigger = CronTrigger.from_crontab(cron_expr,
                                                       **trigger_params)
                else:
                    # If cron_expression is empty, don't schedule the job
                    logger.warning(
                        f"Task '{task_name}' has an empty cron_expression and "
                        "will not be scheduled.")
                    return True
            else:
                trigger = trigger_type

            # Add job to APScheduler
            self.apscheduler.add_job(job_wrapper,
                                     id=task_name,
                                     name=task_name,
                                     trigger=trigger,
                                     **trigger_params)
            self.tasks[task_name]['status'] = 'running'
            logger.info(
                f"Task '{task_name}' scheduled with trigger: {trigger_config}")
            global_signals.task_status_changed.emit(task_name, 'running')
            return True
        except Exception as e:
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
        Starts all enabled tasks that are not currently running.
        """
        # Reloads and initializes all tasks based on config
        self.load_tasks()

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
        for task_name in self.tasks:
            if self.tasks[task_name].get('status') in ['running', 'paused']:
                self.tasks[task_name]['status'] = 'stopped'
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
        trigger_config = task_info.get('config_data', {}).get('trigger', {})
        trigger_type = trigger_config.get('type')

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
