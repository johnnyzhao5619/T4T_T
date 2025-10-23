# -*- coding: utf-8 -*-
"""
Module task template V2
Starter template for building a new module task.

To create a new module, copy this directory and rename it to match your module name.
Then rename this file so it matches the directory name.
"""


def run(context, inputs):
    """
    Entry point for the module task.
    The system invokes this function when the trigger defined in manifest.yaml is satisfied.

    Args:
        context: Provides task context information, including logging, configuration,
                 and state helpers. Key attributes include:
                 - context.logger: Logger instance that reports to the UI and log files.
                   Usage:
                       context.logger.info("This is an info log")
                       context.logger.warning("This is a warning log")
                       context.logger.error("This is an error log")
                       context.logger.debug("This is a debug log")

                 - context.task_name (str): Task name from manifest.yaml.
                   Usage:
                       task_name = context.task_name
                       context.logger.info(f"Task '{task_name}' started")

                 - context.config (dict): Task configuration dictionary sourced from manifest.yaml.
                   Usage:
                       api_key = context.config.get("settings", {}).get("api_key")

                 - context.get_state(key, default=None): Fetch a persisted state value.
                   Usage:
                       last_run = context.get_state("last_run_timestamp")

                 - context.update_state(key, value): Persist or update a state value.
                   Usage:
                       from datetime import datetime
                       context.update_state("last_run_timestamp", datetime.now().isoformat())

        inputs (dict): Data mapped from the triggering payload.
                       Inputs are declared in the 'inputs' section of manifest.yaml.
                       When an input is marked 'required: true', the system validates
                       its presence before invoking this function.
                       Usage:
                           user_id = inputs.get("user_id")
                           if user_id:
                               context.logger.info(f"Processing request for user {user_id}")
    """
    task_name = context.task_name
    context.logger.info(f"Task '{task_name}' has started.")

    # --- Core task logic ---
    # Replace this block with the actual implementation of your task.
    try:
        # Example: Access inputs and settings
        context.logger.info(f"Received inputs: {inputs}")

        message = inputs.get("message", "No message provided")
        context.logger.info(f"Incoming message: '{message}'")

        # Example: Read custom settings declared in manifest.yaml
        settings = context.config.get('settings', {})
        example_setting = settings.get('example_setting', 'default value')
        context.logger.info(f"'example_setting' is set to: '{example_setting}'")

        # Example: Use state management
        run_count = context.get_state("run_count", 0) + 1
        context.update_state("run_count", run_count)
        context.logger.info(f"This is run number {run_count} for the task.")

        context.logger.info(f"Task '{task_name}' completed successfully.")

    except Exception as e:
        # Key point: handle exceptions so a single task failure does not crash the application.
        context.logger.error(f"Task '{task_name}' encountered an error: {e}", exc_info=True)

    context.logger.info(f"Task '{task_name}' has finished.")
