[English](./README.md) | [简体中文](./README.zh-CN.md) | [Français](./README.fr.md)

---

# T4T - Task For Task

**T4T is a highly extensible desktop automation platform built with Python and PyQt5. It is designed to be a flexible, event-driven hub for task management and execution.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## ✨ Core Features

*   **Dual-Mode Triggers**: Supports both traditional **scheduled** tasks (Cron, Interval) and powerful **event-driven** tasks.
*   **Pluggable Module System**: Create new functional modules with a simple `manifest.yaml` and a Python script, enabling true "hot-plugging".
*   **Message Bus Integration**: A built-in MQTT client allows for decoupled communication between tasks and with external systems (e.g., IoT devices, Web APIs).
*   **Concurrent Execution**: Uses a `ThreadPoolExecutor` to run all tasks asynchronously, ensuring a smooth UI and non-blocking task execution.
*   **Rich User Interface**: Provides features for task management, real-time logging, status monitoring, multi-language support, and theme switching.
*   **Context-Aware Logging**: Logs from each task are automatically associated with the task instance for clear and easy debugging.

## 📂 Project Structure
```
/
├─── core/              # Core application logic (TaskManager, ModuleManager, etc.)
├─── docs/              # Documentation files
├─── i18n/              # Internationalization files (en.json, zh-CN.json, fr.json)
├─── modules/           # Reusable module templates (manifest.yaml, scripts)
├─── tasks/             # User-configured task instances
├─── utils/             # Utility classes (Logger, ThemeManager, MessageBus)
├─── view/              # PyQt5 UI components and windows
├─── main.py            # Main application entry point
├─── requirements.txt   # Python dependencies
└─── README.md          # This file
```

## 🏛️ Project Architecture

The project follows a layered architecture, clearly separating presentation, business logic, and services.

*   **View (`view/`)**: The entire user interface, built with PyQt5. It is responsible for displaying data and forwarding user actions to the core layer.
*   **Core (`core/`)**: The heart of the application. It contains the main business logic:
    *   `ModuleManager`: Discovers and manages all available modules (`modules/`).
    *   `TaskManager`: Manages the lifecycle of all task instances (`tasks/`), including their creation, execution, and state.
    *   `Scheduler`: A facade for `APScheduler` that handles all time-based triggers.
    *   `StateManager`: Manages the state of the application and tasks.
*   **Utils (`utils/`)**: A collection of utility classes and functions used across the application, such as logging, i18n, theme management, and the system-wide message bus.
*   **Modules & Tasks**:
    *   `modules/`: Contains the reusable “templates” for tasks.
    *   `tasks/`: Contains the configured instances of modules, each with its own `config.yaml`.

## 🚀 Tech Stack

*   **Backend**: Python 3
*   **UI**: PyQt5
*   **Desktop Automation**: PyAutoGUI
*   **Core Architecture**: Event-Driven, Publish/Subscribe
*   **Concurrency**: `ThreadPoolExecutor`
*   **Message Queue**: Paho-MQTT
*   **Scheduling**: APScheduler (for `schedule` type tasks)

## 📖 Documentation

*   **[User Manual](./docs/user_manual.md)**: A guide for end-users on how to operate the software.
*   **[Development Guide](./docs/development_guide.md)**: A detailed guide for developers on how to create new V2 modules, explaining the core API and architecture.

## Quick Start

1.  **Clone the repository**
    ```bash
    git clone github.com/johnnyzhao5619/T4T_T.git
    cd T4T
    ```

2.  **Install dependencies**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the application**
    ```bash
    python main.py
    ```

## Contributing

Contributions of any kind are welcome! Whether it's bug reports, feature suggestions, or pull requests.

1.  Fork the Project
2.  Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the Branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull Request

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
