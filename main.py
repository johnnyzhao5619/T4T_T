import sys
import os
import qtawesome
from PyQt5.QtWidgets import QApplication
from core.scheduler import SchedulerManager
from core.task_manager import TaskManager
from core.module_manager import ModuleManager
from view.main_window import T4TMainWindow
from utils.config import ConfigManager
from utils.theme import switch_theme
from utils.i18n import switch_language
from utils.logger import LoggerManager, setup_exception_hook, get_logger


def main():
    """Entry point for the T4T application."""
    # --- Setup Logging and Exception Handling ---
    # Initialize the logger manager to configure logging.
    LoggerManager()
    # Set up the global exception hook to catch unhandled exceptions.
    setup_exception_hook()

    logger = get_logger(__name__)
    logger.info("Application starting...")

    global app
    app = QApplication(sys.argv)

    # Initialize icon font
    qtawesome.icon('fa5s.star', color='black')

    # --- Path Setup ---
    # Get the absolute path to the directory of the current script (main.py)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # These paths are now absolute, ensuring they work regardless of CWD
    CONFIG_DIR = os.path.join(script_dir, 'config')
    MODULES_DIR = os.path.join(script_dir, 'modules')
    TASKS_DIR = os.path.join(script_dir, 'tasks')

    # Initialize core components
    config_manager = ConfigManager(config_dir=CONFIG_DIR)

    scheduler = SchedulerManager(config_manager)
    task_manager = TaskManager(tasks_dir=TASKS_DIR, modules_dir=MODULES_DIR)
    module_manager = ModuleManager(module_path=MODULES_DIR)

    # Load initial theme and language using the new managers
    theme_name = config_manager.get('general', 'theme', fallback='dark')
    lang_code = config_manager.get('general', 'language', fallback='en')

    # Apply initial theme
    # The switch_theme function now handles loading and applying
    switch_theme(theme_name)

    # Load initial language
    # The switch_language function handles loading and triggers the signal
    switch_language(lang_code)

    # Initialize main window
    # The window no longer needs theme_data and lang_data in its constructor
    window = T4TMainWindow(scheduler, task_manager, module_manager)

    # The theme and language are now managed globally.
    # The main window and its children will connect to the managers' signals
    # to handle dynamic updates.
    window.show()

    # Start the scheduler after the main window is shown
    scheduler.start()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
