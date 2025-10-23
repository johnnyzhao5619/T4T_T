[English](./README.md) | [简体中文](./README.zh-CN.md) | [Français](./README.fr.md)

---

# T4T - Task For Task

**T4T is a highly extensible desktop automation platform built with Python and PyQt5. It acts as a flexible, event-driven hub for task management and execution.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## ✨ Core Features

| Domain | Highlight |
| --- | --- |
| Task Automation | **Dual trigger modes**: Run cron/interval jobs alongside event-driven tasks to cover both recurring and real-time scenarios. |
| Module Extensibility | **Hot-swappable modules**: Publish new modules with `manifest.yaml` + a `run` function—configuration only, no boilerplate rewrites. |
| Message Orchestration | **Built-in MQTT message bus**: Offers publish/subscribe capability with hop-count protection for safe automation chains. |
| Parallel Execution | **Thread-pool scheduling**: All tasks run asynchronously, keeping the UI responsive while workloads scale. |
| Observability | **Context-aware logging & runtime telemetry**: Logs are automatically tagged per task and surfaced through the status bar. |
| User Experience | **Internationalization & theming**: Real-time language/theme switching and live log panels keep onboarding friction low. |

## 🧭 Release History

> Migration tips, compatibility notes, and full change details are available in the [Change Log](./docs/CHANGELOG.md).

* **v1.0.0 (2024-06-01)** — First public release:
  * Delivered the modular task architecture with hot-swappable modules, contextual logging, and theming.
  * Added a built-in MQTT message bus and service orchestration framework, supporting both embedded and external brokers.
  * Introduced thread-pool scheduling, hop-count protection, and UI observability widgets for reliable runtime behavior.

## 📂 Project Structure
```text
/
├── core/              # Core application logic (TaskManager, ModuleManager, etc.)
├── docs/              # Documentation files
├── i18n/              # Internationalization files (en.json, zh-CN.json, fr.json)
├── modules/           # Reusable module templates (manifest.yaml, scripts)
├── tasks/             # User-configured task instances
├── utils/             # Utility classes (Logger, ThemeManager, MessageBus)
├── view/              # PyQt5 UI components and windows
├── main.py            # Main application entry point
├── requirements.txt   # Python dependencies
└── README.md          # This file
```

## 🏛️ Project Architecture

The project follows a layered architecture, clearly separating presentation, business logic, and services.

* **View (`view/`)**: PyQt5 UI components responsible for displaying data and forwarding user interactions.
* **Core (`core/`)**: Application heart containing business logic:
  * `ModuleManager`: Discovers and manages all available modules (`modules/`).
  * `TaskManager`: Handles lifecycle management for task instances (`tasks/`).
  * `Scheduler`: Facade around `APScheduler` for time-based triggers.
  * `StateManager`: Tracks application and task state.
* **Utils (`utils/`)**: Logging, theming, internationalization, and message bus utilities shared across the app.
* **Modules & Tasks**:
  * `modules/`: Reusable templates.
  * `tasks/`: Configured task instances with their own `config.yaml`.

## 🛰️ Message Bus & Service Management

T4T's event-driven capabilities rely on coordinated services:

1. **ServiceManager (`core/service_manager.py`)**
   * Declaratively registers background services (embedded MQTT broker, data collectors, etc.).
   * Exposes unified `start/stop/restart` APIs and emits `global_signals.service_state_changed` so UI, tasks, and monitoring tools stay informed.
2. **MessageBusManager (`utils/message_bus.py`)**
   * Supports both external brokers and the embedded broker, handling connection, reconnection, and fault reporting.
   * Couples with the ServiceManager: establishes MQTT sessions only after the broker service enters the `RUNNING` state.
3. **Event Safety Nets**
   * `__hops` counters in message payloads limit propagation depth to prevent event loops.
   * Global thresholds in `config/config.ini`, combined with contextual logs, make anomaly triage and alerting straightforward.

Together, these components keep background services stable and message flows transparent, ensuring reliable event-driven automation on the desktop.

## 🚀 Tech Stack

* **Backend**: Python 3
* **UI**: PyQt5
* **Desktop Automation**: PyAutoGUI
* **Core Architecture**: Event-driven, Publish/Subscribe
* **Concurrency**: `ThreadPoolExecutor`
* **Message Queue**: Paho-MQTT
* **Scheduling**: APScheduler (for `schedule` tasks)

## 📖 Documentation

* **[User Manual](./docs/user_manual.md)**: End-user guide to the application.
* **[Development Guide](./docs/development_guide.md)**: Tutorial for building v1.0 modules and understanding the architecture.
* **[Change Log](./docs/CHANGELOG.md)**: Release history and feature evolution.

## 📦 Packaging & Runtime Requirements

### Runtime Environment

* **Operating System**: Windows 10/11, macOS 12+, or modern Linux desktop distributions with a graphical environment.
* **Python**: Python 3.10 or newer. Keep `pip`, `setuptools`, and `wheel` up to date inside the virtual environment to avoid missing assets during builds.
* **Dependencies**:
  * Qt platform plugins are required for GUI execution; some Linux distributions need packages such as `libxcb` and `qt5-default` installed system-wide.
  * The message bus defaults to an external MQTT broker; when enabling the embedded `amqtt` service, ensure the port is free and loopback access is permitted.
  * Optional add-ons: screenshot/OCR modules may require packages like `pillow` or `opencv-python`.

### Packaging Guide

1. Create an isolated environment and install build dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install --upgrade pip setuptools wheel pyinstaller
   ```
2. From the project root run:
   ```bash
   pyinstaller main.py \
     --name T4T \
     --noconfirm \
     --windowed \
     --add-data "modules:modules" \
     --add-data "themes:themes" \
     --add-data "i18n:i18n" \
     --add-data "config:config"
   ```
3. Distribute `dist/T4T` (or the generated `.app`/`.exe`) along with the `config/`, `tasks/`, `logs/` directories and any custom module resources.
4. When enabling the embedded MQTT broker, document in deployment scripts or runbooks:
   * Port availability checks and firewall rules.
   * Whether the service should start with the OS or be launched manually before use.

> 💡 **Tip**: Run a full end-to-end smoke test on the target platform (message bus connectivity, theme switching, module execution) before delivery to minimize rework.

## 🚀 Quick Start

1. **Clone the repository**
   ```bash
   git clone github.com/johnnyzhao5619/T4T_T.git
   cd T4T_T
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python main.py
   ```

## 🤝 Contributing

Contributions of any kind are welcome! Whether it's bug reports, feature suggestions, or pull requests.

1. Fork the project
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a pull request

---
