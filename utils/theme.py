import os
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication


class ThemeManager(QObject):
    """
    Manages application themes by scanning for .qss files,
    loading them, and applying them to the application.
    Notifies UI elements of changes.
    """
    theme_changed = pyqtSignal(str)

    def __init__(self, theme_dir='themes'):
        super().__init__()
        self.theme_dir = theme_dir
        self.current_theme_name = 'light'  # Default theme
        self.current_stylesheet = ""
        self.load_stylesheet(
            self.current_theme_name)  # Load default theme at startup

    def get_available_themes(self):
        """
        Scans the theme directory and returns a list of available theme names.
        """
        themes = []
        if os.path.isdir(self.theme_dir):
            for file_name in os.listdir(self.theme_dir):
                if file_name.endswith('.qss'):
                    themes.append(os.path.splitext(file_name)[0])
        return sorted(themes)

    def load_stylesheet(self, theme_name):
        """
        Loads a QSS stylesheet from a file and stores it.
        """
        file_path = os.path.join(self.theme_dir, f'{theme_name}.qss')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.current_stylesheet = f.read()
            self.current_theme_name = theme_name
            print(f"Successfully loaded stylesheet for theme: {theme_name}")
            return True
        except FileNotFoundError:
            print(f"Error: Stylesheet file not found at {file_path}")
            self.current_stylesheet = ""  # Reset to empty stylesheet on error
            return False

    def apply_theme(self, theme_name):
        """
        Loads and applies a theme to the entire application.
        """
        if self.load_stylesheet(theme_name):
            app = QApplication.instance()
            if app:
                app.setStyleSheet(self.current_stylesheet)
                self.theme_changed.emit(self.current_stylesheet)


# --- Global Instance ---
theme_manager = ThemeManager()


def switch_theme(theme_name):
    """
    Global function to switch the application theme.
    """
    theme_manager.apply_theme(theme_name)
