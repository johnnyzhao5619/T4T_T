from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox,
                             QDialogButtonBox, QLabel, QListWidget,
                             QPushButton, QHBoxLayout, QFileDialog,
                             QMessageBox, QListWidgetItem, QWidget, QGroupBox)
from utils.theme import theme_manager, switch_theme
from utils.i18n import language_manager, switch_language, _
from core.module_manager import module_manager
from utils.signals import global_signals
from utils.icon_manager import get_icon


class SettingsDialog(QDialog):
    """
    A dialog for changing application settings, with an improved layout.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(500)
        self.init_ui()
        self.populate_and_connect()

    def init_ui(self):
        self.setWindowTitle(_("settings_dialog_title"))
        main_layout = QVBoxLayout(self)

        # --- Appearance and Language Group ---
        appearance_group = QGroupBox(_("appearance_language_group_title"))
        form_layout = QFormLayout(appearance_group)

        self.theme_label = QLabel()
        self.theme_combo = QComboBox()
        form_layout.addRow(self.theme_label, self.theme_combo)

        self.language_label = QLabel()
        self.language_combo = QComboBox()
        form_layout.addRow(self.language_label, self.language_combo)

        main_layout.addWidget(appearance_group)

        # --- Module Management Group ---
        module_group = QGroupBox(_("module_management_group_title"))
        module_layout = QVBoxLayout(module_group)

        self.module_list_widget = QListWidget()
        self.module_list_widget.setObjectName("ModuleList")
        module_layout.addWidget(self.module_list_widget)

        import_button_layout = QHBoxLayout()
        self.import_module_button = QPushButton(get_icon("fa5s.plus-circle"),
                                                "")
        import_button_layout.addWidget(self.import_module_button)
        import_button_layout.addStretch()
        module_layout.addLayout(import_button_layout)

        main_layout.addWidget(module_group)

        # --- Dialog Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.Ok
                                      | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def populate_and_connect(self):
        self.populate_themes()
        self.populate_languages()
        self.populate_modules()
        self.retranslate_ui()

        self.theme_combo.currentTextChanged.connect(self.on_theme_changed)
        self.language_combo.currentTextChanged.connect(
            self.on_language_changed)
        self.import_module_button.clicked.connect(self.import_module)

        language_manager.language_changed.connect(self.retranslate_ui)
        global_signals.modules_updated.connect(self.populate_modules)

    def populate_themes(self):
        available_themes = theme_manager.get_available_themes()
        current_theme = theme_manager.current_theme_name
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        self.theme_combo.addItems(available_themes)
        if current_theme in available_themes:
            self.theme_combo.setCurrentText(current_theme)
        self.theme_combo.blockSignals(False)

    def populate_languages(self):
        available_languages = language_manager.get_available_languages()
        current_language = language_manager.current_language
        self.language_combo.blockSignals(True)
        self.language_combo.clear()
        self.language_combo.addItems(available_languages)
        if current_language in available_languages:
            self.language_combo.setCurrentText(current_language)
        self.language_combo.blockSignals(False)

    def on_theme_changed(self, theme_name):
        if theme_name:
            switch_theme(theme_name)

    def on_language_changed(self, language_code):
        if language_code:
            switch_language(language_code)

    def populate_modules(self):
        self.module_list_widget.clear()
        module_names = module_manager.get_module_names()
        for name in module_names:
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(5, 2, 5, 2)

            label = QLabel(name)
            export_button = QPushButton(get_icon("fa5s.download"),
                                        _("export_button"))
            export_button.setToolTip(_("export_module_tooltip"))
            export_button.clicked.connect(
                lambda _, n=name: self.export_module(n))

            item_layout.addWidget(label)
            item_layout.addStretch()
            item_layout.addWidget(export_button)

            list_item = QListWidgetItem(self.module_list_widget)
            list_item.setSizeHint(item_widget.sizeHint())
            self.module_list_widget.addItem(list_item)
            self.module_list_widget.setItemWidget(list_item, item_widget)

    def import_module(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, _("import_module_dialog_title"), "", _("zip_files_filter"))
        if file_path:
            if module_manager.import_module(file_path):
                QMessageBox.information(self, _("import_success_title"),
                                        _("import_success_message"))
            else:
                QMessageBox.warning(self, _("import_error_title"),
                                    _("import_error_message"))

    def export_module(self, module_name):
        file_path, _ = QFileDialog.getSaveFileName(
            self, _("export_module_dialog_title"), f"{module_name}.zip",
            _("zip_files_filter"))
        if file_path:
            if module_manager.export_module(module_name, file_path):
                QMessageBox.information(self, _("export_success_title"),
                                        _("export_success_message"))
            else:
                QMessageBox.warning(self, _("export_error_title"),
                                    _("export_error_message"))

    def retranslate_ui(self):
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
