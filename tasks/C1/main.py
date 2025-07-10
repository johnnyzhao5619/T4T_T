import json
import logging

# Use a standard logger for file-based logging, separate from UI emission.
file_logger = logging.getLogger(__name__)


def run(config, log_emitter, debug=False, config_path=None):
    """
    A simple counter task that increments a number and logs it to the UI.
    It persists the count by writing back to its own config file.
    """
    task_name = config.get('name', 'Unnamed Counter Task')
    log_emitter(f"INFO: Task '{task_name}' is running.")
    file_logger.info(f"Task '{task_name}' is running.")

    if not config_path:
        log_emitter(
            "ERROR: Config file path was not provided. Cannot save state.")
        file_logger.error(
            "Config file path was not provided. Cannot save state.")
        return

    try:
        # Get settings, using .get() for safety
        settings = config.get('settings', {})
        current_count = settings.get('current_count', 0)
        increment_by = settings.get('increment_by', 1)

        # Perform the core logic
        new_count = current_count + increment_by
        log_emitter(f"INFO: Count is now: {new_count}")

        # Update the value in the config dictionary
        config['settings']['current_count'] = new_count

        # Write the updated config back to the file
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
            log_emitter(
                f"INFO: Successfully saved new count ({new_count}) to config.")
        except Exception as e:
            log_emitter(
                f"ERROR: Failed to write updated config to '{config_path}': {e}"
            )
            file_logger.error(
                f"Failed to write updated config to '{config_path}': {e}")

        # Handle debug mode
        if debug:
            debug_message = settings.get('debug_message', 'Debug mode is on.')
            log_emitter(f"DEBUG: {debug_message}")

    except Exception as e:
        log_emitter(
            f"ERROR: An error occurred in the counter task '{task_name}': {e}")
        file_logger.error(
            f"An error occurred in the counter task '{task_name}': {e}")
