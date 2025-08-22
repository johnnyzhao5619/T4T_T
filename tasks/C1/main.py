# -*- coding: utf-8 -*-
"""
V2 Counter Module
A simple counter task that increments a number and logs it.
It persists the count using the context's state management.
"""


def run(context, inputs):
    """
    Main entry point for the counter task.

    Args:
        context: The task context object, providing access to logging, config,
                 and state management.
        inputs (dict): Data from the triggering event payload. For this module,
                       it might contain an optional 'increment_by' value.
    """
    task_name = context.task_name
    context.logger.info(f"任务 '{task_name}' 正在运行。")

    try:
        # 从 'inputs' 或 'settings' 获取增量值，'inputs' 优先
        # 这允许事件动态地覆盖默认增量
        default_increment = context.config.get('settings', {})\
                                          .get('increment_by', 1)
        increment_by = inputs.get('increment_by', default_increment)

        # 使用 context.get_state 获取当前计数值，如果不存在则默认为 0
        current_count = context.get_state('count', 0)

        # 执行核心逻辑
        new_count = current_count + increment_by
        context.logger.info(f"计数值更新为: {new_count}")

        # 使用 context.update_state 持久化新的计数值
        context.update_state('count', new_count)
        context.logger.info(f"已成功保存新的计数值 ({new_count})。")

    except Exception as e:
        context.logger.error(f"计数器任务 '{task_name}' 发生错误: {e}", exc_info=True)
