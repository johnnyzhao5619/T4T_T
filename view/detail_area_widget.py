import logging
from PyQt5.QtWidgets import QTabWidget, QWidget, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt
from utils.i18n import _
from utils.icon_manager import get_icon
from core.task_manager import TaskManager
from view.task_detail_tab_widget import TaskDetailTabWidget
from view.settings_widget import SettingsWidget
from view.new_task_widget import NewTaskWidget
from utils.signals import a_signal

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
        a_signal.task_renamed.connect(self.on_task_renamed)

        # Apply VS Code-like styling for tabs
        self.setStyleSheet("""
            QTabBar::tab {
                padding: 8px 15px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                border: 1px solid #333;
                border-bottom: none;
                background-color: #2d2d2d;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                border-color: #555;
            }
            QTabBar::tab:!selected:hover {
                background-color: #3c3c3c;
            }
            QTabWidget::tab-bar {
                alignment: left;
            }
        """)

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

        icon = get_icon(icon_name)
        index = self.addTab(widget, icon, title)
        self.open_tabs[widget_id] = index
        self.setCurrentIndex(index)

        self._update_tab_indices()

    def close_task_tab(self, index):
        widget = self.widget(index)

        # Find the ID of the tab to close
        tab_id_to_remove = None
        for tab_id, tab_index in self.open_tabs.items():
            if tab_index == index:
                tab_id_to_remove = tab_id
                break

        if tab_id_to_remove:
            # Special handling for task tabs
            if isinstance(widget, TaskDetailTabWidget):
                widget.save_splitter_state()

            widget.deleteLater()
            self.removeTab(index)
            del self.open_tabs[tab_id_to_remove]

            logger.info(
                f"Closed tab and released resources for: {tab_id_to_remove}")
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
            # The widget's internal task_name is updated via its own signal
            logger.info(f"Tab for task '{old_name}' updated to '{new_name}'.")

    def _update_tab_indices(self):
        # Rebuild the open_tabs dictionary based on current tab order
        current_tabs = {}
        for i in range(self.count()):
            widget = self.widget(i)
            # Find the ID for this widget instance
            for tab_id, tab_widget in self.open_tabs.items():
                if self.widget(self.open_tabs[tab_id]) is widget:
                    current_tabs[tab_id] = i
                    break
        self.open_tabs = current_tabs

    def update_details(self, task_name: str, status: str):
        if task_name:
            self.open_task_tab(task_name)

    def clear_details(self):
        pass

    def retranslate_ui(self):
        if self.count() == 1 and self.widget(0) == self.welcome_widget:
            self.setTabText(0, _("welcome_tab_title"))
