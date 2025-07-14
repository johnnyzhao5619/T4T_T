# -*- coding: utf-8 -*-
"""
V2 Screen Protector Module
Checks for mouse inactivity and jiggles the mouse if the system is idle.
State is managed by the context object.
"""
import random
import pyautogui


def run(context, inputs):
    """
    Main entry point for the screen protector task.

    Args:
        context: The task context object.
        inputs (dict): Not used in this module.
    """
    task_name = context.task_name
    context.logger.debug(f"任务 '{task_name}' 正在运行。")

    try:
        # 使用 context.get_state 获取上次的鼠标位置
        last_position = context.get_state('last_position')
        current_position = list(pyautogui.position())

        context.logger.debug(
            f"检查活动。当前位置: {current_position}, 上次位置: {last_position}")

        # 比较当前位置与上次保存的位置
        if last_position and last_position == current_position:
            # 检测到空闲：移动鼠标
            context.logger.info("检测到系统空闲，正在移动鼠标。")

            settings = context.config.get('settings', {})
            min_jiggle = settings.get('mouse_jiggle_range_min', 10)
            max_jiggle = settings.get('mouse_jiggle_range_max', 50)

            dx = (random.randint(min_jiggle, max_jiggle) *
                  random.choice([-1, 1]))
            dy = (random.randint(min_jiggle, max_jiggle) *
                  random.choice([-1, 1]))

            pyautogui.moveRel(dx, dy)
            new_pos = list(pyautogui.position())

            context.logger.info(f"鼠标已从 {current_position} 移动到 {new_pos}。")

            # 更新 current_position 为移动后的新位置
            current_position = new_pos
        else:
            # 非空闲或首次运行
            context.logger.debug(f"鼠标活动或首次运行。更新位置为 {current_position}。")

        # 使用 context.update_state 保存当前位置以备下次运行
        context.update_state('last_position', current_position)

    except Exception as e:
        context.logger.error(f"屏幕保护任务 '{task_name}' 发生错误: {e}", exc_info=True)
