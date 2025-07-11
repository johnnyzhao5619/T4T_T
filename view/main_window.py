import logging
import psutil
import os
import shutil
import json
from functools import partial
from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QStatusBar,
    QToolBar,
    QAction,
    QSplitter,
    QMessageBox,
    QInputDialog,
    QTextBrowser,
    QPushButton,
)
from PyQt5.QtCore import Qt, QTimer
from view.task_list_widget import TaskListWidget
from view.detail_area_widget import DetailAreaWidget
from utils.i18n import language_manager, _
from utils.theme import theme_manager
from utils.icon_manager import get_icon, set_theme as set_icon_theme
from utils.signals import a_signal

logger = logging.getLogger(__name__)


class DevGuideWidget(QWidget):
    """A widget to display the development guide."""

    def __init__(self, module_manager, parent=None):
        super().__init__(parent)
        self.module_manager = module_manager
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Add a button to create a new module from the template
        self.create_module_button = QPushButton(
            get_icon('fa5s.plus-square', color_key='success'),
            _("create_new_module"))
        self.create_module_button.clicked.connect(self.create_new_module)
        layout.addWidget(self.create_module_button)

        # Text browser to display the guide
        self.text_browser = QTextBrowser()
        layout.addWidget(self.text_browser)

        self.load_guide()

    def load_guide(self):
        try:
            with open('docs/development_guide.md', 'r', encoding='utf-8') as f:
                content = f.read()
            self.text_browser.setMarkdown(content)
        except FileNotFoundError:
            self.text_browser.setText(_("dev_guide_not_found"))

    def create_new_module(self):
        module_name, ok = QInputDialog.getText(self, _("create_new_module"),
                                               _("enter_module_name"))
        if ok and module_name:
            try:
                # Sanitize module name to be a valid directory name
                safe_module_name = "".join(c for c in module_name
                                           if c.isalnum() or c in ('_', '-'))
                safe_module_name = safe_module_name.rstrip()
                if not safe_module_name:
                    QMessageBox.warning(self, _("invalid_name"),
                                        _("module_name_invalid_chars"))
                    return

                src_dir = 'modules/template'
                dest_dir = f'modules/{safe_module_name}'

                if os.path.exists(dest_dir):
                    QMessageBox.warning(
                        self, _("module_exists"),
                        _("module_already_exists").format(
                            name=safe_module_name))
                    return

                # Copy the template directory
                shutil.copytree(src_dir, dest_dir)

                # Rename the files
                py_path = os.path.join(dest_dir, 'template_template.py')
                new_py_path = os.path.join(dest_dir,
                                           f'{safe_module_name}_template.py')
                os.rename(py_path, new_py_path)

                json_path = os.path.join(dest_dir, 'template_template.json')
                new_json_path = os.path.join(
                    dest_dir, f'{safe_module_name}_template.json')
                os.rename(json_path, new_json_path)

                # Update the module_type in the new json file
                with open(new_json_path, 'r+', encoding='utf-8') as f:
                    data = json.load(f)
                    data['module_type'] = safe_module_name
                    data['name'] = module_name
                    f.seek(0)
                    json.dump(data, f, indent=4)
                    f.truncate()

                QMessageBox.information(
                    self, _("success"),
                    _("module_created_successfully").format(
                        name=safe_module_name))
                self.module_manager.discover_modules()  # Refresh modules
            except Exception as e:
                QMessageBox.critical(
                    self, _("error"),
                    _("module_creation_failed").format(error=e))


