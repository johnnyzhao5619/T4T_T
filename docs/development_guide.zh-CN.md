[English](./development_guide.md) | [简体中文](./development_guide.zh-CN.md)

---

# T4T 开发者指南 (V2)

欢迎来到 T4T V2 模块开发的世界！本文档将引导您了解新的事件驱动架构、核心概念以及如何构建一个功能完备的 V2 模块。

## 1. V2 模块结构概览

一个 V2 模块由两个核心文件组成，它们共同定义了模块的行为和元数据。

* **`manifest.yaml`**: 这是模块的“身份证”。它是一个声明式的配置文件，用于定义模块的名称、触发方式、输入参数以及其他元数据。系统通过解析这个文件来了解如何以及何时执行你的任务。
* **任务脚本 (`__init__.py` 或其他指定脚本)**: 这是模块的“大脑”，包含了实际的业务逻辑。其核心是一个名为 `run` 的函数，系统会在触发条件满足时调用它。

---

## 2. 编写任务脚本 (`run` 函数)

V2 模块的入口点是一个具有标准签名的 `run` 函数。这个函数的设计遵循“依赖注入”的原则，使得测试和代码复用变得更加简单。

```python
def run(context, inputs):
    """
    一个标准的 V2 任务函数。

    :param context: 由系统注入的上下文对象，提供对日志、消息总线等核心服务的访问。
    :param inputs: 一个包含任务所需输入数据的字典。
    """
    # 你的代码逻辑在这里
    pass
```

### 2.1. 上下文对象 (`context`)

`context` 对象是你的任务与 T4T 系统交互的桥梁。它是一个由任务管理器在运行时动态创建并传入的实例，包含了执行任务所需的所有环境信息和服务。

**`context` 对象的属性:**

| 属性 | 类型 | 描述 |
| :--- | :--- | :--- |
| `task_name` | `str` | 当前执行的任务实例的名称。 |
| `logger` | `logging.Logger` | 标准 Python 日志记录器，可使用 `.info()`、`.warning()`、`.error()`、`.debug()` 等方法输出任务级日志。 |

**代码示例：使用上下文日志**

使用 `context.logger` 而不是 `print()` 是最佳实践，因为它能将日志与特定的任务关联起来，便于调试。

```python
def run(context, inputs):
    context.logger.info(f"任务 '{context.task_name}' 已启动。")

    try:
        # ... 核心逻辑 ...
        result = "操作成功"
        context.logger.info(f"处理完成: {result}")
    except Exception as e:
        context.logger.error(f"任务执行失败: {e}")

```

### 2.2. 输入数据 (`inputs`)

`inputs` 参数是一个字典，包含了任务执行所需的所有数据。这些数据的来源由 `manifest.yaml` 中的 `trigger` 和 `inputs` 配置决定。

* **对于事件触发器 (`event`)**: `inputs` 字典的键值对通常来自于触发事件的 `payload`（例如，一个 MQTT 消息的内容）。
* **对于定时触发器 (`schedule`)**: `inputs` 字典通常为空，因为这类任务不是由外部数据驱动的。

---

## 3. 配置清单 (`manifest.yaml`)

`manifest.yaml` 是 V2 模块的核心，它以一种清晰、可读的方式定义了模块的行为。

### 3.1. 触发器 (`trigger`)

`trigger` 字段定义了启动任务的条件。T4T V2 支持两种主要的触发器类型。

#### a) 定时触发器 (`schedule`)

当您希望任务按固定的时间表（例如，每小时、每天午夜）执行时，使用此触发器。它底层由 `APScheduler` 支持。

**完整配置示例:**

```yaml
# manifest.yaml
name: "每日报告任务"
module_type: "reporting_v2"
version: "1.0"

trigger:
  type: schedule
  config:
    type: cron      # cron, interval, or date
    hour: 0         # 每天 00:00 执行
    minute: 0
```

#### b) 事件触发器 (`event`)

当您希望任务响应系统中的特定事件（例如，另一任务完成、收到一条 MQTT 消息）时，使用此触发器。这是构建响应式、解耦系统的关键。

**完整配置示例:**

