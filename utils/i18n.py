import json
import os
from typing import Union
from PyQt5.QtCore import QObject, pyqtSignal


class LanguageManager(QObject):
    """
    Manages application language, loads translations, and notifies
    UI elements of changes.
    """
    language_changed = pyqtSignal()

    def __init__(self, language_dir='i18n'):
        super().__init__()
        self.language_dir = language_dir
        self.translations = {}
        self.current_language = 'en'  # Default language

    def get_available_languages(self):
        """
        Scans the language directory and returns a dictionary mapping language
        codes to their full names.
        """
        languages = {}
        if os.path.isdir(self.language_dir):
            for file_name in os.listdir(self.language_dir):
                if file_name.endswith('.json'):
                    code = os.path.splitext(file_name)[0]
                    file_path = os.path.join(self.language_dir, file_name)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            # Use the 'language' key for the name
                            languages[code] = data.get('language', code)
                    except (json.JSONDecodeError, IOError):
                        # In case of error, just use the code
                        languages[code] = code
        return languages

    def load_language(self, language_code):
        """
        Loads a specific language file and updates the translations.
        Emits language_changed signal upon successful loading.
        """
        file_path = os.path.join(self.language_dir, f'{language_code}.json')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.translations = json.load(f)
            self.current_language = language_code
            print(f"Successfully loaded language: {language_code}")
            self.language_changed.emit()
            return True
        except FileNotFoundError:
            print(f"Error: Language file not found at {file_path}")
            return False
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from {file_path}")
            return False

    def translate(self, key):
        """
        Translates a given key using the loaded language file.
        Falls back to the key itself if translation is not found.
        """
        return self.translations.get(key, key)

    def get_language_code(self, language_name: str) -> Union[str, None]:
        """
        Finds the language code corresponding to a given language name.
        """
        available_languages = self.get_available_languages()
        for code, name in available_languages.items():
            if name == language_name:
                return code
        return None


# --- Global Instance and Function ---
# This makes the language manager a singleton and easily accessible.
language_manager = LanguageManager()


def _(key):
    """
    Global translation function for easy access in the UI code.
    Example: self.setWindowTitle(_("app_title"))
    """
    return language_manager.translate(key)


def switch_language(language_code):
    """
    Global function to switch the application language.
    """
    language_manager.load_language(language_code)


def translate_service_state(state) -> str:
    """
    Translates a ServiceState enum member into a human-readable,
    localized string.
    """
    key = f"service_status_{state.name.lower()}"
    return _(key)
