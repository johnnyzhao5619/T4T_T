# utils/icon_manager.py
import qtawesome as qta
from PyQt5.QtGui import QIcon, QColor

# Define icon color schemes for different themes
ICON_COLORS = {
    "light": {
        "default": QColor("#4D4D4D"),
        "primary": QColor("#007ACC"),
        "success": QColor("#2E7D32"),
        "warning": QColor("#FFC107"),
        "error": QColor("#D32F2F"),
        "info": QColor("#0288D1"),
    },
    "dark": {
        "default": QColor("#CCCCCC"),
        "primary": QColor("#0090F1"),
        "success": QColor("#4CAF50"),
        "warning": QColor("#FFEB3B"),
        "error": QColor("#F44336"),
        "info": QColor("#03A9F4"),
    }
}


class IconManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(IconManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, theme_name='light'):
        if not hasattr(self, 'initialized'):
            self.set_theme(theme_name)
            self.initialized = True

    def set_theme(self, theme_name):
        """Sets the color scheme based on the theme name."""
        self.theme_name = theme_name if theme_name in ICON_COLORS else 'light'
        self.colors = ICON_COLORS[self.theme_name]

    def get_icon(self, icon_name, color_key='default', scale_factor=1.0):
        """
        Gets a QIcon from qtawesome.

        :param icon_name: Name of the icon (e.g., 'fa.save', 'fa5s.cog').
        :param color_key: Key for the color from the theme's color scheme.
        :param scale_factor: Scale factor for the icon.
        :return: QIcon object.
        """
        color = self.colors.get(color_key, self.colors['default'])
        return qta.icon(icon_name, color=color, scale_factor=scale_factor)


# Singleton instance
icon_manager = IconManager()


def get_icon(icon_name, color_key='default', scale_factor=1.0):
    """Convenience function to access the singleton instance."""
    return icon_manager.get_icon(icon_name, color_key, scale_factor)


def set_theme(theme_name):
    """Convenience function to set the theme on the singleton instance."""
    icon_manager.set_theme(theme_name)