```yaml
# manifest.yaml
name: "温度传感器处理器"
module_type: "sensor_handler_v2"
version: "1.0"

trigger:
  type: event
  config:
    topic: "sensors/temperature/reading" # 订阅 MQTT 主题
    max_hops: 5 # 可选，防止事件链路循环触发
```

> 💡 **安全提示**：`max_hops` 用于限制事件在任务之间转发的最大跳数。当 payload 中的 `__hops` 大于此阈值时，任务会记录错误并忽略该事件。若未在任务中指定，系统会回退到 `config/config.ini` 中 `[TaskDefaults] event_max_hops` 的全局默认值（默认值：`5`）。

### 3.2. 输入映射与验证 (`inputs`)

`inputs` 字段是 `manifest.yaml` 中一个至关重要的部分。它扮演着双重角色：

1. **数据映射**: 它声明了任务 `run` 函数期望接收哪些输入参数。对于事件触发器，系统会尝试从事件的 `payload` 中提取这些字段。
2. **前置验证**: 它是保护你的任务免受无效或缺失数据影响的第一道防线。

**重点: `required: true`**

当一个输入字段被标记为 `required: true` 时，任务管理器会在调用 `run` 函数**之前**检查该字段是否存在于输入数据中。如果数据缺失，任务将不会被执行，并会在系统日志中记录一条错误。这可以极大地简化你 `run` 函数中的错误处理逻辑。

**配置示例:**

```yaml
# manifest.yaml
name: "用户注册处理器"
# ... 其他配置 ...

trigger:
  type: event
  config:
    topic: "users/register"

inputs:
  - name: username
    type: string
    description: "用户的唯一标识符。"
    required: true  # 如果 MQTT 消息中没有 username 字段，任务将不会运行

  - name: email
    type: string
    description: "用户的电子邮件地址。"
    required: true

  - name: referral_code
    type: string
    description: "推荐码（可选）。"
    required: false # 这个字段是可选的
```

### 3.3. UI 表单描述（`schema`）

`schema` 是一个可选的元数据段，用来告诉任务管理器如何渲染模块的配置表单。每个条目都对应一个配置键（使用点号表示嵌套路径），并可以声明标签、描述信息以及所属分组等属性。

```yaml
schema:
  name:
    label: "任务名称"
    description: "在控制台中展示的名称。"
    group: "基础信息"
  trigger:
    label: "执行计划"
    group: "调度"
  settings.increment_by:
    type: integer
    label: "自增步长"
    min: 1
    group: "计数器设置"
```

编写 `schema` 时请注意：

* **点号路径** 可精准指向嵌套字典（例如 `settings.increment_by`）。
* **`group` 字段** 用于控制字段在 UI 中的分组，只要分组名称相同就会自动聚合并生成一个标题。
* **特殊区块**（如 `trigger` 与 `inputs`）依然会渲染专属的交互组件，同时尊重在 schema 中声明的分组与标签。
* **兼容策略**：未在 schema 中声明的字段会根据配置结构自动归组；旧版依赖 `properties` 嵌套的 schema 仍然受支持，无需强制迁移。

---

## 4. 核心概念详解

### 4.1. 并发模型

T4T V2 采用 `ThreadPoolExecutor` 来管理一个工作线程池。所有的任务（无论是 `schedule` 还是 `event` 触发）都会被提交到这个线程池中异步执行。

* **与旧模型的区别**: 在旧的 `APScheduler` 模型中，长时间运行的任务可能会阻塞调度器线程。新的线程池模型确保了每个任务都在一个独立的线程中运行，从而避免了任务之间的相互干扰，并保证了主应用的 UI 始终保持响应。

### 4.2. 事件驱动与消息总线

系统的核心是一个轻量级的**消息总线**（默认使用 MQTT 实现）。它允许不同的模块和任务之间以“发布/订阅”的模式进行通信，而无需直接相互依赖。

* **角色**: 消息总线是整个系统事件驱动架构的基石。一个任务可以向一个主题（Topic）发布一条消息（例如 `task/A/completed`），而其他任意数量的任务都可以订阅这个主题，并在消息到达时被触发。这种模式极大地提高了系统的灵活性和可扩展性。

### 4.3. 后台服务与 ServiceManager

`ServiceManager` 负责统一管理后台服务（例如嵌入式 MQTT Broker）的生命周期。系统在 `main.py` 中显式注册所需服务，以保证入口唯一性。

