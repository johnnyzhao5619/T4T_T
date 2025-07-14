import json
import logging
import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QMessageBox, QPlainTextEdit)
from PyQt5.QtCore import QRegExp
from PyQt5.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from utils.signals import global_signals
from utils.theme import theme_manager

logger = logging.getLogger(__name__)


class JsonSyntaxHighlighter(QSyntaxHighlighter):
    """
    A syntax highlighter for JSON data that uses colors from the current theme.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.highlighting_rules = []
        self.load_theme_colors()

    def load_theme_colors(self):
        theme_name = theme_manager.current_theme_name
        theme_file = os.path.join(theme_manager.theme_dir,
                                  f'{theme_name}.json')

        # Default VS Code dark theme colors as fallback
        colors = {
            "key": "#9CDCFE",
            "string": "#CE9178",
            "number": "#B5CEA8",
            "boolean": "#569CD6",
            "null": "#569CD6"
        }

        try:
            with open(theme_file, 'r') as f:
                theme_data = json.load(f)
                # Override defaults with colors from the "editor"
                # section of the theme file
                if "editor" in theme_data and "syntax" in theme_data["editor"]:
                    colors.update(theme_data["editor"]["syntax"])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(
                "Could not load theme colors from %s: %s. Using defaults.",
                theme_file, e)

        self.highlighting_rules = []

        # Rule for keys
        key_format = QTextCharFormat()
        key_format.setForeground(QColor(colors['key']))
        self.highlighting_rules.append((QRegExp(r'"[^"]*"\s*:'), key_format))

        # Rule for string values
        string_format = QTextCharFormat()
        string_format.setForeground(QColor(colors['string']))
        self.highlighting_rules.append(
            (QRegExp(r':\s*"(?:\\.|[^"\\])*"'), string_format))

        # Rule for numbers
        number_format = QTextCharFormat()
        number_format.setForeground(QColor(colors['number']))
        self.highlighting_rules.append(
            (QRegExp(r'\b-?\d+(\.\d+)?([eE][+-]?\d+)?\b'), number_format))

        # Rule for booleans
        boolean_format = QTextCharFormat()
        boolean_format.setForeground(QColor(colors['boolean']))
        boolean_format.setFontWeight(QFont.Bold)
        self.highlighting_rules.append(
            (QRegExp(r'\b(true|false)\b'), boolean_format))

        # Rule for null
        null_format = QTextCharFormat()
        null_format.setForeground(QColor(colors['null']))
        null_format.setFontWeight(QFont.Bold)
        self.highlighting_rules.append((QRegExp(r'\bnull\b'), null_format))

    def highlightBlock(self, text):
        for pattern, format_rule in self.highlighting_rules:
            expression = QRegExp(pattern)
            index = expression.indexIn(text)
            while index >= 0:
                length = expression.matchedLength()
                self.setFormat(index, length, format_rule)
                index = expression.indexIn(text, index + length)
        self.setCurrentBlockState(0)

    def on_theme_changed(self):
        self.load_theme_colors()
        self.rehighlight()


class JsonConfigEditorWidget(QWidget):
    """
    A widget that provides a themed text editor for viewing
    and editing JSON configs.
    """

    def __init__(self, task_name, task_manager, parent=None):
        super().__init__(parent)
        self.task_name = task_name
        self.task_manager = task_manager

        self.init_ui()
        self.load_config()
        global_signals.theme_changed.connect(self.on_theme_changed)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Courier New", 10))
        self.highlighter = JsonSyntaxHighlighter(self.editor.document())

        self.update_editor_style()
        layout.addWidget(self.editor)

    def update_editor_style(self):
        theme_name = theme_manager.current_theme_name
        theme_file = os.path.join(theme_manager.theme_dir,
                                  f'{theme_name}.json')

        # Default VS Code dark theme colors
        bg_color = "#1E1E1E"
        fg_color = "#D4D4D4"

        try:
            with open(theme_file, 'r') as f:
                theme_data = json.load(f)
                if "editor" in theme_data:
                    bg_color = theme_data["editor"].get("background", bg_color)
                    fg_color = theme_data["editor"].get("foreground", fg_color)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(
                "Could not load editor styles from %s: %s. Using defaults.",
                theme_file, e)

        border_color = theme_data.get("colors", {}).get(
            "editorWidget.border", "#3c3c3c")
        self.editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {bg_color};
                color: {fg_color};
                border: 1px solid {border_color};
                font-family: 'Courier New', 'Lucida Console', 
                             'Monaco', monospace;
                font-size: 10pt;
            }}
        """)

    def load_config(self):
        config_data = self.task_manager.get_task_config(self.task_name)
        self.set_config(config_data)

    def set_config(self, config_data):
        if config_data is not None:
            try:
                json_string = json.dumps(config_data, indent=4, sort_keys=True)
                self.editor.setPlainText(json_string)
            except Exception as e:
                logger.error(
                    f"Failed to serialize config for '{self.task_name}': {e}")
                self.editor.setPlainText(f"// Error loading config: {e}")
        else:
            logger.warning(
                f"No configuration found for task '{self.task_name}'.")
            self.editor.setPlainText(
                f"// No configuration file found for '{self.task_name}'.")

    def get_config(self):
        json_string = self.editor.toPlainText()
        try:
            return json.loads(json_string)
        except json.JSONDecodeError as e:
            QMessageBox.critical(
                self, "Invalid JSON",
                f"The content is not valid JSON and cannot be saved.\n"
                f"Please correct the errors before switching tabs or saving."
                f"\n\nError: {e}")
            logger.error(
                f"Invalid JSON format for task '{self.task_name}': {e}")
            return None  # Return None to indicate failure

    def on_theme_changed(self):
        self.update_editor_style()
        self.highlighter.on_theme_changed()

    def __del__(self):
        # Disconnect signal to prevent issues during shutdown
        try:
            global_signals.theme_changed.disconnect(self.on_theme_changed)
        except TypeError:
            pass  # Signal already disconnected
