[English](./README.md) | [简体中文](./README.zh-CN.md) | [Français](./README.fr.md)

---

# T4T - Task For Task

**T4T is a highly extensible desktop automation platform built with Python and PyQt5. It is designed to be a flexible, event-driven hub for task management and execution.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## ✨ 核心特性清单

| 领域 | 能力亮点 |
| --- | --- |
| 任务自动化 | **双触发模式**：支持 Cron/Interval 等定时任务与事件驱动任务并行使用，满足周期性与实时性的双重需求。 |
| 模块扩展 | **模块热插拔**：通过 `manifest.yaml` + `run` 函数即可发布新模块，配置即生效，避免重复开发。 |
| 消息联动 | **内置 MQTT 消息总线**：提供发布/订阅能力与循环跳数防护，轻松联动物联网设备或其他系统。 |
| 并发执行 | **线程池调度**：所有任务异步执行，保证 UI 流畅与后台处理互不阻塞。 |
| 可观测性 | **上下文日志 & 运行态监控**：日志自动归属任务实例，配合状态栏实时呈现消息总线与系统资源。 |
| 体验友好 | **多语言 & 主题切换**：支持多语言界面、主题自定义与实时日志面板，降低学习成本。 |

## 🧭 版本历史

* **v1.0.0 (2024-06-01)**：首个公开版本，提供模块化任务体系、MQTT 消息总线集成、可视化调度器与基础服务管理。详见 [更新日志](./docs/CHANGELOG.md)。

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

## 🛰️ 消息总线与服务管理

T4T 通过 **ServiceManager** 与 **MessageBusManager** 协同管理后台服务和通信链路：

* **ServiceManager (`core/service_manager.py`)**：统一注册、启动、停止后台服务（如内置 MQTT Broker），并向全局信号发出状态变更，保证服务生命周期的可控性。
* **MessageBusManager (`utils/message_bus.py`)**：依据配置自动连接外部或内置 MQTT，总线状态会同步到 UI 状态栏；若启用内置 Broker，会等待 ServiceManager 报告 `RUNNING` 才发起连接，避免重复重启或连接失败。
* **事件安全机制**：消息负载中的 `__hops` 字段可限制事件链路跳数，防止任务之间的循环触发。

借助这一组合，任务可以在后台服务可靠运行的前提下进行事件驱动联动，而不会影响桌面端的交互体验。

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
*   **[Change Log](./docs/CHANGELOG.md)**: 历史版本与功能演进记录。

## 📦 打包与运行环境要求

### 运行环境

* **操作系统**：Windows 10/11、macOS 12+、常见 Linux 桌面发行版（需带有图形环境）。
* **Python**：推荐 Python 3.10 或更高版本，确保与 PyQt5 及 `threading`/`asyncio` 相关依赖兼容。
* **依赖组件**：
  * GUI 运行需要系统安装 Qt 平台运行库（PyQt5 会自动打包，但在部分 Linux 发行版可能需要额外的 Qt 插件包）。
  * 消息总线默认依赖外部 MQTT Broker，可选使用内置 `amqtt` 服务。

### 打包指引

1. 安装额外构建依赖：`pip install pyinstaller`。
2. 在项目根目录执行：
   ```bash
   pyinstaller main.py \
     --name T4T \
     --noconfirm \
     --windowed \
     --add-data "modules:modules" \
     --add-data "themes:themes" \
     --add-data "i18n:i18n"
   ```
3. 将 `dist/T4T`（或 `.app`/`.exe`）连同 `config/`、`tasks/` 等运行时目录打包分发。
4. 若计划内置 MQTT Broker，需在 `config/config.ini` 中开启 `embedded_broker.enabled=true`，并在安装脚本中配置开机自启或运行前检查端口占用。

> 💡 **提示**：建议在干净的虚拟环境中执行上述命令，并在目标平台上进行一次完整运行测试，以验证消息总线连接、界面字体以及多语言资源是否正常加载。

## Quick Start

1.  **Clone the repository**
    ```bash
    git clone github.com/johnnyzhao5619/T4T_T.git
    cd T4T_T
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
