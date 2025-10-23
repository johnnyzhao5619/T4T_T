from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout

from utils.i18n import _, language_manager
from view.components.settings_base import SettingsSections


class SettingsDialog(QDialog):
    """
    A dialog for changing application settings, with an improved layout.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(500)
        self._sections = SettingsSections(self,
                                          None,
                                          language_display="code",
                                          export_button_text_key="export_button")
        self.theme_combo = self._sections.theme_combo
        self.language_combo = self._sections.language_combo
        self.module_list_widget = self._sections.module_list_widget
        self.import_module_button = self._sections.import_module_button
        self.init_ui()
        self._sections.initialize()
        self._update_window_title()
        language_manager.language_changed.connect(self._update_window_title)

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        self._sections.add_to_layout(main_layout)

        # --- Dialog Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.Ok
                                      | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def retranslate_ui(self):
        self._sections.retranslate()
        self._update_window_title()

    def _update_window_title(self):
        self.setWindowTitle(_("settings_dialog_title"))
        self.theme_label.setText(_("theme_label"))
        self.language_label.setText(_("language_label"))
        self.import_module_button.setText(_("import_module_button"))
        self.findChild(QGroupBox, "appearance_language_group_title").setTitle(
            _("appearance_language_group_title"))
        self.findChild(QGroupBox, "module_management_group_title").setTitle(
            _("module_management_group_title"))
        self.populate_modules()

    def _disconnect_signals(self):
        signal_slot_pairs = [
            (language_manager.language_changed, self.retranslate_ui),
            (global_signals.modules_updated, self.populate_modules),
        ]
        for signal, slot in signal_slot_pairs:
            try:
                signal.disconnect(slot)
            except TypeError:
                pass

    def closeEvent(self, event):
        self._disconnect_signals()
        super().closeEvent(event)
