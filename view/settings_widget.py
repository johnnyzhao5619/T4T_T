from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from utils.config import ConfigManager
from utils.i18n import _
from view.components.settings_base import SettingsSections


class SettingsWidget(QWidget):
    """
    A widget for changing application settings, designed to be embedded
    in a tab.
    """

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self._sections = SettingsSections(self,
                                          config_manager,
                                          language_display="name",
                                          export_button_text_key=None)
        self.theme_combo = self._sections.theme_combo
        self.language_combo = self._sections.language_combo
        self.module_list_widget = self._sections.module_list_widget
        self.import_module_button = self._sections.import_module_button
        self.init_ui()
        self._sections.initialize()
        # Set an object name for styling
        self.setObjectName("SettingsWidget")

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setObjectName("SettingsScrollArea")

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(20, 20, 20, 20)
        container_layout.setSpacing(15)
        container_layout.setAlignment(Qt.AlignTop)

        self._sections.add_to_layout(container_layout)

        scroll_area.setWidget(container)
        main_layout.addWidget(scroll_area)
    def __del__(self):
        if hasattr(self, "_sections"):
            self._sections.cleanup()