class T4TMainWindow(QMainWindow):
    """Main window for the T4T Task Management Platform."""

    def __init__(self, scheduler, task_manager, module_manager):
        super().__init__()
        self.setGeometry(100, 100, 1280, 720)
        self.setMinimumSize(1280, 720)

        # Store managers
        self.scheduler = scheduler
        self.task_manager = task_manager
        self.module_manager = module_manager

        # Setup UI
        self.setup_ui()
        self.retranslate_ui()  # Set initial text

        # Status bar timer
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status_bar)
        self.status_timer.start(2000)  # Update every 2 seconds
        self.update_status_bar()

        # Connect to signals for dynamic updates
        language_manager.language_changed.connect(self.retranslate_ui)
        theme_manager.theme_changed.connect(self.on_theme_changed)
        a_signal.task_manager_updated.connect(self.update_status_bar)
        a_signal.execute_in_main_thread.connect(
            self.execute_task_in_main_thread)

        # Start tasks that are marked as enabled in their config
        self.autostart_enabled_tasks()

    def execute_task_in_main_thread(self, task_name: str):
        """
        Executes a task function in the main GUI thread, triggered by a
        signal from a background worker. This is crucial for thread-unsafe
        libraries like pynput on macOS.
        """
        logger.debug(
            f"Main thread received request to execute task: {task_name}")
        task_info = self.task_manager.get_task_info(task_name)
        if not task_info:
            logger.error(
                f"Cannot execute task: '{task_name}' not found in TaskManager."
            )
            return

        # All task-loading and execution now happens safely in the main thread.
        try:
            executable_func = self.task_manager._load_task_executable(
                task_info['script'])
            if not executable_func:
                return

            log_emitter = partial(a_signal.log_message.emit, task_name)
            task_config = task_info.get('config_data', {})

            # Re-create the final callable function within the main thread
            task_callable = partial(executable_func,
                                    config=task_config,
                                    log_emitter=log_emitter,
                                    debug=task_config.get('debug', False),
                                    config_path=task_info['config'])

            # Execute the task
            task_callable()

        except Exception as e:
            logger.error(
                f"An error occurred while executing task '{task_name}'"
                f" in main thread: {e}")

    def autostart_enabled_tasks(self):
        """
        Automatically starts tasks that are marked as 'enabled' in their
        configuration file.
        """
        for task_name in self.task_manager.get_task_list():
            task_config = self.task_manager.get_task_config(task_name)
            if task_config and task_config.get('enabled', False):
                self.task_manager.start_task(task_name, self.scheduler)

    def on_theme_changed(self, stylesheet):
        """
        Slot to handle theme changes.
        The stylesheet is already applied globally, but this slot can be
        used for any component-specific updates if needed in the future.
        """
        logger.info(f"Theme changed to {theme_manager.current_theme_name}.")
        set_icon_theme(theme_manager.current_theme_name)
        self.setup_toolbar_icons()
        pass

    def setup_ui(self):
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout()
        main_widget.setLayout(main_layout)

        # Splitter for resizable panels
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # Left panel: Task List with Title
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_panel.setLayout(left_layout)

        self.task_list_title = QLabel()
        self.task_list_title.setObjectName("task_list_title")  # For styling
        left_layout.addWidget(self.task_list_title)

        self.task_list_widget = TaskListWidget(self.task_manager,
                                               self.scheduler, self)
        left_layout.addWidget(self.task_list_widget)

        splitter.addWidget(left_panel)

        self.task_list_widget.itemSelectionChanged.connect(
            self.on_task_selection_changed)

        # Right panel: Task Details (Tabbed view)
        self.detail_area_widget = DetailAreaWidget(self.task_manager)
        splitter.addWidget(self.detail_area_widget)

        # Set initial sizes for splitter (approx 25% left, 75% right)
        splitter.setSizes([int(self.width() * 0.25), int(self.width() * 0.75)])

        # Toolbar at the top
        self.toolbar = QToolBar("Main Toolbar")
        self.addToolBar(self.toolbar)

        # Toolbar actions
        self.add_task_action = QAction("", self)
        self.add_task_action.triggered.connect(self.add_task)

        self.start_action = QAction("", self)
        self.start_action.triggered.connect(self.start_task)
        self.pause_action = QAction("", self)
        self.pause_action.triggered.connect(self.pause_task)
        self.stop_action = QAction("", self)
        self.stop_action.triggered.connect(self.stop_task)

        self.start_all_action = QAction("", self)
        self.start_all_action.triggered.connect(self.start_all_tasks)
        self.pause_all_action = QAction("", self)
        self.pause_all_action.triggered.connect(self.pause_all_tasks)
        self.stop_all_action = QAction("", self)
        self.stop_all_action.triggered.connect(self.stop_all_tasks)

        self.toolbar.addSeparator()

        self.logs_action = QAction("", self)
        self.logs_action.triggered.connect(self.open_logs_tab)
        self.dev_guide_action = QAction("", self)
        self.dev_guide_action.triggered.connect(self.open_dev_guide_tab)
        self.help_action = QAction("", self)
        self.help_action.triggered.connect(self.open_help_tab)

        self.toolbar.addSeparator()

        self.settings_action = QAction("", self)
        self.settings_action.triggered.connect(self.open_settings_tab)

        self.toolbar.addAction(self.add_task_action)
        self.toolbar.addAction(self.start_action)
        self.toolbar.addAction(self.pause_action)
        self.toolbar.addAction(self.stop_action)
        self.toolbar.addAction(self.start_all_action)
        self.toolbar.addAction(self.pause_all_action)
        self.toolbar.addAction(self.stop_all_action)
        self.toolbar.addAction(self.logs_action)
        self.toolbar.addAction(self.dev_guide_action)
        self.toolbar.addAction(self.help_action)
        self.toolbar.addAction(self.settings_action)

        self.setup_toolbar_icons()

        # Initial state for task-specific actions
        self.start_action.setEnabled(False)
        self.pause_action.setEnabled(False)
        self.stop_action.setEnabled(False)

        # Status bar at the bottom
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

    def setup_toolbar_icons(self):
        """Set icons for all toolbar actions."""
        self.add_task_action.setIcon(get_icon('fa5s.plus',
                                              color_key='success'))
        self.start_action.setIcon(get_icon('fa5s.play', color_key='success'))
        self.pause_action.setIcon(get_icon('fa5s.pause', color_key='warning'))
        self.stop_action.setIcon(get_icon('fa5s.stop', color_key='danger'))
        self.start_all_action.setIcon(
            get_icon('fa5s.play-circle', color_key='success'))
        self.pause_all_action.setIcon(
            get_icon('fa5s.pause-circle', color_key='warning'))
        self.stop_all_action.setIcon(
            get_icon('fa5s.stop-circle', color_key='danger'))
        self.logs_action.setIcon(get_icon('fa5s.file-alt', color_key='info'))
        self.dev_guide_action.setIcon(get_icon('fa5s.book', color_key='info'))
        self.help_action.setIcon(
            get_icon('fa5s.question-circle', color_key='info'))
        self.settings_action.setIcon(get_icon('fa5s.cogs'))

        # Status bar at the bottom
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

    def retranslate_ui(self):
        """
        Update all UI text elements with the current language translations.
        """
        self.setWindowTitle(_("app_title"))
        self.toolbar.setWindowTitle(_("main_toolbar_title"))
        self.task_list_title.setText(_("task_list_title"))
        self.add_task_action.setText(_("add_task_action"))
        self.start_action.setText(_("start_action"))
        self.pause_action.setText(_("pause_action"))
        self.start_all_action.setText(_("start_all_action"))
        self.pause_all_action.setText(_("pause_all_action"))
        self.stop_action.setText(_("stop_action"))
        self.stop_all_action.setText(_("stop_all_action"))
        self.logs_action.setText(_("logs_action"))
        self.dev_guide_action.setText(_("dev_guide_title"))
        self.help_action.setText(_("help_action"))
        self.settings_action.setText(_("settings_action"))
        # Also retranslate child widgets if they don't handle it themselves
        self.task_list_widget.retranslate_ui()
        self.detail_area_widget.retranslate_ui()
        self.update_status_bar()

    def closeEvent(self, event):
        # TODO: Save splitter state before closing
        self.scheduler.shutdown()
        event.accept()

    def on_task_selection_changed(self):
        """
        Handles the logic when a task selection changes in the list.
        """
        selected_items = self.task_list_widget.selectedItems()
        if selected_items:
            task_name = selected_items[0].text()
            status = self.task_manager.get_task_status(task_name,
                                                       self.scheduler)
            self.detail_area_widget.update_details(task_name, status)
            self.start_action.setEnabled(True)
            self.pause_action.setEnabled(True)
            self.stop_action.setEnabled(True)
        else:
            self.detail_area_widget.clear_details()
            self.start_action.setEnabled(False)
            self.pause_action.setEnabled(False)
            self.stop_action.setEnabled(False)

    def update_status_bar(self):
        """
        Update the status bar with current task counts and system
        resource usage.
        """
        total_tasks = self.task_manager.get_task_count()
        running_tasks = self.task_manager.get_running_task_count(
            self.scheduler)

        cpu_percent = psutil.cpu_percent()
        memory_info = psutil.virtual_memory()
        memory_percent = memory_info.percent

        status_text = (
            f"{_('status_bar_tasks').format(count=total_tasks)} | "
            f"{_('status_bar_running').format(count=running_tasks)} | "
            f"CPU: {cpu_percent:.1f}% | "
            f"Mem: {memory_percent:.1f}%")
        self.statusBar().showMessage(status_text)

    def add_task(self):
        """
        Opens a new tab to create a new task.
        """
        self.detail_area_widget.open_new_task_tab()

    def start_task(self):
        selected_items = self.task_list_widget.selectedItems()
        if selected_items:
            task_name = selected_items[0].text()
            status = self.task_manager.get_task_status(task_name,
                                                       self.scheduler)
            if status == 'paused':
                success = self.task_manager.resume_task(
                    task_name, self.scheduler)
            else:
                success = self.task_manager.start_task(task_name,
                                                       self.scheduler)
            if success:
                self.on_task_selection_changed()
                logger.info(f"Task {task_name} started or resumed.")
            else:
                logger.error(f"Failed to start or resume task {task_name}.")
        else:
            logger.warning("No task selected to start.")

    def pause_task(self):
        selected_items = self.task_list_widget.selectedItems()
        if selected_items:
            task_name = selected_items[0].text()
            success = self.task_manager.pause_task(task_name, self.scheduler)
            if success:
                self.on_task_selection_changed()
                logger.info(f"Task {task_name} paused.")
            else:
                logger.error(f"Failed to pause task {task_name}.")
        else:
            logger.warning("No task selected to pause.")

    def start_all_tasks(self):
        self.task_manager.start_all_tasks(self.scheduler)
        self.on_task_selection_changed()
        logger.info("Attempted to start all tasks.")

    def pause_all_tasks(self):
        self.task_manager.pause_all_tasks(self.scheduler)
        self.on_task_selection_changed()
        logger.info("Attempted to pause all tasks.")

    def stop_all_tasks(self):
        self.task_manager.stop_all_tasks(self.scheduler)
        self.on_task_selection_changed()
        logger.info("Attempted to stop all tasks.")

    def stop_task(self):
        selected_items = self.task_list_widget.selectedItems()
        if selected_items:
            task_name = selected_items[0].text()
            success = self.task_manager.stop_task(task_name, self.scheduler)
            if success:
                self.on_task_selection_changed()
                logger.info(f"Task {task_name} stopped.")
            else:
                logger.error(f"Failed to stop task {task_name}.")
        else:
            logger.warning("No task selected to stop.")

    def delete_task(self):
        selected_items = self.task_list_widget.selectedItems()
        if selected_items:
            task_name = selected_items[0].text()
            success = self.task_manager.delete_task(task_name)
            if success:
                self.task_list_widget.refresh_tasks()
                self.update_status_bar()
                logger.info(f"Task {task_name} deleted.")
            else:
                logger.error(f"Failed to delete task {task_name}.")
        else:
            logger.warning("No task selected to delete.")

    def open_settings_tab(self):
        """
        Opens the settings widget in a new tab.
        """
        self.detail_area_widget.open_settings_tab()

    def open_logs_tab(self):
        """
        Opens the log viewer widget in a new tab.
        """
        self.detail_area_widget.open_log_viewer_tab()

    def open_help_tab(self):
        """
        Opens the help widget in a new tab.
        """
        self.detail_area_widget.open_help_tab()

    def open_dev_guide_tab(self):
        """
        Opens the development guide widget in a new tab.
        """
        self.detail_area_widget.open_widget_as_tab(
            widget_id="dev_guide_tab",
            widget_class=DevGuideWidget,
            title=_("dev_guide_title"),
            icon_name='fa5s.book',
            constructor_args=[self.module_manager])
