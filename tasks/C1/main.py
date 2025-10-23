# -*- coding: utf-8 -*-
"""
V2 Counter Module
A simple counter task that increments a number and logs it.
It persists the count using the context's state management.
"""


def run(context, inputs):
    """
    Main entry point for the counter task.

    Args:
        context: The task context object, providing access to logging, config,
                 and state management.
        inputs (dict): Data from the triggering event payload. For this module,
                       it might contain an optional 'increment_by' value.
    """
    task_name = context.task_name
    context.logger.info(f"Task '{task_name}' is running.")

    try:
        # Read the increment from 'inputs' when available, otherwise fall back to the settings value
        # This lets event payloads override the default increment dynamically
        default_increment = context.config.get('settings', {})\
                                          .get('increment_by', 1)
        increment_by = inputs.get('increment_by', default_increment)

        # Retrieve the current count; default to 0 if no state has been stored yet
        current_count = context.get_state('count', 0)

        # Execute the core logic
        new_count = current_count + increment_by
        context.logger.info(f"Counter updated to: {new_count}")

        # Persist the updated count for the next run
        context.update_state('count', new_count)
        context.logger.info(f"Successfully saved the updated count ({new_count}).")

    except Exception as e:
        context.logger.error(f"Counter task '{task_name}' encountered an error: {e}", exc_info=True)
