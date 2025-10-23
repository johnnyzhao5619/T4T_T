# -*- coding: utf-8 -*-
"""
V2 Screen Protector Module
Checks for mouse inactivity and jiggles the mouse if the system is idle.
State is managed by the context object.
"""
import random
import pyautogui


def run(context, inputs):
    """
    Main entry point for the screen protector task.

    Args:
        context: The task context object.
        inputs (dict): Not used in this module.
    """
    task_name = context.task_name
    context.logger.debug(f"Task '{task_name}' is running.")

    try:
        # Use context.get_state to retrieve the previous mouse position
        last_position = context.get_state('last_position')
        current_position = list(pyautogui.position())

        context.logger.debug(
            f"Checking activity. Current position: {current_position}, previous position: {last_position}")

        # Compare the current position with the last saved position
        if last_position and last_position == current_position:
            # Idle detected: jiggle the mouse
            context.logger.info("System appears idle; moving the mouse.")

            settings = context.config.get('settings', {})
            min_jiggle = settings.get('mouse_jiggle_range_min', 10)
            max_jiggle = settings.get('mouse_jiggle_range_max', 50)

            dx = (random.randint(min_jiggle, max_jiggle) *
                  random.choice([-1, 1]))
            dy = (random.randint(min_jiggle, max_jiggle) *
                  random.choice([-1, 1]))

            pyautogui.moveRel(dx, dy)
            new_pos = list(pyautogui.position())

            context.logger.info(
                f"Mouse moved from {current_position} to {new_pos}.")

            # Update current_position to reflect the new location after moving
            current_position = new_pos
        else:
            # Not idle or this is the first execution
            context.logger.debug(
                f"Mouse activity detected or first run. Updating position to {current_position}.")

        # Use context.update_state to persist the current position for the next run
        context.update_state('last_position', current_position)

    except Exception as e:
        context.logger.error(
            f"Screen protector task '{task_name}' encountered an error: {e}",
            exc_info=True)
