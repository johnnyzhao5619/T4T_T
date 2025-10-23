[English](./development_guide.md) | [简体中文](./development_guide.zh-CN.md)

---

# T4T Developer Guide (V2)

Welcome to the world of T4T V2 module development! This document will guide you through the new event-driven architecture, core concepts, and how to build a fully functional V2 module.

## 1. V2 Module Structure Overview

A V2 module consists of two core files that together define its behavior and metadata.

*   **`manifest.yaml`**: This is the module's "ID card." It is a declarative configuration file used to define the module's name, trigger mechanism, input parameters, and other metadata. The system parses this file to understand how and when to execute your task.
*   **Task Script (`__init__.py` or other specified script)**: This is the module's "brain," containing the actual business logic. Its core is a function named `run`, which the system calls when the trigger condition is met.

---

## 2. Writing the Task Script (The `run` function)

The entry point for a V2 module is a `run` function with a standard signature. This function's design follows the principle of "dependency injection," making testing and code reuse simpler.

```python
def run(context, inputs):
    """
    A standard V2 task function.

    :param context: A context object injected by the system, providing access to core services like logging and the message bus.
    :param inputs: A dictionary containing the input data required by the task.
    """
    # Your code logic goes here
    pass
```

### 2.1. The Context Object (`context`)

The `context` object is the bridge for your task to interact with the T4T system. It is an instance created and passed by the Task Manager at runtime, containing all the environmental information and services needed to execute the task.

**`context` Object Attributes:**

| Attribute   | Type       | Description                                                                 |
| :---------- | :--------- | :-------------------------------------------------------------------------- |
| `task_name` | `str`      | The name of the currently executing task instance.                          |
| `logger`    | `logging.Logger` | Standard Python logger instance for task-scoped logs; use `.info()`, `.warning()`, `.error()`, `.debug()` as needed. |

**Code Example: Using the Contextual Logger**

Using `context.logger` instead of `print()` is a best practice because it associates logs with a specific task, which is invaluable for debugging.

```python
def run(context, inputs):
    context.logger.info(f"Task '{context.task_name}' has started.")

    try:
        # ... core logic ...
        result = "Operation successful"
        context.logger.info(f"Processing complete: {result}")
    except Exception as e:
        context.logger.error(f"Task execution failed: {e}")
```

### 2.2. Input Data (`inputs`)

The `inputs` parameter is a dictionary containing all the data needed for the task's execution. The source of this data is determined by the `trigger` and `inputs` configurations in `manifest.yaml`.

*   **For `event` triggers**: The key-value pairs in the `inputs` dictionary typically come from the `payload` of the triggering event (e.g., the content of an MQTT message).
*   **For `schedule` triggers**: The `inputs` dictionary is usually empty, as these tasks are not driven by external data.

---

## 3. The Manifest File (`manifest.yaml`)

`manifest.yaml` is the core of a V2 module, defining its behavior in a clear, human-readable way.

### 3.1. The Trigger (`trigger`)

The `trigger` field defines the condition that starts the task. T4T V2 supports two main types of triggers.

#### a) Schedule Trigger (`schedule`)

Use this trigger when you want a task to run on a fixed schedule (e.g., every hour, daily at midnight). It is powered by `APScheduler` under the hood.

**Complete Configuration Example:**

```yaml
# manifest.yaml
name: "Daily Report Task"
module_type: "reporting_v2"
version: "1.0"

trigger:
  type: schedule
  config:
    type: cron      # cron, interval, or date
    hour: 0         # Executes daily at 00:00
    minute: 0
```

#### b) Event Trigger (`event`)

Use this trigger when you want a task to respond to a specific event in the system (e.g., the completion of another task, the receipt of an MQTT message). This is key to building responsive, decoupled systems.

**Complete Configuration Example:**

```yaml
# manifest.yaml
name: "Temperature Sensor Processor"
module_type: "sensor_handler_v2"
version: "1.0"

trigger:
  type: event
  config:
    topic: "sensors/temperature/reading" # Subscribe to an MQTT topic
    max_hops: 5 # Optional safeguard against circular event chains
```

> 💡 **Safety Net**: `max_hops` limits how many times an event payload can be forwarded between tasks. If the payload contains `__hops` greater than this threshold, the event is ignored and an error is logged. If you omit `max_hops`, the Task Manager falls back to the global default defined in `config/config.ini` under `[TaskDefaults] event_max_hops` (default: `5`).

### 3.2. Input Mapping and Validation (`inputs`)

The `inputs` field is a crucial part of `manifest.yaml`. It serves a dual role:

1.  **Data Mapping**: It declares which input parameters the task's `run` function expects. For event triggers, the system will attempt to extract these fields from the event's `payload`.
2.  **Upfront Validation**: It is the first line of defense to protect your task from invalid or missing data.

**Highlight: `required: true`**

When an input field is marked as `required: true`, the Task Manager will check for its existence in the input data **before** calling the `run` function. If the data is missing, the task will not be executed, and an error will be logged. This can significantly simplify the error-handling logic within your `run` function.

