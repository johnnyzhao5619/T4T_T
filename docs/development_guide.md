# T4T Module Development Guide (v1.0)

## 1. Introduction

Welcome to the official module development guide for the T4T Task Management Platform. This document provides a comprehensive overview of the module system, architectural context, and best practices to help you build powerful, stable, and well-integrated modules.

Modules are the primary way to extend the functionality of T4T, allowing you to automate virtually any task.

---

## 2. Project Architecture Overview

To write effective modules, it's helpful to understand how they fit into the T4T ecosystem. The core of the application resides in the `core/` directory and consists of three main components:

- **`ModuleManager`**: Responsible for discovering modules in the `modules/` directory. It reads the `_template.json` files to understand what modules are available.
- **`TaskManager`**: Manages the lifecycle of individual tasks. When you create a task from a module, the TaskManager creates a specific instance of it, copying the module's template to a new directory in `tasks/`. It handles starting, stopping, and configuring these task instances.
- **`Scheduler` (`apscheduler`)**: The engine that runs your code. It reads the `schedule` from a task's `config.json` and executes the module's `run` function accordingly.

**The Module Lifecycle:**

1. **Discovery**: On startup, `ModuleManager` scans `modules/` for valid modules.
2. **Instantiation**: When a user creates a new task, `TaskManager` copies the chosen module's template to `tasks/<TaskName>/`.
3. **Scheduling**: When a task is started, `TaskManager` adds a job to the `Scheduler`.
4. **Execution**: At the scheduled time, `Scheduler` calls the `run` function in the task's `main.py`.

---

## 3. Quick Start: "Hello World"

This tutorial will guide you through creating a simple module.

1. **Create from Template**: Use the "Create New Module" button in the "Development Guide" tab to create a module named `hello_world`.
2. **Customize Script** (`modules/hello_world/hello_world_template.py`):

    ```python
    # --- Core Task Logic ---
    try:
        log_emitter("INFO: Hello, World from my first module!")
    except Exception as e:
        log_emitter(f"ERROR: An error occurred: {e}")
    ```

3. **Run the Task**: Create a new task from the `hello_world` module type, start it, and check the logs.

---

## 4. Core Script (`_template.py`) In-Depth

### The `run` Function Signature

`def run(config, log_emitter, debug=False, config_path=None):`

- `config` (dict): The **live configuration** for the specific task instance, loaded from `tasks/<TaskName>/config.json`.
- `log_emitter` (function): Your primary way to communicate with the user. It sends messages to the UI's log panel for that task.
- `debug` (bool): `True` if the "Debug Mode" switch is enabled for the task in the UI.
- `config_path` (str): The absolute path to the task's `config.json`. **This is essential for state management.**

### Logging Best Practices

- **`log_emitter` (for Users)**: Always prefix with a level (`INFO`, `WARNING`, `ERROR`, `DEBUG`). This is crucial for log filtering in the UI.

  ```python
  log_emitter("INFO: Task started successfully.")
  log_emitter("WARNING: Optional setting 'x' not found, using default.")
  ```

- **`file_logger` (for Developers)**: For detailed debugging. These logs go to the `logs/` directory and are not visible in the UI. Use this for verbose data dumps or tracing complex logic.

  ```python
  import logging
  file_logger = logging.getLogger(__name__)
  file_logger.debug(f"Full API response: {response.json()}")
  ```

---

## 5. State Management: Case Studies

A task that cannot remember things is of limited use. Here’s how to persist state, with examples from existing modules.

### Case Study 1: `counter` (Simple State)

The `counter` module needs to remember only one piece of information: the current count. The simplest way to do this is by writing back to its own configuration file.

**How it works:**

1. Read the `current_count` from `config['settings']`.
2. Increment the value.
3. Update the `config` dictionary in memory.
4. Use `json.dump()` to write the entire `config` dictionary back to the file at `config_path`.

**When to use this method**: Ideal for simple, infrequent state changes. Not suitable for large data or very frequent updates, as it involves rewriting the whole JSON file.

### Case Study 2: `screen_protector` (Complex/Volatile State)

The `screen_protector` needs to track the last mouse position. This state is volatile and not really a "setting". Storing it in the main config would be messy. Therefore, it uses a separate `state.json`.

**How it works:**

1. It constructs the path to its own `state.json` using the `config_path`: `os.path.join(os.path.dirname(config_path), "state.json")`.
2. It reads/writes only the last mouse position to this separate file.

**When to use this method**: Best for complex state data, frequently changing data, or data that is not a user-configurable setting.

---

## 6. Configuration (`_template.json`) In-Depth

- `name`: Default task name.
- `module_type`: **Crucial**. Must exactly match the module's directory name.
- `enabled`: If `true`, tasks created from this module will be active by default.
- `schedule`:
  - `trigger`: `interval` (runs every `seconds`) or `cron` (runs on a cron schedule defined in `expression`).
- `settings`: An object for your module's specific parameters. These appear in the "Configuration" tab in the UI and can be edited by the user.

---

## 7. Advanced Topics

### Dependency Management

If your module requires a third-party Python library (like `pyautogui` for `screen_protector`), you must:

1. Assume the user has the library installed.
2. In your module's `run` function, include a `try...except ImportError` block to provide a helpful error message if the library is missing.

    ```python
    try:
        import pyautogui
    except ImportError:
        log_emitter("ERROR: pyautogui is not installed. Please run 'pip install pyautogui' to use this module.")
        return # Stop execution
    ```

3. Document the dependency in a `README.md` file within your module's directory (optional but highly recommended).

### Effective Debugging

The `debug` flag passed into your `run` function is a powerful tool. When a user enables "Debug Mode" for a task, this flag becomes `True`, allowing you to activate more verbose logging.

**Best Practice:**
In your script, use an `if debug:` block at the beginning of your core logic to log the state of important variables and settings. The updated module template provides a clear example:

```python
# In modules/template/template_template.py
...
if debug:
    log_emitter(f"DEBUG: Debug mode is enabled for '{task_name}'.")
    # Get the custom debug message from settings
    debug_message = settings.get('debug_message', 'No debug message set.')
    log_emitter(f"DEBUG: Message from settings: {debug_message}")
    # Log the state of a key variable
    log_emitter(f"DEBUG: 'example_setting' is currently: '{example_setting}'")
    # Optionally, log the entire config to the file logger for deep inspection
    file_logger.debug(f"Full config for {task_name}: {config}")
...
```

By adding a `debug_message` to your module's `settings` in the JSON file, you can even allow users to customize the debug output for different task instances, which can be incredibly helpful.

**General Tips:**

- **Use `file_logger` for noisy logs**: If you need to dump large amounts of data (like a full API response), use `file_logger.debug()`. This keeps the UI clean but saves the data in `logs/` for your review.
- **Test changes iteratively**: You can directly edit the `main.py` inside a task's folder (e.g., `tasks/My_First_Task/main.py`) and restart the task to quickly test changes. Once you are satisfied, remember to copy the code back to your module template in `modules/`.

---

## 8. Packaging and Distribution

To share your module:

1. Ensure your module's directory is clean and contains only the necessary files.
2. Create a `.zip` archive of the directory.
3. Other users can import this `.zip` file via **Settings -> Import Module**.
