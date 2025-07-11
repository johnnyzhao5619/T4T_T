import random
import logging
import os
import json
import pyautogui

# Use a standard logger for file-based logging.
file_logger = logging.getLogger(__name__)


def run(config, log_emitter, debug=False, config_path=None):
    """
    Main entry point for the screen protector task.
    It checks for mouse inactivity by comparing the current mouse position
    with the position from the previous run, stored in a state file.
    """
    if not config_path:
        log_emitter("ERROR: config_path not provided, cannot manage state.")
        return

    # Define the path for the state file within the task's directory
    state_file = os.path.join(os.path.dirname(config_path), "state.json")

    # Check if state file exists, create if it doesn't
    if not os.path.exists(state_file):
        log_emitter("INFO: State file not found. Creating a new one.")
        state = {}
        try:
            with open(state_file, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            log_emitter(f"ERROR: Could not create state file: {e}")
            return  # Exit if we can't create the state file
    else:
        # Load the last known state
        try:
            with open(state_file, 'r') as f:
                state = json.load(f)
        except json.JSONDecodeError:
            log_emitter("WARNING: State file is corrupted. Resetting state.")
            state = {}
        except Exception as e:
            log_emitter(f"ERROR: Could not read state file: {e}")
            return  # Exit if we can't read the state file

    last_position = state.get('last_position')
    current_position = list(pyautogui.position())

    if debug:
        log_emitter(f"DEBUG: Checking activity. Current: {current_position}, "
                    f"Last: {last_position}")

    # Compare current position with the last saved position
    if last_position and last_position == current_position:
        # Idle detected: move the mouse
        if debug:
            log_emitter("DEBUG: Mouse has not moved. Simulating movement.")

        try:
            settings = config.get('settings', {})
            min_jiggle = settings.get('mouse_jiggle_range_min', 10)
            max_jiggle = settings.get('mouse_jiggle_range_max', 50)

            dx = random.randint(min_jiggle, max_jiggle) * random.choice(
                [-1, 1])
            dy = random.randint(min_jiggle, max_jiggle) * random.choice(
                [-1, 1])

            pyautogui.moveRel(dx, dy)
            new_pos = list(pyautogui.position())

            action_msg = (
                f"System idle, moved mouse from {current_position} to "
                f"{new_pos}.")
            log_emitter(f"INFO: {action_msg}")
            file_logger.info(action_msg)

            # Update current_position to the new position after moving
            current_position = new_pos

        except Exception as e:
            error_msg = f"Failed to move mouse: {e}"
            log_emitter(f"ERROR: {error_msg}")
            file_logger.error(error_msg)
    else:
        # Not idle or first run
        if debug:
            log_emitter("DEBUG: Mouse is active or this is the first run. "
                        f"Updating position to {current_position}.")

    # Save the current position for the next run
    state['last_position'] = current_position
    try:
        with open(state_file, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        error_msg = f"Failed to write to state file {state_file}: {e}"
        log_emitter(f"ERROR: {error_msg}")
        file_logger.error(error_msg)