> ℹ️ **Tip**: The `inputs` section can be declared either as a list (as shown below) or as a dictionary keyed by the field name. Optional fields may also define a `default` value—if the payload omits that field, the Task Manager automatically injects the default into the dictionary passed to your task.

**Configuration Example:**

```yaml
# manifest.yaml
name: "User Registration Handler"
# ... other configs ...

trigger:
  type: event
  config:
    topic: "users/register"

inputs:
  - name: username
    type: string
    description: "The user's unique identifier."
    required: true  # Task will not run if username is missing from the MQTT message

  - name: email
    type: string
    description: "The user's email address."
    required: true

  - name: referral_code
    type: string
    description: "Referral code (optional)."
    required: false # This field is optional
```

### 3.3. Declaring Additional Assets (`assets.copy_files`)

Some modules depend on extra files (for example credentials, templates, or binary resources) besides the default `manifest.yaml` and task script. Declare these assets in the manifest so that the Task Manager can copy them from the module directory to each new task instance.

Use the `assets.copy_files` list to describe the relative paths that should be copied. Paths must stay within the module directory (no absolute paths or `..` segments) and can point to files or directories. When a directory is listed, its entire structure is duplicated. The Task Manager preserves the relative layout when copying the resources.

```yaml
assets:
  copy_files:
    - resources/credentials.json   # Copies a single file
    - templates/email/             # Copies an entire directory
```

> ℹ️ **Tip**: If the module does not require additional assets, set `assets.copy_files` to an empty list (or omit the section entirely) to keep the manifest clean.

---

## 4. Core Concepts Explained

### 4.1. Concurrency Model

T4T V2 uses a `ThreadPoolExecutor` to manage a pool of worker threads. All tasks (whether triggered by `schedule` or `event`) are submitted to this pool for asynchronous execution.

*   **Difference from the old model**: In the old `APScheduler` model, a long-running task could block the scheduler thread. The new thread pool model ensures that each task runs in a separate thread, preventing tasks from interfering with each other and ensuring the main application UI remains responsive at all times.

### 4.2. Event-Driven Architecture & The Message Bus

At the heart of the system is a lightweight **Message Bus** (implemented with MQTT by default). It allows different modules and tasks to communicate in a "publish/subscribe" pattern without being directly dependent on each other.

*   **Role**: The message bus is the cornerstone of the system's event-driven architecture. One task can publish a message to a topic (e.g., `task/A/completed`), and any number of other tasks can subscribe to that topic to be triggered when the message arrives. This pattern dramatically increases the system's flexibility and scalability.

To keep the embedded MQTT broker and the client connection in sync, `MessageBusManager.connect()` inspects the `ServiceState` exposed by the `ServiceManager`. When the configuration requests the embedded broker, the manager starts `mqtt_broker` (if needed) and waits for a `global_signals.service_state_changed` notification that the service is `RUNNING`. If the broker does not reach that state within the default timeout, a clear error is logged and the MQTT client connection is skipped to avoid redundant restarts or indefinite blocking.

---

## 5. A Complete V2 Module Example

Let's bring all these concepts together in a complete, event-driven module. This module will listen to an MQTT topic, validate the incoming temperature data, and log messages at different levels based on the temperature value.

**Directory Structure:**

```
modules/
└── smart_thermostat/
    ├── manifest.yaml
    └── smart_thermostat_template.py
```

**`manifest.yaml`:**

```yaml
name: "Smart Thermostat"
module_type: "smart_thermostat_v2"
version: "1.1"
description: "Listens for temperature readings and logs a warning if it's too high."

trigger:
  type: event
  config:
    topic: "home/living_room/temperature"

inputs:
  - name: current_temp
    type: float
    description: "The current temperature reading in Celsius."
    required: true

  - name: device_id
    type: string
    description: "The unique ID of the sensor."
    required: false
```

**`smart_thermostat_template.py`:**

```python
def run(context, inputs):
    """
    Processes temperature sensor data.
    """
    task_name = context.task_name
    logger = context.logger

    # Because `required: true` is set in manifest.yaml,
    # we can safely access 'current_temp' directly here.
    temperature = inputs['current_temp']
    device_id = inputs.get('device_id', 'Unknown Device') # Use .get() for optional fields

    logger.info(f"[{task_name}] Received temperature data from '{device_id}': {temperature}°C")

    if temperature > 30.0:
        logger.warning(f"[{task_name}] High temperature alert! Temperature reached {temperature}°C.")
    elif temperature < 5.0:
        logger.warning(f"[{task_name}] Low temperature alert! Temperature dropped to {temperature}°C.")
    else:
        logger.info(f"[{task_name}] Temperature '{temperature}°C' is within the normal range.")

```

This example demonstrates how to leverage the features of the V2 architecture—a declarative `manifest.yaml`, robust input validation, and context-aware logging—to create a module that is concise, reliable, and easy to maintain.
