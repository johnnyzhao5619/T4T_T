# T4T - Task For Task

**T4T 是一个用 Python 和 PyQt5 构建的、高度可扩展的桌面自动化平台。它旨在成为一个灵活的、事件驱动的任务管理与执行中心。**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## ✨ 核心特性

*   **双模式触发**: 支持传统的 **定时调度** (Cron, Interval) 和强大的 **事件驱动** 任务。
*   **插件化模块系统**: 通过简单的 `manifest.yaml` 和 Python 脚本即可创建新功能模块，实现真正的“热插拔”。
*   **消息总线集成**: 内置 MQTT 客户端，允许任务间以及任务与外部系统（如 IoT 设备、Web API）之间进行解耦通信。
*   **并发执行**: 使用线程池模型异步执行所有任务，确保 UI 流畅，任务互不阻塞。
*   **丰富的用户界面**: 提供任务管理、实时日志、状态监控、多语言和主题切换等功能。
*   **上下文感知日志**: 每个任务的日志都自动与任务实例关联，调试清晰明了。

## 🚀 技术栈

*   **后端**: Python 3
*   **UI**: PyQt5
*   **核心架构**: 事件驱动、发布/订阅模式
*   **并发**: `ThreadPoolExecutor`
*   **消息队列**: Paho-MQTT
*   **调度**: APScheduler (用于 `schedule` 类型任务)

## 📖 文档

*   **[用户手册](./docs/user_manual.md)**: 为最终用户准备的指南，介绍如何使用本软件的各项功能。
*   **[开发者指南](./docs/development_guide.md)**: 为开发者准备的详细文档，介绍如何创建新的 V2 模块、核心 API 和架构概念。

## 快速开始

1.  **克隆仓库**
    ```bash
    git clone [https://github.com/your-repo/T4T.git](https://github.com/johnnyzhao5619/T4T_T.git)
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

1.  Fork 本仓库
2.  创建您的特性分支 (`git checkout -b feature/AmazingFeature`)
3.  提交您的更改 (`git commit -m 'Add some AmazingFeature'`)
4.  推送到分支 (`git push origin feature/AmazingFeature`)
5.  打开一个 Pull Request

---

## 📄 许可

本项目采用 [MIT 许可](LICENSE) 。
