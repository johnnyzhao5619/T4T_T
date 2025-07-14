from PyQt5.QtWidgets import QFrame


class Separator(QFrame):
    """A horizontal separator line."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)
        self.setStyleSheet("margin-top: 10px; margin-bottom: 5px;")
