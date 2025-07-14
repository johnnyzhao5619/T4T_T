import logging
from PyQt5.QtWidgets import (QTreeWidget, QTreeWidgetItem, QMenu, QInputDialog,
                             QMessageBox, QLineEdit, QHeaderView)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from utils.signals import global_signals
from utils.icon_manager import get_icon
from utils.i18n import _

logger = logging.getLogger(__name__)


class TaskListWidget(QTreeWidget):
    """
    A custom widget to display and manage the list of tasks in a multi-column
    view with status indicators and a context menu.
    """

    def __init__(self, task_manager, scheduler, main_window, parent=None):
        super().__init__(parent)
        self.task_manager = task_manager
        self.scheduler = scheduler
        self.main_window = main_window
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setColumnCount(4)
        headers = [
            _("header_task_name"),
            _("header_status"),
            _("header_last_run"),
            _("header_details")
        ]
        self.setHeaderLabels(headers)
        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        self.populate_tasks()

        # Connect signals
        self.customContextMenuRequested.connect(self.show_context_menu)
        global_signals.task_manager_updated.connect(self.refresh_tasks)
        global_signals.task_status_changed.connect(
            self._on_task_status_changed)
        global_signals.task_renamed.connect(self._on_task_renamed)
        global_signals.task_succeeded.connect(self._on_task_succeeded)
        global_signals.task_failed.connect(self._on_task_failed)

    def find_item_by_name(self, task_name: str) -> QTreeWidgetItem | None:
        """Find a top-level item by the task name in the first column."""
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.text(0) == task_name:
                return item
        return None

    def populate_tasks(self):
        self.clear()
        try:
            tasks = self.task_manager.get_task_list()
            if not tasks:
                logger.info("No tasks found to populate the list.")
                return

            for task_name in sorted(tasks):
                item = QTreeWidgetItem(self)
                item.setText(0, task_name)
                self.addTopLevelItem(item)

                # Update visuals based on current status
                status = self.task_manager.get_task_status(task_name)
                self.update_item_visuals(item, status)

            logger.info(f"Task list populated with {len(tasks)} tasks.")
        except Exception as e:
            logger.error(f"Failed to populate task list: {e}")

    def update_item_visuals(self, item: QTreeWidgetItem, status: str):
        status_visuals = {
            'running': {
                "icon": "fa5s.play-circle",
                "text": _("status_running")
            },
            'listening': {
                "icon": "fa5s.satellite-dish",
                "text": _("status_listening")
            },
            'paused': {
                "icon": "fa5s.pause-circle",
                "text": _("status_paused")
            },
            'stopped': {
                "icon": "fa5s.stop-circle",
                "text": _("status_stopped")
            },
            'error': {
                "icon": "fa5s.exclamation-circle",
                "text": _("status_error")
            }
        }
        visual_config = status_visuals.get(status, status_visuals['stopped'])
        item.setIcon(0, get_icon(visual_config["icon"]))
        item.setText(1, visual_config["text"])

    def show_context_menu(self, position):
        item = self.itemAt(position)
        if not item:
            return

        task_name = item.text(0)
        status = self.task_manager.get_task_status(task_name)

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
        stop_action.setEnabled(status in ['running', 'paused', 'listening'])

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
        old_name = item.text(0)
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
        current_item = self.currentItem()
        current_selection = current_item.text(0) if current_item else None

        self.populate_tasks()

        if current_selection:
            item_to_select = self.find_item_by_name(current_selection)
            if item_to_select:
                self.setCurrentItem(item_to_select)

    def retranslate_ui(self):
        headers = [
            _("header_task_name"),
            _("header_status"),
            _("header_last_run"),
            _("header_details")
        ]
        self.setHeaderLabels(headers)
        # Instead of refreshing the whole list, just update the status text
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            task_name = item.text(0)
            status = self.task_manager.get_task_status(task_name)
            self.update_item_visuals(item, status)

    def _on_task_status_changed(self, task_name: str, status: str):
        logger.info(
            f"Slot triggered: Task '{task_name}' status changed to '{status}'."
        )
        item = self.find_item_by_name(task_name)
        if not item:
            logger.warning(
                f"Could not find item for task '{task_name}' to update status."
            )
            return

        self.update_item_visuals(item, status)

        if status == 'listening':
            task_config = self.task_manager.get_task_config(task_name)
            topic = task_config.get('trigger', {}).get('topic', 'N/A')
            item.setText(3, f"{_('listening_on')}: {topic}")
            item.setToolTip(3, f"{_('listening_on_tooltip')}: {topic}")
        elif status == 'stopped':
            # Clear details when stopped
            item.setText(2, "")
            item.setText(3, "")
            item.setToolTip(3, "")

    def _on_task_succeeded(self, task_name: str, timestamp: str, message: str):
        """
        Update the task item when a task execution succeeds.
        """
        item = self.find_item_by_name(task_name)
        if item:
            item.setText(2, timestamp)
            item.setText(3, _("status_success"))
            item.setForeground(3, QColor('green'))
            item.setToolTip(3, message)

    def _on_task_failed(self, task_name: str, timestamp: str, error: str):
        """
        Update the task item when a task execution fails.
        """
        item = self.find_item_by_name(task_name)
        if item:
            item.setText(2, timestamp)
            item.setText(3, _("status_failed"))
            item.setForeground(3, QColor('red'))
            item.setToolTip(3, error)

    def _on_task_renamed(self, old_name: str, new_name: str):
        logger.info(
            f"Slot triggered: Task '{old_name}' renamed to '{new_name}'.")
        item = self.find_item_by_name(old_name)
        if item:
            item.setText(0, new_name)
        else:
            logger.warning(
                f"Could not find item for task '{old_name}' to rename.")
