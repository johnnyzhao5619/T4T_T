# T4T Module Development Guide (v2.0)

## 1. Introduction

Welcome to the v2.0 development guide for the T4T platform. This version introduces a paradigm shift from simple scheduled tasks to a powerful, **event-driven architecture**. This guide covers the new concepts, APIs, and best practices for building modules in this new ecosystem.

Modules are now capable of reacting to external events, communicating with each other, and handling complex data flows.

---

## 2. V2 Architecture: Key Concepts

### 2.1. The Message Bus
The core of V2 is the **Message Bus**, a central communication channel (powered by MQTT by default) that allows tasks to be completely decoupled.
- **Publish/Subscribe:** Tasks can publish messages to a "topic" or subscribe to a topic to listen for messages.
- **Inter-Task Communication:** Task A can publish its result to `results/task_a`, and Task B can subscribe to that topic to use the result, without either task knowing about the other.

### 2.2. New Trigger Types
- **`interval`, `cron`, `date`:** These are traditional time-based triggers managed by the internal scheduler.
- **`event`:** This is the most powerful new trigger. An event-driven task does not run on a schedule. Instead, it **subscribes to a message bus topic** and executes its `run` function only when a message arrives on that topic.

### 2.3. Concurrency Model
**Crucial Change:** To prevent long-running tasks from blocking the application, all task executions (regardless of trigger type) are run in a **background thread pool**. This ensures that the UI and message bus client remain responsive at all times.

---

## 3. The V2 `run` Function

The function signature has been completely redesigned for dependency injection and clarity.

`def run(context, **inputs):`

- `context` (`TaskContext` object): This is your gateway to all core services. It's an object injected by the `TaskManager` that holds:
  - `context.logger`: The function to send logs to the UI.
  - `context.message_bus`: The instance of the message bus client for publishing messages.
  - `context.config`: The full configuration dictionary for the task instance.
  - `context.config_path`: The absolute path to the task's `config.json`.

- `**inputs` (dict): A dictionary containing the data that triggered the task.
  - For time-based triggers, this will be empty.
  - For an `event` trigger, this dictionary is the **JSON payload of the incoming message**, automatically parsed for you.

---

## 4. The V2 Configuration (`_template.json`)

The `config.json` structure has been standardized to support the new features.

```json
{
  "name": "V2 Module Template",
  "module_type": "template_v2",
  "enabled": true,
  "trigger": {
    "type": "event",
    "config": {
      "topic": "sensor/temperature/raw"
    }
  },
  "inputs": [
    { "name": "temperature", "type": "float", "description": "The temperature reading." },
    { "name": "humidity", "type": "float", "description": "The humidity reading." }
  ],
  "outputs": [
    { "name": "status_report", "type": "json", "target": { "type": "mqtt", "topic": "analyzer/temperature/report" } }
  ],
  "settings": {
    "temp_threshold": 30.0
  }
}
```

- **`trigger` (object):** This is now the central point for defining how a task starts.
  - `type`: Can be `interval`, `cron`, `date`, or `event`.
  - `config`: A sub-object containing the parameters for the chosen trigger type (e.g., `seconds` for `interval`, `topic` for `event`).

- **`inputs` & `outputs` (arrays):** These are **metadata for the UI and for developers**. They describe the data contract of your module, making it easier to understand and integrate. They do not enforce runtime checks.

- **`settings` (object):** This remains the place for user-configurable parameters for your module's logic.

---

## 5. Building a V2 Module: A Practical Example

Let's build a module that listens for temperature readings and publishes an alert if it's too hot.

**1. Configure `_template.json`:**
   - Set `trigger.type` to `event`.
   - Set `trigger.config.topic` to `sensor/temperature/raw`.
   - Define `inputs` for `temperature` and `humidity`.
   - Define an `output` that publishes to `analyzer/temperature/report`.
   - Add a `temp_threshold` to `settings`.

**2. Write the Script (`_template.py`):**

```python
import json

def run(context, **inputs):
    """
    Analyzes temperature readings and publishes an alert if a threshold is exceeded.
    """
    logger = context.logger
    bus = context.message_bus
    settings = context.config.get('settings', {})
    
    logger("INFO: Received new sensor data.")

    # Safely get inputs from the message payload
    temp = inputs.get('temperature')
    humidity = inputs.get('humidity')
    
    if temp is None:
        logger("ERROR: 'temperature' not found in the input data.")
        return

    # Get the threshold from user settings
    threshold = settings.get('temp_threshold', 35.0)
    
    report = {
        "checked_temp": temp,
        "checked_humidity": humidity,
        "threshold": threshold
    }

    # Core logic
    if temp > threshold:
        report["status"] = "ALERT"
        report["message"] = f"High temperature detected: {temp}°C"
        logger(f"WARNING: {report['message']}")
    else:
        report["status"] = "NORMAL"
        report["message"] = f"Temperature is normal: {temp}°C"
        logger(f"INFO: {report['message']}")

    # Publish the output report to the target topic
    try:
        output_topic = context.config['outputs'][0]['target']['topic']
        bus.publish(output_topic, json.dumps(report))
        logger(f"INFO: Report published to {output_topic}.")
    except (IndexError, KeyError) as e:
        logger(f"ERROR: Could not determine output topic from config.json: {e}")

```

### Key Practices Illustrated:
- **Use the `context` object:** All services are accessed via `context`.
- **Safely access `inputs`:** Always use `.get()` to avoid `KeyError` if the incoming message is malformed.
- **Separate `settings` from `inputs`:** `settings` are for user configuration; `inputs` are for data that triggers the task.
- **Publish structured data:** Always publish JSON strings for easy consumption by other tasks.

---

## 6. State Management in V2

The principles of state management remain the same, but the implementation is cleaner using the `context` object.

- **For simple state:** Write back to the task's own `config.json`.
  - Get the path: `context.config_path`.
  - Read the config: `context.config`.
  - Modify the dictionary in memory.
  - Write the whole dictionary back to `context.config_path`.

- **For complex state:** Use a separate `state.json` file.
  - Get the directory: `os.path.dirname(context.config_path)`.
  - Construct the path to `state.json`.
  - Read/write to the separate state file.

---

## 7. Dependency Management

This remains unchanged. If your module needs a third-party library, you must use a `try...except ImportError` block and provide a clear error message to the user via `context.logger()`.

```python
try:
    import numpy
except ImportError:
    context.logger("ERROR: numpy is not installed. Please run 'pip install numpy' to use this module.")
    return
```
