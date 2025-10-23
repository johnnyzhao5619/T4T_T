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

> 各版本的迁移指南、兼容性提示与详细改动请参阅 [更新日志](./docs/CHANGELOG.md)。

* **v1.0.0 (2024-06-01)** — 首个公开版本：
  * 构建 V2 模块/任务体系，支持热插拔模块、上下文日志与多语言主题。
  * 引入内置 MQTT 消息总线与服务管理框架，可在外部 Broker 与嵌入式 Broker 间无缝切换。
  * 新增线程池调度、事件跳数防护与 UI 观测组件，保障运行时可靠性与可调试性。

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

T4T 的事件驱动能力依赖稳定的服务编排：

1. **ServiceManager (`core/service_manager.py`)**
   * 声明式注册后台服务（内置 MQTT Broker、自定义采集器等）。
   * 提供统一的 `start/stop/restart` 接口，并通过 `global_signals.service_state_changed` 广播状态，方便 UI、任务与监控工具感知变化。
2. **MessageBusManager (`utils/message_bus.py`)**
   * 支持外部 Broker 与嵌入式 Broker 双模式，依据配置自动连接、重连与故障告警。
   * 与 ServiceManager 联动：仅在 Broker 服务进入 `RUNNING` 状态后建立 MQTT 会话，避免端口抢占或重复启动。
3. **事件安全机制**
   * 消息负载中的 `__hops` 计数可限制事件跳数，阻断循环触发。
   * 结合 `config/config.ini` 的全局阈值与日志追踪，可快速定位异常链路并触发告警。

这套组合确保后台服务稳定、消息链路透明，使事件驱动任务在桌面端保持高可靠性与可观测性。

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

* **操作系统**：Windows 10/11、macOS 12+、常见 Linux 桌面发行版（需具备图形界面）。
* **Python**：推荐 Python 3.10 或更高版本；请确保虚拟环境内的 `pip`、`setuptools`、`wheel` 保持最新，避免构建时缺失资源文件。
* **依赖组件**：
  * GUI 运行依赖 Qt 平台插件；在部分 Linux 发行版上需提前安装 `libxcb`、`qt5-default` 等系统包。
  * 消息总线默认连接外部 MQTT Broker；启用内置 `amqtt` 服务时需确认监听端口可用，并允许本地回环访问。
  * 可选扩展：如需截图、OCR 等增强模块，可在虚拟环境中额外安装 `pillow`、`opencv-python` 等库。

### 打包指引

1. 创建隔离环境并安装构建依赖：
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install --upgrade pip setuptools wheel pyinstaller
   ```
2. 在项目根目录执行：
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
3. 将 `dist/T4T`（或 `.app`/`.exe`）连同 `config/`、`tasks/`、`logs/` 目录及自定义模块资源一并打包分发。
4. 若启用内置 MQTT Broker，请在部署脚本或运维手册中新增：
   * 端口占用检测与防火墙策略说明；
   * 服务随系统启动或运行前手动启动的操作步骤。

> 💡 **提示**：建议在目标平台执行一次全流程自检（含消息总线连接、主题切换、模块执行）后再交付，可显著降低部署后返工成本。

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
