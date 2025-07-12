# T4T Task Management Platform - User Manual (v2.0)

## 1. Introduction

Welcome to T4T v2.0, a powerful automation platform that has evolved beyond simple scheduling. T4T can now run tasks based on schedules, at specific times, or in response to real-time events. This guide will walk you through all the features.

## 2. Interface Overview

- **Task List (Left Panel):** Displays all your tasks. You can see their status at a glance, including whether they are running, paused, or listening for an event.
- **Detail Area (Right Panel):** A tabbed interface to configure tasks, view logs, and change application settings.
- **Toolbar (Top):** Quick access to add, start, pause, and stop tasks.
- **Status Bar (Bottom):** Shows a summary of tasks, system resource usage, and the **Message Bus connection status**.

## 3. Core Features

### 3.1. Task Management

- **Add Task:** Click the `+` icon to open the "New Task" tab.
- **Start/Pause/Stop Task:** Use the toolbar buttons to control tasks.
  - For scheduled tasks, "Start" means adding them to the schedule.
  - For **event-driven tasks**, "Start" means they begin listening for their specific event.
- **Delete Task:** Right-click a task and select "Delete".

### 3.2. Task Configuration

When creating or editing a task, you will now see more powerful options.

- **Trigger Type:** This is the most important new setting. It defines *how* a task is activated.
  - **Interval:** Runs repeatedly every X seconds/minutes/hours.
  - **Cron:** Runs on a complex schedule (e.g., "every weekday at 9 AM").
  - **Date:** Runs only once at a specific date and time you choose.
  - **Event:** Does not run on a schedule. It listens for a message on a specific **Message Bus topic** and runs only when a message arrives.

- **Config Tab:** A user-friendly editor for the task's parameters. The options here will change based on the **Trigger Type** you select.
- **Output Tab:** Displays real-time logs from the task.
- **State Tab:** Shows the task's current status, next scheduled run time, or the event topic it is listening to.

### 3.3. The Message Bus

T4T v2.0 includes a Message Bus, which allows tasks to communicate with each other and react to external systems.
- **Connection Status:** Look for the icon in the bottom status bar to see if the application is successfully connected to the message broker (e.g., MQTT).
- **Event-Driven Tasks:** This feature allows you to create powerful workflows. For example, Task A can monitor a sensor and publish a reading to a topic, and Task B can be an event-driven task that listens to that topic to process the reading.

### 3.4. Settings

Click the "Settings" (cogs) icon to open the Settings tab.
- **Theme & Language:** Customize the look and feel.
- **Message Bus Configuration:** Here you can configure the connection details for your MQTT broker (hostname, port, etc.). This is required for event-driven tasks to work.

## 4. Troubleshooting

- **Task not running:**
  - For scheduled tasks, check its "Next Run Time" in the State tab.
  - For event-driven tasks, ensure it is started (it should show a "listening" status) and that the Message Bus is connected (check the status bar icon).
- **Message Bus not connecting:** Double-check the connection details in the Settings tab. Ensure the MQTT broker is running and accessible from your computer.
- **Interface is not translated:** Make sure the corresponding language file (e.g., `zh-CN.json`) exists in the `i18n` directory.
