[English](./user_manual.md) | [简体中文](./user_manual.zh-CN.md)

---

# T4T Task Management Platform - User Manual (V2)

## 1. Welcome to T4T

Welcome to T4T V2, a powerful and flexible automation tool. Whether you want to execute repetitive tasks on a schedule or build complex event-driven workflows, T4T has you covered. This manual will guide you through the software's features.

## 2. Main Interface Overview

![T4T Main Interface](https://your-image-host.com/main-window.png) *(Please replace with an actual screenshot of the interface)*

*   **Task List (Left Panel)**: Centrally displays all your tasks. The status of each task (Running, Paused, Listening, or Stopped) is visible at a glance.
*   **Detail Area (Right Panel)**: A tabbed area for configuring new tasks, modifying existing ones, viewing real-time logs, and adjusting application settings.
*   **Toolbar (Top)**: Provides shortcuts for common actions like "Add Task," "Start All," "Pause All," etc.
*   **Status Bar (Bottom)**: Shows a system summary, including the total number of tasks, CPU/memory usage, and the crucial **Message Bus connection status**.

---

## 3. Core Features Explained

### 3.1. Managing Your Tasks

*   **Add New Task**: Click the `+` (Add) icon on the toolbar to open the "New Task" configuration page on the right.
*   **Control Tasks**: Select one or more tasks and use the "Start," "Pause," and "Stop" buttons on the toolbar to control their lifecycle.
*   **Delete Task**: Right-click a task in the list and select "Delete."

### 3.2. Understanding Task Triggers

When creating or editing a task, the "Trigger Type" is the most critical setting. It determines *when* the task will be executed.

| Trigger Type | Use Case Description |
| :--- | :--- |
| `schedule` | **Scheduled Execution**: For tasks that need to run on a fixed schedule. For example: every 5 minutes, every weekday at 9 AM, or at 3 PM on January 1, 2025. |
| `event` | **Event-Driven**: For tasks that respond to specific events occurring in the system. The task "listens" to a message topic and only executes when a message arrives on that topic. |

### 3.3. Configuring a Task

On the "New Task" or "Edit Task" page, you will see the following key configuration areas:

*   **Basic Information**: Set the task's name and description.
*   **Trigger Configuration**: This section displays different options based on the trigger type you select.
    *   If you choose `schedule`, you will need to configure parameters like `cron`, `interval`, or `date`.
    *   If you choose `event`, you will need to specify the `topic` the task should subscribe to.
*   **Input Parameters (`inputs`)**: This defines the parameters the task needs to run. For event-driven tasks, these parameters typically come from the content of the event it is listening to.

### 3.4. Real-Time Monitoring

*   **Task Logs (`Output` Tab)**: The output of each task (including info, warnings, and errors) is displayed here in real-time. This is the most important window for debugging and monitoring task execution.
*   **Task State (`State` Tab)**: Shows the detailed status of a task, for example:
    *   For scheduled tasks, it will show the "Next Run Time."
    *   For event tasks, it will show the "Topic" it is listening to and its current status (e.g., "Listening").

---

## 4. Event-Driven Architecture and the Message Bus

The core of T4T V2 is the **Message Bus** (usually an MQTT server), which allows tasks to communicate with each other and with the outside world.

*   **How It Works**: Imagine a post office system. A task (the publisher) can send a letter (a message) to a specific address (a topic). Any other task or tasks (the subscribers) interested in this address can "subscribe" to it and will receive the letter instantly upon its arrival.
*   **Connection Status**: Be sure to pay attention to the status bar in the bottom-right corner of the main interface. A dedicated icon will show whether the application is currently connected to the message bus. **If the connection is lost, all event-driven tasks will be unable to receive events.**

## 5. Application Settings

Click the "Settings" icon (usually a gear) on the main toolbar to open the global settings page.

*   **Theme & Language**: Personalize your application's appearance and display language here.
*   **Message Bus Configuration**: This is where you configure how T4T connects to your MQTT server. You need to correctly fill in the server address, port, username, and password (if required).

## 6. Frequently Asked Questions (FAQ)

*   **Q: My scheduled task isn't running on time.**
    *   **A:** Please check: 1) Is the task in the "Started" state? 2) In the "State" tab, is the "Next Run Time" correct? 3) Check the main application log or the task's own log for any error messages.

*   **Q: My event-driven task is not responding.**
    *   **A:** Please check: 1) Is the task in the "Listening" state? 2) Does the message bus icon in the status bar show as "Connected"? 3) Confirm that the source publishing the message (another task or an external program) is actually publishing to the exact same topic that the task is listening to.

*   **Q: How can I make two tasks work together?**
    *   **A:** This is the beauty of event-driven design! Have Task A, upon completion, publish a message with its result to a topic (e.g., `tasks/A/result`). Then, create an event-driven Task B and have it subscribe to the `tasks/A/result` topic. This way, whenever A finishes, B will be automatically triggered and receive A's results.
