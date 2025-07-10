import time
import random
import logging
import os
import json
from pynput import mouse

# Use a standard logger for file-based logging, separate from UI emission.
file_logger = logging.getLogger(__name__)

# State is now managed within the run function using a state file.


def jiggle_mouse(config, log_emitter):
    """
    Jiggles the mouse to simulate activity. This is the only action
    performed by this simplified task.
    """
    try:
        mouse_controller = mouse.Controller()
        original_pos = mouse_controller.position

        settings = config.get('settings', {})
        min_jiggle = settings.get('mouse_jiggle_range_min', 10)
        max_jiggle = settings.get('mouse_jiggle_range_max', 50)

        dx = random.randint(min_jiggle, max_jiggle) * random.choice([-1, 1])
        dy = random.randint(min_jiggle, max_jiggle) * random.choice([-1, 1])

        new_pos = (original_pos[0] + dx, original_pos[1] + dy)
        mouse_controller.move(dx, dy)
        time.sleep(0.1)
        mouse_controller.position = original_pos

        action_msg = (
            f"System idle, simulated mouse jiggle from {original_pos} to "
            f"{new_pos} and back."
        )
        log_emitter(f"INFO: {action_msg}")
        return action_msg
    except Exception as e:
        error_msg = f"Failed to jiggle mouse: {e}"
        log_emitter(f"ERROR: {error_msg}")
        file_logger.error(error_msg)
        return error_msg


def run(config, log_emitter, debug=False, config_path=None):
    """
    Main entry point for the screen protector task.
    It checks for mouse movement and persists the last known position
    in a state file to detect inactivity across multiple runs.
    """
    if not config_path:
        log_emitter("ERROR: config_path not provided, cannot manage state.")
        return

    state_file = os.path.join(os.path.dirname(config_path), "state.json")

    try:
        with open(state_file, 'r') as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}

    last_position = state.get('last_position')

    mouse_controller = mouse.Controller()
    current_position = mouse_controller.position

    if debug:
        log_emitter(
            f"DEBUG: Checking activity. Current: {current_position}, "
            f"Last: {last_position}"
        )

    if last_position is None:
        state['last_position'] = list(current_position)
        log_emitter("INFO: Initializing mouse position.")
    elif tuple(last_position) == current_position:
        if debug:
            log_emitter("DEBUG: Mouse has not moved. Jiggling.")
        jiggle_mouse(config, log_emitter)
    else:
        if debug:
            log_emitter(
                f"DEBUG: Mouse moved to {current_position}. Updating position."
            )
        state['last_position'] = list(current_position)

    with open(state_file, 'w') as f:
        json.dump(state, f)
