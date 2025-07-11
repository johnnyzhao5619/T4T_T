# -*- coding: utf-8 -*-
"""
This is a template for a new module.

To create a new module, copy this directory and rename it to your module's
name.
Then, rename the files to match the directory name.
"""

import json
import logging
import os

# Standard logger for file-based logging. This is separate from the UI log.
# It's good practice to use this for detailed, developer-focused logging.
file_logger = logging.getLogger(__name__)


def run(config, log_emitter, debug=False, config_path=None):
    """
    Main entry point for the module's task.

    This function is called by the scheduler based on the settings in the
    accompanying JSON configuration file.

    Args:
        config (dict): The configuration for this task, loaded from the
                       associated `_template.json` file.
        log_emitter (function): A callable that sends log messages to the UI.
                                Use this for user-facing information.
        debug (bool): A flag indicating if debug mode is enabled in the config.
        config_path (str): The absolute path to the task's JSON config file.
                           Useful for persisting state.
    """
    task_name = config.get('name', 'Unnamed Task')

    # Always good to log the start of a task run.
    log_emitter(f"INFO: Task '{task_name}' has started.")
    file_logger.info(f"Task '{task_name}' started. Config Path: {config_path}")

    # --- Core Task Logic ---
    # Replace this section with the actual logic for your task.
    try:
        # Example: Accessing custom settings from the config file.
        settings = config.get('settings', {})
        example_setting = settings.get('example_setting', 'default_value')

        if debug:
            log_emitter(f"DEBUG: Debug mode is enabled for '{task_name}'.")
            debug_message = settings.get('debug_message',
                                         'No debug message set.')
            log_emitter(f"DEBUG: Message from settings: {debug_message}")
            log_emitter(
                f"DEBUG: 'example_setting' is currently: '{example_setting}'")
            file_logger.debug(f"Full config for {task_name}: {config}")

        log_emitter(
            f"INFO: The value of 'example_setting' is: {example_setting}")

        # Example: Performing a simple operation.
        # This is where your module's main functionality would go.
        result = (f"Task '{task_name}' completed successfully with setting: "
                  f"{example_setting}")
        log_emitter(f"INFO: {result}")
        file_logger.info(result)

    except Exception as e:
        # It's crucial to handle exceptions to prevent the entire application
        # from crashing if one task fails.
        error_message = f"An error occurred in '{task_name}': {e}"
        log_emitter(f"ERROR: {error_message}")
        file_logger.exception(error_message)  # .exception logs stack trace

    # --- State Management (Optional) ---
    # If your task needs to remember information between runs, you can
    # persist state. Here are two common methods:

    # Method 1: Modifying the main config file.
    # Good for simple state. Be careful with frequent writes.
    if config_path:
        try:
            # Example: Incrementing a run counter.
            run_count = config.get('run_count', 0) + 1
            config['run_count'] = run_count

            # Write the updated config back to the file.
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)

            log_emitter(f"INFO: Task has been run {run_count} times.")
            file_logger.info(
                f"Updated run_count to {run_count} in {config_path}")

        except Exception as e:
            error_message = (
                f"Failed to update config file at {config_path}: {e}")
            log_emitter(f"ERROR: {error_message}")
            file_logger.error(error_message)

    # Method 2: Using a separate state file.
    # Better for complex state or to keep the config file clean.
    if config_path:
        state_file_path = os.path.join(os.path.dirname(config_path),
                                       'state.json')
        try:
            # Load existing state or initialize a new one.
            if os.path.exists(state_file_path):
                with open(state_file_path, 'r', encoding='utf-8') as f:
                    state = json.load(f)
            else:
                state = {}

            # Update state
            state['last_run_timestamp'] = file_logger.name  # Just an example
            state['some_other_data'] = "Example data"

            # Write state back to the file.
            with open(state_file_path, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=4)

            file_logger.info(f"State updated in {state_file_path}")

        except Exception as e:
            error_message = (
                f"Failed to manage state file at {state_file_path}: {e}")
            log_emitter(f"ERROR: {error_message}")
            file_logger.error(error_message)

    log_emitter(f"INFO: Task '{task_name}' has finished.")
    file_logger.info(f"Task '{task_name}' finished.")
