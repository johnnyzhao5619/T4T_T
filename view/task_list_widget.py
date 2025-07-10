import logging
from PyQt5.QtWidgets import (QListWidget, QListWidgetItem, QMenu, QAction,
                             QInputDialog, QMessageBox, QLineEdit)
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt, QSize
from utils.signals import a_signal
from utils.icon_manager import get_icon
from utils.i18n import _

logger = logging.getLogger(__name__)


class TaskListWidget(QListWidget):
    """
    A custom widget to display and manage the list of tasks with status indicators
    and a context menu for quick actions.
    """

    def __init__(self, task_manager, scheduler, main_window, parent=None):
        super().__init__(parent)
        self.task_manager = task_manager
        self.scheduler = scheduler
        self.main_window = main_window  # Reference to the main window for actions
        self.setMinimumWidth(200)
        self.setMaximumWidth(400)
        self.setIconSize(QSize(16, 16))
        self.setContextMenuPolicy(Qt.CustomContextMenu)

        self.populate_tasks()

        # Connect signals
        self.customContextMenuRequested.connect(self.show_context_menu)
        a_signal.task_manager_updated.connect(self.refresh_tasks)
        a_signal.task_status_changed.connect(self._on_task_status_changed)
        a_signal.task_renamed.connect(self._on_task_renamed)

    def populate_tasks(self):
        self.clear()
        try:
            tasks = self.task_manager.get_task_list()
            if not tasks:
                logger.info("No tasks found to populate the list.")
                return

            for task_name in sorted(tasks):
                item = QListWidgetItem(task_name)
                self.addItem(item)
                status = self.task_manager.get_task_status(
                    task_name, self.scheduler)
                self.update_item_visuals(item, status)

            logger.info(f"Task list populated with {len(tasks)} tasks.")
        except Exception as e:
            logger.error(f"Failed to populate task list: {e}")

    def update_item_visuals(self, item: QListWidgetItem, status: str):
        status_visuals = {
            'running': {
                "icon": "fa5s.play-circle",
                "color": QColor("#2E7D32")
            },
            'paused': {
                "icon": "fa5s.pause-circle",
                "color": QColor("#FFC107")
            },
            'stopped': {
                "icon": "fa5s.stop-circle",
                "color": Qt.transparent
            },
            'error': {
                "icon": "fa5s.exclamation-circle",
                "color": QColor("#D32F2F")
            }
        }
        visual_config = status_visuals.get(status, status_visuals['stopped'])
        item.setIcon(get_icon(visual_config["icon"]))
        item.setBackground(visual_config["color"])

    def show_context_menu(self, position):
        item = self.itemAt(position)
        if not item:
            return

        task_name = item.text()
        status = self.task_manager.get_task_status(task_name, self.scheduler)

        context_menu = QMenu(self)

        start_action = context_menu.addAction(
            get_icon('fa5s.play', color_key='primary'), _("start_task_action"))
        stop_action = context_menu.addAction(
            get_icon('fa5s.stop', color_key='error'), _("stop_task_action"))
        context_menu.addSeparator()
        rename_action = context_menu.addAction(get_icon('fa5s.edit'),
                                               _("rename_task_action"))
        delete_action = context_menu.addAction(
            get_icon('fa5s.trash-alt', color_key='warning'),
            _("delete_task_action"))

        start_action.setEnabled(status in ['stopped', 'paused', 'error'])
        stop_action.setEnabled(status in ['running', 'paused'])

        action = context_menu.exec_(self.mapToGlobal(position))

        if action == start_action:
            self.main_window.start_task()
        elif action == stop_action:
            self.main_window.stop_task()
        elif action == rename_action:
            self.rename_task(item)
        elif action == delete_action:
            self.main_window.delete_task()

    def rename_task(self, item):
        old_name = item.text()
        new_name, ok = QInputDialog.getText(self,
                                            _("rename_task_dialog_title"),
                                            _("rename_task_dialog_prompt"),
                                            QLineEdit.Normal, old_name)

        if ok and new_name and new_name != old_name:
            if self.task_manager.rename_task(old_name, new_name):
                QMessageBox.information(
                    self, _("success_title"),
                    _("task_renamed_success_message").format(old=old_name,
                                                             new=new_name))
            else:
                QMessageBox.critical(self, _("error_title"),
                                     _("task_rename_failed_message"))

    def refresh_tasks(self):
        logger.debug("Refreshing task list.")
        current_selection = self.currentItem().text() if self.currentItem(
        ) else None
        self.populate_tasks()
        if current_selection:
            items = self.findItems(current_selection, Qt.MatchExactly)
            if items:
                self.setCurrentItem(items[0])

    def retranslate_ui(self):
        pass

    def _on_task_status_changed(self, task_name: str, status: str):
        logger.info(
            f"Slot triggered: Task '{task_name}' status changed to '{status}'."
        )
        items = self.findItems(task_name, Qt.MatchExactly)
        if items:
            self.update_item_visuals(items[0], status)
        else:
            logger.warning(
                f"Could not find item for task '{task_name}' to update status."
            )

    def _on_task_renamed(self, old_name: str, new_name: str):
        logger.info(
            f"Slot triggered: Task '{old_name}' renamed to '{new_name}'.")
        items = self.findItems(old_name, Qt.MatchExactly)
        if items:
            items[0].setText(new_name)
        else:
            logger.warning(
                f"Could not find item for task '{old_name}' to rename.")
