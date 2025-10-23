from functools import partial
from typing import Optional

from PyQt5.QtCore import QObject, Qt
from PyQt5.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QGroupBox,
                             QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QMessageBox, QPushButton, QVBoxLayout, QWidget)

from core.module_manager import module_manager
from utils.icon_manager import get_icon
from utils.i18n import _, language_manager, switch_language
from utils.signals import global_signals, SignalConnectionManagerMixin
from utils.theme import switch_theme, theme_manager


class SettingsSections(SignalConnectionManagerMixin, QObject):
    """Shared UI logic for settings widgets and dialogs."""

    def __init__(self,
                 owner: QObject,
                 config_manager: Optional[object] = None,
                 *,
                 language_display: str = "name",
                 export_button_text_key: Optional[str] = None):
        super().__init__(owner)
        self._owner = owner
        self._config_manager = config_manager
        self._language_display = language_display
        self._export_button_text_key = export_button_text_key
        self._initialized = False

        self.appearance_group = QGroupBox(parent=owner)
        self.appearance_group.setObjectName("appearance_language_group_title")
        appearance_layout = QFormLayout(self.appearance_group)
        appearance_layout.setLabelAlignment(Qt.AlignLeft)
        appearance_layout.setFormAlignment(Qt.AlignLeft)
        appearance_layout.setFieldGrowthPolicy(
            QFormLayout.AllNonFixedFieldsGrow)
        appearance_layout.setSpacing(10)

        self.theme_label = QLabel(parent=owner)
        self.theme_combo = QComboBox(parent=owner)
        appearance_layout.addRow(self.theme_label, self.theme_combo)

        self.language_label = QLabel(parent=owner)
        self.language_combo = QComboBox(parent=owner)
        appearance_layout.addRow(self.language_label, self.language_combo)

        self.module_group = QGroupBox(parent=owner)
        self.module_group.setObjectName("module_management_group_title")
        module_layout = QVBoxLayout(self.module_group)

        self.module_list_widget = QListWidget(parent=owner)
        self.module_list_widget.setObjectName("ModuleList")
        module_layout.addWidget(self.module_list_widget)

        import_button_layout = QHBoxLayout()
        self.import_module_button = QPushButton(get_icon("fa5s.plus-circle"),
                                                "", parent=owner)
        import_button_layout.addWidget(self.import_module_button)
        import_button_layout.addStretch()
        module_layout.addLayout(import_button_layout)

    def add_to_layout(self, layout: QVBoxLayout) -> None:
        """Add the settings sections to the provided layout."""
        layout.addWidget(self.appearance_group)
        layout.addWidget(self.module_group)

    def initialize(self) -> None:
        if self._initialized:
            return

        self.populate_themes()
        self.retranslate()

        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        self.language_combo.currentTextChanged.connect(
            self._on_language_changed)
        self.import_module_button.clicked.connect(self.import_module)
        self._register_signal(language_manager.language_changed,
                              self.retranslate)
        self._register_signal(global_signals.modules_updated,
                              self.populate_modules)

        self._initialized = True

    def populate_themes(self) -> None:
        available_themes = theme_manager.get_available_themes()
        current_theme = theme_manager.current_theme_name

        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        self.theme_combo.addItems(available_themes)
        if current_theme in available_themes:
            self.theme_combo.setCurrentText(current_theme)
        self.theme_combo.blockSignals(False)

    def populate_languages(self) -> None:
        available_languages = language_manager.get_available_languages()
        current_code = language_manager.current_language

        self.language_combo.blockSignals(True)
        self.language_combo.clear()

        if self._language_display == "code":
            for code in available_languages.keys():
                self.language_combo.addItem(code)
            self.language_combo.setCurrentText(current_code)
        else:
            names = sorted(available_languages.values())
            for name in names:
                self.language_combo.addItem(name)
            current_name = available_languages.get(current_code, current_code)
            self.language_combo.setCurrentText(current_name)

        self.language_combo.blockSignals(False)

    def populate_modules(self) -> None:
        self.module_list_widget.clear()
        module_names = module_manager.get_module_names()

        for name in module_names:
            item_widget = QWidget(self._owner)
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(5, 2, 5, 2)

            label = QLabel(name, parent=item_widget)
            export_button = QPushButton(get_icon("fa5s.download"), "",
                                        parent=item_widget)
            if self._export_button_text_key:
                export_button.setText(_(self._export_button_text_key))
            export_button.setToolTip(_("export_module_tooltip"))
            export_button.clicked.connect(partial(self.export_module, name))

            item_layout.addWidget(label)
            item_layout.addStretch()
            item_layout.addWidget(export_button)

            list_item = QListWidgetItem(self.module_list_widget)
            list_item.setSizeHint(item_widget.sizeHint())
            self.module_list_widget.addItem(list_item)
            self.module_list_widget.setItemWidget(list_item, item_widget)

    def import_module(self) -> None:
        file_path, _unused = QFileDialog.getOpenFileName(
            self._owner, _("import_module_dialog_title"), "",
            _("zip_files_filter"))
        if file_path:
            if module_manager.import_module(file_path):
                QMessageBox.information(self._owner,
                                        _("import_success_title"),
                                        _("import_success_message"))
            else:
                QMessageBox.warning(self._owner, _("import_error_title"),
                                    _("import_error_message"))

    def export_module(self, module_name: str) -> None:
        file_path, _unused = QFileDialog.getSaveFileName(
            self._owner, _("export_module_dialog_title"),
            f"{module_name}.zip", _("zip_files_filter"))
        if file_path:
            if module_manager.export_module(module_name, file_path):
                QMessageBox.information(self._owner,
                                        _("export_success_title"),
                                        _("export_success_message"))
            else:
                QMessageBox.warning(self._owner, _("export_error_title"),
                                    _("export_error_message"))

    def retranslate(self) -> None:
        self.appearance_group.setTitle(_("appearance_language_group_title"))
        self.module_group.setTitle(_("module_management_group_title"))
        self.theme_label.setText(_("theme_label"))
        self.language_label.setText(_("language_label"))
        self.import_module_button.setText(_("import_module_button"))

        self.populate_languages()
        self.populate_modules()

    def cleanup(self) -> None:
        self._disconnect_tracked_signals()

    def _on_theme_changed(self, theme_name: str) -> None:
        if not theme_name:
            return
        switch_theme(theme_name)
        if self._config_manager is not None:
            self._config_manager.set('appearance', 'theme', theme_name)

    def _on_language_changed(self, value: str) -> None:
        if not value:
            return

        if self._language_display == "code":
            language_code = value
        else:
            language_code = language_manager.get_language_code(value)

        if not language_code:
            return

        switch_language(language_code)
        if self._config_manager is not None:
            self._config_manager.set('appearance', 'language', language_code)
