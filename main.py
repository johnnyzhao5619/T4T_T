import sys
import os
import qtawesome
from PyQt5.QtWidgets import QApplication
from core.scheduler import SchedulerManager
from core.task_manager import TaskManager
from core.module_manager import ModuleManager
from core.service_manager import service_manager
from services.embedded_mqtt_broker import EmbeddedMQTTBroker
from view.main_window import T4TMainWindow
from utils.config import ConfigManager
from utils.message_bus import message_bus_manager
from utils.theme import switch_theme
from utils.i18n import switch_language, set_language_dir
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
    LANGUAGE_DIR = os.path.join(script_dir, 'i18n')

    # Initialize core components
    config_manager = ConfigManager(config_dir=CONFIG_DIR)

    # Ensure message bus and embedded broker share the absolute config path
    message_bus_manager.configure(config_manager=config_manager)
    service_manager.register_service(
        'mqtt_broker',
        EmbeddedMQTTBroker(config_manager=config_manager))

    module_manager = ModuleManager()
    module_manager.set_module_path(MODULES_DIR)
    set_language_dir(LANGUAGE_DIR)

    scheduler = SchedulerManager()
    task_manager = TaskManager(scheduler_manager=scheduler,
                               tasks_dir=TASKS_DIR,
                               modules_dir=MODULES_DIR)

    # Load initial theme and language using the new managers
    theme_name = config_manager.get('appearance', 'theme', fallback='dark')
    lang_code = config_manager.get('appearance', 'language', fallback='en')

    # Apply initial theme
    # The switch_theme function now handles loading and applying
    switch_theme(theme_name)

    # Load initial language
    # The switch_language function handles loading and triggers the signal
    switch_language(lang_code)

    # Initialize main window
    # The window no longer needs theme_data and lang_data in its constructor
    window = T4TMainWindow(scheduler, task_manager, module_manager,
                           config_manager)

    # The theme and language are now managed globally.
    # The main window and its children will connect to the managers' signals
    # to handle dynamic updates.
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
