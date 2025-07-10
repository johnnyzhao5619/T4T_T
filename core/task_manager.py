import os
import logging
import json
import shutil
import importlib.util
from functools import partial
from core.module_manager import ModuleManager
from core.scheduler import SchedulerManager
from utils.signals import a_signal

logger = logging.getLogger(__name__)


class TaskManager:
    """
    Manages task instances, including creation, modification,
    deletion, and scheduling. Integrates with ModuleManager for
    task creation and TaskScheduler for execution.
    """

    def __init__(self, tasks_dir='tasks', modules_dir='modules'):
        """
        Initialize the TaskManager with directories for tasks and modules.

        Args:
            tasks_dir (str): Directory path where task instances are stored.
            modules_dir (str): Directory path where module templates
            are stored.
        """
        self.tasks_dir = tasks_dir
        self.module_manager = ModuleManager(modules_dir)
        self.tasks = {}
        self.load_tasks()
        logger.info(
            f"TaskManager initialized with tasks directory: {tasks_dir}")

    def load_tasks(self):
        """
        Load all task instances from the tasks directory.
        Each task is expected to have a subfolder with main.py and config.json.
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
                config_file = os.path.join(task_path, "config.json")

                if os.path.exists(script_file) and os.path.exists(config_file):
                    try:
                        with open(config_file, 'r', encoding='utf-8') as f:
                            config_data = json.load(f)
                        self.tasks[task_name] = {
                            'path': task_path,
                            'script': script_file,
                            'config': config_file,
                            'config_data': config_data,
                            'status': 'stopped'
                        }
                        logger.info(f"Task '{task_name}' loaded.")
                    except Exception as e:
                        logger.error(f"Failed to load task '{task_name}': {e}")
                else:
                    logger.warning(
                        f"Task '{task_name}' is missing main.py or config.json."
                    )
        logger.info(f"Loaded {len(self.tasks)} tasks.")

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

    def get_running_task_count(self, scheduler: SchedulerManager) -> int:
        """
        Get the number of tasks that are currently running.

        Args:
            scheduler (SchedulerManager): The scheduler instance.

        Returns:
            int: The number of running tasks.
        """
        running_count = 0
        for task_name in self.tasks:
            if self.get_task_status(task_name, scheduler) == 'running':
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
            config_dest = os.path.join(task_path, "config.json")

            # Copy and rename templates
            shutil.copy(templates['py_template'], script_dest)

            # Read the original config, add name and module_type, then write
            with open(templates['json_template'], 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            config_data['name'] = task_name
            config_data['module_type'] = module_type

            with open(config_dest, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4)

            # Special handling for 'DataSync' module type
            if module_type == "DataSync":
                # These files should exist in a predefined location, e.g., 'templates/auth'
                # For now, we'll assume they are in the module directory for simplicity
                module_dir = os.path.dirname(templates['py_template'])
                creds_src = os.path.join(module_dir, "credentials.json")
                token_src = os.path.join(module_dir, "token.json")
                if os.path.exists(creds_src):
                    shutil.copy(creds_src,
                                os.path.join(task_path, "credentials.json"))
                if os.path.exists(token_src):
                    shutil.copy(token_src,
                                os.path.join(task_path, "token.json"))

            logger.info(
                f"Task '{task_name}' created successfully from module '{module_type}'."
            )
            self.load_tasks()  # Refresh task list
            a_signal.task_manager_updated.emit()
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
            a_signal.task_manager_updated.emit()
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
            task_data['config'] = os.path.join(new_path, "config.json")
            task_data['script'] = os.path.join(new_path, "main.py")
            self.tasks[new_name] = task_data

            logger.info(
                f"Task '{old_name}' successfully renamed to '{new_name}'.")
            a_signal.task_renamed.emit(old_name, new_name)
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
        Loads the schema for a given task from 'schema.json'.

        Args:
            task_name (str): The name of the task.

        Returns:
            dict: The loaded schema, or an empty dict if not found or on error.
        """
        if task_name not in self.tasks:
            logger.error(f"Cannot get schema: Task '{task_name}' not found.")
            return {}

        schema_path = os.path.join(self.tasks[task_name]['path'],
                                   'schema.json')
        if not os.path.exists(schema_path):
            # It's not an error to not have a schema, just return empty
            return {}

        try:
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema_data = json.load(f)
            return schema_data
        except json.JSONDecodeError:
            logger.error(f"Error decoding schema.json for task '{task_name}'.")
            return {}
        except Exception as e:
            logger.error(f"Failed to load schema for task '{task_name}': {e}")
            return {}

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
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4)

            # Update the in-memory cache
            self.tasks[final_task_name]['config_data'] = config_data
            logger.info(f"Task '{final_task_name}' configuration updated.")
            return True, final_task_name
        except Exception as e:
            logger.error(
                f"Failed to update config for task '{final_task_name}': {e}")
            return False, final_task_name

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
                logger.error(
                    f"Script '{script_path}' does not have a callable 'run' function."
                )
                return None
        except Exception as e:
            logger.error(
                f"Failed to load task module from '{script_path}': {e}")
            return None

    def start_task(self, task_name, scheduler: SchedulerManager):
        """
        Start a task by scheduling it with the provided scheduler.
        """
        if task_name not in self.tasks:
            logger.error(f"Task {task_name} not found.")
            return False

        task_info = self.tasks[task_name]
        script_path = task_info['script']
        config_data = task_info['config_data']
        schedule_config = config_data.get('schedule', {})
        debug_mode = config_data.get('debug', False)

        # Fallback for old string-based cron schedule
        if isinstance(schedule_config, str):
            schedule_config = {
                'trigger': 'cron',
                'expression': schedule_config
            }

        # --- Threading Strategy ---
        # IMPORTANT: Check module type BEFORE loading any code to avoid
        # thread-safety issues with libraries like pynput on macOS.
        module_type = config_data.get('module_type')

        if module_type == 'screen_protector':
            # For pynput on macOS, all related code must run on the main thread.
            # We schedule a simple lambda that only emits a signal with the
            # task name. The main window handles all loading and execution.
            job_to_schedule = lambda: a_signal.execute_in_main_thread.emit(
                task_name)
            logger.info(
                f"Task '{task_name}' is type '{module_type}', scheduling for main thread execution via signal."
            )
        else:
            # For standard tasks, load the executable and schedule it directly
            # to run in a background thread.
            executable_func = self._load_task_executable(script_path)
            if not executable_func:
                logger.error(
                    f"Could not start task '{task_name}' due to loading failure."
                )
                return False

            log_emitter = partial(a_signal.log_message.emit, task_name)
            job_to_schedule = partial(executable_func,
                                      config=config_data,
                                      log_emitter=log_emitter,
                                      debug=debug_mode,
                                      config_path=task_info['config'])

        try:
            success = scheduler.add_task(task_name, job_to_schedule,
                                         schedule_config)
            if success:
                self.tasks[task_name]['status'] = 'running'
                self.tasks[task_name]['config_data']['enabled'] = True
                self.save_task_config(task_name,
                                      self.tasks[task_name]['config_data'])
                logger.info(f"Task '{task_name}' started successfully.")
                a_signal.task_status_changed.emit(task_name, 'running')
            return success
        except Exception as e:
            logger.error(f"Failed to schedule task '{task_name}': {e}")
            return False

    def stop_task(self, task_name, scheduler: SchedulerManager):
        """
        Stop a task by removing it from the scheduler.

        Args:
            task_name (str): Name of the task to stop.
            scheduler (SchedulerManager): Scheduler instance managing the task.

        Returns:
            bool: True if task was stopped successfully, False otherwise.
        """
        if task_name not in self.tasks:
            logger.error(f"Task {task_name} not found.")
            return False

        try:
            success = scheduler.remove_task(task_name)
            if success:
                self.tasks[task_name]['status'] = 'stopped'
                self.tasks[task_name]['config_data']['enabled'] = False
                self.save_task_config(task_name,
                                      self.tasks[task_name]['config_data'])
                logger.info(
                    f"Task {task_name} stopped and removed from scheduler.")
                a_signal.task_status_changed.emit(task_name, 'stopped')
            return success
        except Exception as e:
            logger.error(f"Failed to stop task {task_name}: {str(e)}")
            return False

    def resume_task(self, task_name, scheduler: SchedulerManager):
        """
        Resume a paused task in the scheduler.

        Args:
            task_name (str): Name of the task to resume.
            scheduler (SchedulerManager): Scheduler instance managing the task.

        Returns:
            bool: True if task was resumed successfully, False otherwise.
        """
        if task_name not in self.tasks:
            logger.error(f"Task {task_name} not found.")
            return False

        try:
            success = scheduler.resume_task(task_name)
            if success:
                self.tasks[task_name]['status'] = 'running'
                logger.info(f"Task {task_name} resumed.")
            return success
        except Exception as e:
            logger.error(f"Failed to resume task {task_name}: {str(e)}")
            return False

    def get_task_status(self, task_name, scheduler: SchedulerManager):
        """
        Get the current status of a task.

        Args:
            task_name (str): Name of the task.
            scheduler (SchedulerManager): Scheduler instance managing the task.

        Returns:
            str: Status of the task ('running', 'paused', 'stopped',
            'not found').
        """
        if task_name not in self.tasks:
            return 'not found'
        status = scheduler.get_task_status(task_name)
        self.tasks[task_name][
            'status'] = status if status != 'not found' else 'stopped'
        return self.tasks[task_name]['status']

    def refresh(self):
        """
        Refresh the list of tasks by reloading from the directory.
        """
        logger.info("Refreshing task list.")
        self.load_tasks()


# TODO: Add support for data sync tasks with Google Sheet templates and authorization files
# TODO: Implement task execution logic with error handling and retry options
