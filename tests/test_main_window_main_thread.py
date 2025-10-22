import logging
import sys
import threading
import types
from pathlib import Path

class _DummySignal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args, **kwargs):
        for slot in list(self._slots):
            slot(*args, **kwargs)

    def disconnect(self, slot):
        self._slots = [s for s in self._slots if s != slot]


# Stub minimal PyQt5 modules required for importing the main window module
PyQt5 = types.ModuleType("PyQt5")
QtCore = types.ModuleType("PyQt5.QtCore")
QtWidgets = types.ModuleType("PyQt5.QtWidgets")
QtGui = types.ModuleType("PyQt5.QtGui")
qtawesome = types.ModuleType("qtawesome")
qtawesome.icon = lambda *args, **kwargs: None
markdown = types.ModuleType("markdown")
markdown.markdown = lambda text, *args, **kwargs: text
pyqtgraph = types.ModuleType("pyqtgraph")


class _DummyPlotData:
    def setData(self, *args, **kwargs):
        return None


class _DummyPlotWidget:
    def __init__(self, *args, **kwargs):
        pass

    def setTitle(self, *args, **kwargs):
        return None

    def setLabel(self, *args, **kwargs):
        return None

    def showGrid(self, *args, **kwargs):
        return None

    def setYRange(self, *args, **kwargs):
        return None

    def plot(self, *args, **kwargs):
        return _DummyPlotData()


pyqtgraph.PlotWidget = _DummyPlotWidget
pyqtgraph.mkPen = lambda *args, **kwargs: None
PyQt5.QtCore = QtCore
PyQt5.QtWidgets = QtWidgets
PyQt5.QtGui = QtGui
PyQt5.uic = types.ModuleType("PyQt5.uic")
sys.modules.setdefault("sip", types.ModuleType("sip"))


class _BaseWidget:
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        def _method(*_args, **_kwargs):
            return None

        return _method


class _BaseAction:
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        def _method(*_args, **_kwargs):
            return None

        return _method


class _BaseLayout:
    def __init__(self, *args, **kwargs):
        pass

    def addWidget(self, *args, **kwargs):
        return None

    def setContentsMargins(self, *args, **kwargs):
        return None


class _BaseMenu(_BaseWidget):
    pass


class _BaseTreeItem:
    def __init__(self, *args, **kwargs):
        pass

    def setText(self, *args, **kwargs):
        return None

    def setIcon(self, *args, **kwargs):
        return None


QtCore.QObject = object
QtCore.pyqtSignal = lambda *args, **kwargs: _DummySignal()
QtCore.Qt = types.SimpleNamespace(Horizontal=1,
                                  CustomContextMenu=2,
                                  ToolButtonTextBesideIcon=3)
QtCore.QTimer = type("QTimer", (), {
    "__init__": lambda self, *args, **kwargs: None,
    "timeout": _DummySignal(),
    "start": lambda self, *args, **kwargs: None,
})
QtCore.QSize = type("QSize", (), {"__init__": lambda self, *args, **kwargs: None})
QtCore.QSettings = type("QSettings", (), {"__init__": lambda self, *args, **kwargs: None})
QtCore.__getattr__ = lambda name: type(name, (), {})

QtWidgets.QMainWindow = type("QMainWindow", (object,), {})
QtWidgets.QWidget = type("QWidget", (_BaseWidget,), {})
QtWidgets.QHBoxLayout = type("QHBoxLayout", (_BaseLayout,), {})
QtWidgets.QVBoxLayout = type("QVBoxLayout", (_BaseLayout,), {})
QtWidgets.QLabel = type("QLabel", (_BaseWidget,), {})
QtWidgets.QStatusBar = type("QStatusBar", (_BaseWidget,), {})
QtWidgets.QToolBar = type("QToolBar", (_BaseWidget,), {})
QtWidgets.QAction = type("QAction", (_BaseAction,), {})
QtWidgets.QSplitter = type("QSplitter", (_BaseWidget,), {})
QtWidgets.QMessageBox = type("QMessageBox", (_BaseWidget,), {})
QtWidgets.QInputDialog = type("QInputDialog", (_BaseWidget,), {})
QtWidgets.QTextBrowser = type("QTextBrowser", (_BaseWidget,), {})
QtWidgets.QPushButton = type("QPushButton", (_BaseWidget,), {})
QtWidgets.QToolButton = type("QToolButton", (_BaseWidget,), {})
QtWidgets.QMenu = type("QMenu", (_BaseMenu,), {})
QtWidgets.QTreeWidget = type("QTreeWidget", (_BaseWidget,), {})
QtWidgets.QTreeWidgetItem = type("QTreeWidgetItem", (_BaseTreeItem,), {})
QtWidgets.QHeaderView = type("QHeaderView", (_BaseWidget,), {})
QtWidgets.QLineEdit = type("QLineEdit", (_BaseWidget,), {})
QtWidgets.__getattr__ = lambda name: type(name, (_BaseWidget,), {})

QtGui.QColor = type("QColor", (), {
    "__init__": lambda self, *args, **kwargs: None
})
QtGui.__getattr__ = lambda name: type(name, (), {})

sys.modules.setdefault("PyQt5", PyQt5)
sys.modules.setdefault("PyQt5.QtCore", QtCore)
sys.modules.setdefault("PyQt5.QtWidgets", QtWidgets)
sys.modules.setdefault("PyQt5.QtGui", QtGui)
sys.modules.setdefault("qtawesome", qtawesome)
sys.modules.setdefault("markdown", markdown)
sys.modules.setdefault("pyqtgraph", pyqtgraph)

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.context import TaskContext
from view.main_window import T4TMainWindow


def test_execute_task_in_main_thread_uses_task_context(monkeypatch):
    from view import main_window

    captured_logs = []
    executed = {}

    class DummyGlobalSignals:
        def __init__(self):
            self.execute_in_main_thread = _DummySignal()
            self.log_message = _DummySignal()

    dummy_signals = DummyGlobalSignals()
    dummy_signals.log_message.connect(
        lambda task, message: captured_logs.append((task, message)))

    monkeypatch.setattr(main_window, "global_signals", dummy_signals)

    class DummyStateManager:
        def __init__(self):
            self._data = {}

        def get_state(self, task_name, key, default=None):
            return self._data.get((task_name, key), default)

        def update_state(self, task_name, key, value):
            self._data[(task_name, key)] = value

    def run_function(context, inputs):
        executed["thread"] = threading.current_thread().name
        executed["context"] = context
        executed["inputs"] = dict(inputs)
        executed["config"] = dict(context.config)
        context.log_emitter("main-thread-log")

    class DummyTaskManager:
        def __init__(self):
            self.state_manager = DummyStateManager()
            self._task_info = {
                "TestTask": {
                    "script": "dummy",
                    "config_data": {"foo": "bar"},
                    "path": "/tmp/test",
                    "logger": logging.getLogger("task.TestTask"),
                }
            }

        def get_task_info(self, task_name):
            return self._task_info.get(task_name)

        def _load_task_executable(self, _):
            return run_function

    window = T4TMainWindow.__new__(T4TMainWindow)
    window.task_manager = DummyTaskManager()

    dummy_signals.execute_in_main_thread.connect(
        window.execute_task_in_main_thread)

    dummy_signals.execute_in_main_thread.emit("TestTask")

    assert executed["thread"] == threading.current_thread().name
    assert isinstance(executed["context"], TaskContext)
    assert executed["context"].task_name == "TestTask"
    assert executed["inputs"] == {}
    assert executed["config"] == {"foo": "bar"}
    assert captured_logs == [("TestTask", "main-thread-log")]
