# -*- coding: utf-8 -*-
import os
import json
import logging
from threading import Lock

logger = logging.getLogger(__name__)


class StateManager:
    """
    Manages the state of all tasks in memory, with an option for
    on-disk persistence.
    """

    def __init__(self):
        self._states = {}
        self._locks = {}
        self._manager_lock = Lock()

    def get_task_lock(self, task_name: str) -> Lock:
        """
        Retrieves a lock for a specific task to ensure thread-safe
        state modifications.
        """
        with self._manager_lock:
            if task_name not in self._locks:
                self._locks[task_name] = Lock()
            return self._locks[task_name]

    def load_state(self, task_name: str, task_path: str):
        """
        Loads state from a file into memory for a single task if it exists.
        """
        state_file = os.path.join(task_path, 'state.json')
        if os.path.exists(state_file):
            try:
                if os.path.getsize(state_file) > 0:
                    with open(state_file, 'r', encoding='utf-8') as f:
                        with self.get_task_lock(task_name):
                            self._states[task_name] = json.load(f)
                    logger.debug(f"State for '{task_name}' loaded from "
                                 f"'{state_file}'.")
                else:
                    with self.get_task_lock(task_name):
                        self._states[task_name] = {}
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load state for '{task_name}': {e}")
                self._states.setdefault(task_name, {})
        else:
            self._states.setdefault(task_name, {})

    def get_state(self, task_name: str, key: str, default=None):
        """
        Retrieves a value from the in-memory state for a given task.
        """
        with self.get_task_lock(task_name):
            return self._states.get(task_name, {}).get(key, default)

    def update_state(self, task_name: str, key: str, value: any):
        """
        Updates a value in the in-memory state for a given task.
        """
        with self.get_task_lock(task_name):
            if task_name not in self._states:
                self._states[task_name] = {}
            self._states[task_name][key] = value

    def save_state(self, task_name: str, task_path: str):
        """
        Saves the in-memory state of a single task to its state.json file.
        """
        state_file = os.path.join(task_path, 'state.json')
        with self.get_task_lock(task_name):
            if task_name in self._states:
                try:
                    with open(state_file, 'w', encoding='utf-8') as f:
                        json.dump(self._states[task_name], f, indent=4)
                    logger.debug(f"State for '{task_name}' saved to "
                                 f"'{state_file}'.")
                except IOError as e:
                    logger.error(
                        f"Failed to save state for '{task_name}': {e}")

    def save_all_states(self, tasks: dict):
        """
        Saves the state for all tasks that are configured for persistence.
        """
        logger.info("Saving states for all "
                    "tasks configured for persistence...")
        for task_name, task_info in tasks.items():
            if task_info.get('config_data', {}).get('persist_state', False):
                self.save_state(task_name, task_info['path'])

    def rename_task(self, old_name: str, new_name: str) -> None:
        """Rename the in-memory state and lock entries for a task.

        This keeps the state manager aligned with renamed task folders while
        ensuring that concurrent updates remain thread-safe.
        """
        if old_name == new_name:
            return

        task_lock = self.get_task_lock(old_name)

        with task_lock:
            with self._manager_lock:
                if old_name in self._states:
                    self._states[new_name] = self._states.pop(old_name)
                else:
                    self._states.setdefault(new_name, {})

                # Move the lock reference to the new task name so that future
                # requests reuse the same lock instance.
                existing_lock = self._locks.pop(old_name, task_lock)
                self._locks[new_name] = existing_lock