* **注册策略**: 通过 `service_manager.register_service('mqtt_broker', EmbeddedMQTTBroker(...))` 注册服务。当需要重新配置或替换实例时，再次调用 `register_service` 会自动停止旧实例并解除它与 Qt 信号的绑定，避免残留线程或重复订阅。
* **何时调用**: 推荐仅在应用启动或配置发生变化时调用 `register_service`。这样可以确保新的配置被正确加载，同时防止旧实例继续响应消息。
* **清理保证**: `register_service` 内部会在替换前调用旧实例的 `stop()` 和 `disconnect_signals()`，并等待相关线程结束。重启或重新配置时无需额外手动清理。
* **连接流程**: `MessageBusManager.connect()` 会在启动消息总线前检查 `ServiceState`。当 MQTT 模式配置为嵌入式时，它会确保 `mqtt_broker` 服务处于 `RUNNING` 状态：如果服务尚未启动则调用 `start_service`，同时阻塞等待 `global_signals.service_state_changed` 发出状态变更通知。若在默认超时时间内未等到 `RUNNING`，会记录易读的错误日志并跳过连接，避免重复启动或无限等待。

---

## 5. 一个完整的 V2 模块示例

让我们将以上所有概念整合到一个完整的、事件驱动的模块中。这个模块会监听一个 MQTT 主题，验证输入的温度数据，并根据温度值记录不同级别的日志。

**目录结构:**

```
modules/
└── smart_thermostat/
    ├── manifest.yaml
    └── smart_thermostat_template.py
```

**`manifest.yaml`:**

```yaml
name: "智能恒温器"
module_type: "smart_thermostat_v2"
version: "1.1"
description: "监听温度读数，如果过高则记录警告。"

trigger:
  type: event
  config:
    topic: "home/living_room/temperature"

inputs:
  - name: current_temp
    type: float
    description: "当前的摄氏温度读数。"
    required: true

  - name: device_id
    type: string
    description: "传感器的唯一ID。"
    required: false
```

**`smart_thermostat_template.py`:**

```python
def run(context, inputs):
    """
    处理温度传感器数据。
    """
    task_name = context.task_name
    logger = context.logger

    # 由于 manifest.yaml 中设置了 required: true，
    # 我们在这里可以安全地直接访问 'current_temp'。
    temperature = inputs['current_temp']
    device_id = inputs.get('device_id', '未知设备') # .get() 用于可选字段

    logger.info(f"[{task_name}] 从 '{device_id}' 收到温度数据: {temperature}°C")

    if temperature > 30.0:
        logger.warning(f"[{task_name}] 高温警报！温度已达到 {temperature}°C。")
    elif temperature < 5.0:
        logger.warning(f"[{task_name}] 低温警报！温度已降至 {temperature}°C。")
    else:
        logger.info(f"[{task_name}] 温度 '{temperature}°C' 在正常范围内。")

```

这个示例展示了如何利用 V2 架构的特性——声明式的 `manifest.yaml`、健壮的输入验证和上下文感知的日志记录——来创建一个简洁、可靠且易于维护的模块。

---

## 7. 许可与分发清单

* **附带 MIT 条款**：任何交付物都必须包含仓库根目录的 `LICENSE` 文件。请在 PyInstaller 配置（详见 README 指引）或未来的打包脚本中显式添加该文件。
* **明确 PyQt5 合规策略**：PyQt5 在未购买商业许可时以 GPL v3 方式发布。若以 MIT 许可分发项目，请确保：
  * 按 GPL 要求公开全部源代码并满足传染性条款，或
  * 从 Riverbank Computing 获取商业许可。
  请在部署说明中记录所采用的策略，方便下游使用者理解授权边界。
* **第三方依赖概览**：当前运行时依赖及其许可证如下：
  * psutil – BSD 3-Clause
  * PyYAML – MIT
  * paho-mqtt – Eclipse Distribution License 1.0
  * APScheduler – MIT
  * qtawesome – MIT
  * amqtt – MIT
  * pyqtgraph – MIT
  * PyAutoGUI – BSD 3-Clause
  * Markdown 3.4.4 – BSD 3-Clause
  这些许可证与 MIT 兼容，但在新增依赖时应重新审查。
