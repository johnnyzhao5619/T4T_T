[English](./README.md) | [简体中文](./README.zh-CN.md) | [Français](./README.fr.md)

---

# T4T - Task For Task

**T4T 是一个用 Python 和 PyQt5 构建的、高度可扩展的桌面自动化平台。它旨在成为一个灵活的、事件驱动的任务管理与执行中心。**

[![许可: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## ✨ 核心特性

*   **双模式触发**: 支持传统的 **定时调度** (Cron, Interval) 和强大的 **事件驱动** 任务。
*   **插件化模块系统**: 通过简单的 `manifest.yaml` 和 Python 脚本即可创建新功能模块，实现真正的“热插拔”。
*   **消息总线集成**: 内置 MQTT 客户端，允许任务间以及任务与外部系统（如 IoT 设备、Web API）之间进行解耦通信。
*   **并发执行**: 使用线程池模型异步执行所有任务，确保 UI 流畅，任务互不阻塞。
*   **丰富的用户界面**: 提供任务管理、实时日志、状态监控、多语言和主题切换等功能。
*   **上下文感知日志**: 每个任务的日志都自动与任务实例关联，调试清晰明了。

## 📂 项目结构
```
/
├─── core/              # 核心应用逻辑 (TaskManager, ModuleManager 等)
├─── docs/              # 文档文件
├─── i18n/              # 国际化文件 (en.json, zh-CN.json, fr.json)
├─── modules/           # 可重用的模块模板 (manifest.yaml, 脚本)
├─── tasks/             # 用户配置的任务实例
├─── utils/             # 工具类 (Logger, ThemeManager, MessageBus)
├─── view/              # PyQt5 UI 组件和窗口
├─── main.py            # 主应用入口点
├─── requirements.txt   # Python 依赖
└─── README.md          # 本文件
```

## 🏛️ 项目架构

项目采用分层架构，清晰地分离了表现层、业务逻辑层和服务层。

*   **表现层 (`view/`)**: 完整的用户界面，使用 PyQt5 构建。它负责显示数据并将用户操作转发到核心层。
*   **核心层 (`core/`)**: 应用的核心。它包含了主要的业务逻辑：
    *   `ModuleManager`: 发现并管理所有可用的模块 (`modules/`)。
    *   `TaskManager`: 管理所有任务实例 (`tasks/`) 的生命周期，包括它们的创建、执行和状态。
    *   `Scheduler`: `APScheduler` 的外观，处理所有基于时间的触发器。
    *   `StateManager`: 管理应用和任务的状态。
*   **工具层 (`utils/`)**: 在整个应用中使用的工具类和函数的集合，如日志记录、国际化、主题管理和系统范围的消息总线。
*   **模块与任务**:
    *   `modules/`: 包含可重用的任务“模板”。
    *   `tasks/`: 包含已配置的模块实例，每个实例都有自己的 `config.yaml`。

## 🚀 技术栈

*   **后端**: Python 3
*   **UI**: PyQt5
*   **核心架构**: 事件驱动、发布/订阅模式
*   **并发**: `ThreadPoolExecutor`
*   **消息队列**: Paho-MQTT
*   **调度**: APScheduler (用于 `schedule` 类型的任务)

## 📖 文档

*   **[用户手册](./docs/user_manual.md)**: 为最终用户准备的指南，介绍如何使用本软件的各项功能。
*   **[开发者指南](./docs/development_guide.md)**: 为开发者准备的详细文档，介绍如何创建新的 V2 模块、核心 API 和架构概念。

## 快速开始

1.  **克隆仓库**
    ```bash
    git clone https://github.com/your-repo/T4T.git
    cd T4T
    ```

2.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    ```

3.  **运行应用**
    ```bash
    python main.py
    ```

## 贡献

欢迎任何形式的贡献！无论是提交 Bug 报告、功能建议还是代码 Pull Request。

1.  Fork 本项目
2.  创建您的特性分支 (`git checkout -b feature/AmazingFeature`)
3.  提交您的更改 (`git commit -m 'Add some AmazingFeature'`)
4.  推送到分支 (`git push origin feature/AmazingFeature`)
5.  打开一个 Pull Request

---

## 📄 许可

本项目采用 [MIT 许可](LICENSE)。
