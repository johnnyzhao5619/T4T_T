import logging

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from core.task_manager import TaskManager
from utils.i18n import _
from utils.icon_manager import get_icon
from utils.signals import global_signals
from view.help_widget import HelpWidget
from view.log_viewer_widget import LogViewerWidget
from view.new_task_widget import NewTaskWidget
from view.settings_widget import SettingsWidget
from view.task_detail_tab_widget import TaskDetailTabWidget

logger = logging.getLogger(__name__)


class WelcomeWidget(QWidget):
    """A placeholder widget displayed when no tabs are open."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        icon_label = QLabel()
        icon = get_icon('fa5s.code', scale_factor=5)
        icon_label.setPixmap(icon.pixmap(128, 128))
        icon_label.setAlignment(Qt.AlignCenter)

        text_label = QLabel(_("welcome_message"))
        text_label.setAlignment(Qt.AlignCenter)
        text_label.setStyleSheet("font-size: 18px; color: gray;")

        layout.addWidget(icon_label)
        layout.addWidget(text_label)


class DetailAreaWidget(QTabWidget):
    """
    A custom QTabWidget to display and manage task details in a dynamic,
    closable tab interface, with left-aligned tabs.
    """

    def __init__(self, task_manager: TaskManager, parent=None):
        super().__init__(parent)
        self.task_manager = task_manager
        self.open_tabs = {}

        self.setTabsClosable(True)
        self.setMovable(True)
        self.tabCloseRequested.connect(self.close_task_tab)
        global_signals.task_renamed.connect(self.on_task_renamed)

        # Set tab bar alignment to the left
        self.setStyleSheet("QTabWidget::tab-bar { alignment: left; }")

        self.welcome_widget = WelcomeWidget(self)
        self.addTab(self.welcome_widget, _("welcome_tab_title"))
        self.tabBar().setTabButton(0, self.tabBar().RightSide, None)

    def open_task_tab(self, task_name: str):
        self.open_widget_as_tab(
            widget_id=task_name,
            widget_class=TaskDetailTabWidget,
            title=task_name,
            icon_name='fa5s.tasks',
            constructor_args=[task_name, self.task_manager])

    def open_settings_tab(self):
        self.open_widget_as_tab(widget_id="settings_tab",
                                widget_class=SettingsWidget,
                                title=_("settings_action"),
                                icon_name='fa5s.cog')

    def open_log_viewer_tab(self):
        self.open_widget_as_tab(widget_id="log_viewer_tab",
                                widget_class=LogViewerWidget,
                                title=_("logs_action"),
                                icon_name='fa5s.file-alt')

    def open_help_tab(self):
        self.open_widget_as_tab(widget_id="help_tab",
                                widget_class=HelpWidget,
                                title=_("help_action"),
                                icon_name='fa5s.question-circle')

    def open_new_task_tab(self):
        widget_id = "new_task_tab"
        if widget_id in self.open_tabs:
            self.setCurrentIndex(self.open_tabs[widget_id])
            return

        # Special handling for this widget because it can close itself
        # and open another tab.
        if len(self.open_tabs) == 0 and self.count() == 1 and self.widget(
                0) == self.welcome_widget:
            self.removeTab(0)

        widget = NewTaskWidget(self.task_manager)
        widget.task_created.connect(self.on_new_task_created)
        widget.widget_id = widget_id  # Assign ID to widget

        icon = get_icon('fa5s.plus-square')
        index = self.addTab(widget, icon, _("add_task_action"))
        self.open_tabs[widget_id] = index
        self.setCurrentIndex(index)

        self._update_tab_indices()

    def on_new_task_created(self, task_name):
        # Close the "New Task" tab
        if "new_task_tab" in self.open_tabs:
            index_to_close = self.open_tabs["new_task_tab"]
            self.close_task_tab(index_to_close)

        # Open the new task's tab
        self.open_task_tab(task_name)

    def open_widget_as_tab(self,
                           widget_id,
                           widget_class,
                           title,
                           icon_name,
                           constructor_args=None):
        if widget_id in self.open_tabs:
            self.setCurrentIndex(self.open_tabs[widget_id])
            return

        # Remove welcome widget if it's the only tab
        if len(self.open_tabs) == 0 and self.count() == 1 and self.widget(
                0) == self.welcome_widget:
            self.removeTab(0)

        constructor_args = constructor_args or []
        widget = widget_class(*constructor_args)
        widget.widget_id = widget_id  # Assign ID to widget

        icon = get_icon(icon_name)
        index = self.addTab(widget, icon, title)
        self.open_tabs[widget_id] = index
        self.setCurrentIndex(index)

        self._update_tab_indices()

    def close_task_tab(self, index):
        widget = self.widget(index)
        if not hasattr(widget, 'widget_id'):
            # This can happen if the welcome widget is somehow targeted,
            # which shouldn't occur with a non-closable tab.
            logger.warning("Attempted to close a tab without a widget_id.")
            # It's safer to just remove the tab if we don't know what it is.
            self.removeTab(index)
            return

        tab_id_to_remove = widget.widget_id

        if tab_id_to_remove in self.open_tabs:
            # Special handling for task tabs that have a splitter state
            if isinstance(widget, TaskDetailTabWidget):
                widget.save_splitter_state()

            # Remove from dictionary first
            del self.open_tabs[tab_id_to_remove]

            # Now remove from UI and schedule for deletion
            self.removeTab(index)
            widget.deleteLater()

            logger.info(
                f"Closed tab and released resources for: {tab_id_to_remove}")
            # Resync indices for all remaining tabs
            self._update_tab_indices()

        if self.count() == 0:
            self.addTab(self.welcome_widget, _("welcome_tab_title"))
            self.tabBar().setTabButton(0, self.tabBar().RightSide, None)

    def on_task_renamed(self, old_name, new_name):
        if old_name in self.open_tabs:
            index = self.open_tabs.pop(old_name)
            self.open_tabs[new_name] = index
            self.setTabText(index, new_name)
            self.setTabToolTip(index, new_name)

            # Also update the widget_id on the widget itself
            widget = self.widget(index)
            if hasattr(widget, 'widget_id') and widget.widget_id == old_name:
                widget.widget_id = new_name

            logger.info(f"Tab for task '{old_name}' updated to '{new_name}'.")

    def _update_tab_indices(self):
        """
        Rebuilds the open_tabs dictionary to ensure all indices are correct,
        especially after a tab has been closed or moved.
        """
        new_open_tabs = {}
        for i in range(self.count()):
            widget = self.widget(i)
            # The welcome widget doesn't have a widget_id and isn't in open_tabs
            if hasattr(widget, 'widget_id'):
                new_open_tabs[widget.widget_id] = i
        self.open_tabs = new_open_tabs

    def update_details(self, task_name: str, status: str):
        if task_name:
            self.open_task_tab(task_name)

    def clear_details(self):
        pass

    def retranslate_ui(self):
        # Define a mapping from widget_id to its translatable title key
        title_keys = {
            "settings_tab": "settings_action",
            "log_viewer_tab": "logs_action",
            "help_tab": "help_action",
            "new_task_tab": "add_task_action",
            "dev_guide_tab": "dev_guide_title",
            "message_bus_monitor_tab": "message_bus_monitor_title",
        }

        for i in range(self.count()):
            widget = self.widget(i)
            widget_id = getattr(widget, 'widget_id', None)

            # Retranslate tab titles for known, non-task tabs
            if widget_id and widget_id in title_keys:
                self.setTabText(i, _(title_keys[widget_id]))
            # Special case for the welcome widget
            elif widget == self.welcome_widget:
                self.setTabText(i, _("welcome_tab_title"))

            # Retranslate the content of the widget itself if possible
            if hasattr(widget, 'retranslate_ui'):
                widget.retranslate_ui()
