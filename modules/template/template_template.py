# -*- coding: utf-8 -*-
"""
模块任务模板 V2
这是一个新模块任务的模板。

要创建一个新模块，请复制此目录并将其重命名为您的模块名称。
然后，将此文件名重命名以匹配目录名。
"""


def run(context, inputs):
    """
    这是模块任务的主入口点。
    当满足 manifest.yaml 中定义的触发条件时，系统会调用此函数。

    Args:
        context: 一个包含任务上下文信息的对象。它提供了对日志、配置和状态管理的访问。
                 可访问的属性包括：
                 - context.logger: 一个日志记录器实例，用于向UI和日志文件发送消息。
                   用法:
                       context.logger.info("这是一条信息日志")
                       context.logger.warning("这是一条警告日志")
                       context.logger.error("这是一条错误日志")
                       context.logger.debug("这是一条调试日志")

                 - context.task_name (str): 当前任务的名称，来自 manifest.yaml。
                   用法:
                       task_name = context.task_name
                       context.logger.info(f"任务 '{task_name}' 已启动")

                 - context.config (dict): 一个包含此任务完整配置的字典，
                                          内容来自 manifest.yaml。
                   用法:
                       api_key = context.config.get("settings", {}).get("api_key")

                 - context.get_state(key, default=None): 从持久化存储中获取一个状态值。
                   用法:
                       last_run = context.get_state("last_run_timestamp")

                 - context.update_state(key, value): 更新或添加一个状态值到
                   持久化存储。
                   用法:
                       from datetime import datetime
                       context.update_state("last_run_timestamp", datetime.now().isoformat())

        inputs (dict): 一个包含从触发事件的 payload 中映射过来的数据
                       的字典。
                       这些输入字段在 manifest.yaml 的 'inputs' 部分定义。
                       如果一个输入被标记为 'required: true'，系统会确保它
                       在调用此函数之前存在。
                       用法:
                           user_id = inputs.get("user_id")
                           if user_id:
                               context.logger.info(f"处理用户 {user_id} 的请求")
    """
    task_name = context.task_name
    context.logger.info(f"任务 '{task_name}' 已启动。")

    # --- 核心任务逻辑 ---
    # 在此替换为您的任务的实际逻辑。
    try:
        # 示例：访问 inputs 和 settings
        context.logger.info(f"收到的输入: {inputs}")

        message = inputs.get("message", "没有提供消息")
        context.logger.info(f"收到的消息是: '{message}'")

        # 示例：访问 manifest.yaml 中的自定义设置
        settings = context.config.get('settings', {})
        example_setting = settings.get('example_setting', '默认值')
        context.logger.info(f"'example_setting' 的值是: '{example_setting}'")

        # 示例：使用状态管理
        run_count = context.get_state("run_count", 0) + 1
        context.update_state("run_count", run_count)
        context.logger.info(f"这是任务第 {run_count} 次运行。")

        context.logger.info(f"任务 '{task_name}' 成功完成。")

    except Exception as e:
        # 关键：处理异常以防止整个应用程序因单个任务失败而崩溃。
        context.logger.error(f"任务 '{task_name}' 发生错误: {e}", exc_info=True)

    context.logger.info(f"任务 '{task_name}' 已结束。")
