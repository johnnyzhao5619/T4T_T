import logging
from datetime import datetime
from collections import deque

import pyqtgraph as pg
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTextBrowser, QHBoxLayout,
                             QPushButton, QLabel, QFrame, QGridLayout,
                             QSplitter)
from PyQt5.QtCore import Qt

from core.service_manager import service_manager, ServiceState
from utils.i18n import _, translate_service_state
from utils.signals import global_signals

logger = logging.getLogger(__name__)


class MessageBusMonitorWidget(QWidget):
    """
    A widget to display real-time messages from the message bus and
    visualize MQTT broker activity.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # pg.setConfigOption('background', 'w')
        # pg.setConfigOption('foreground', 'k')

        self.init_ui()
        self.connect_signals()
        self.update_status()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setWindowTitle(_("message_bus_monitor_title"))

        # --- Main Splitter ---
        main_splitter = QSplitter(Qt.Vertical, self)
        main_layout.addWidget(main_splitter)

        # --- Top Panel (Stats & Graph) ---
        top_panel = QFrame()
        top_layout = QVBoxLayout(top_panel)
        top_layout.setContentsMargins(5, 5, 5, 5)

        # Control Panel
        control_panel = self._create_control_panel()
        top_layout.addWidget(control_panel)

        # Details Splitter
        details_splitter = QSplitter(Qt.Horizontal, self)

        # Connection Details Panel
        connection_panel = self._create_connection_details_panel()
        details_splitter.addWidget(connection_panel)

        # Stats Panel
        stats_panel = self._create_stats_panel()
        details_splitter.addWidget(stats_panel)

        details_splitter.setSizes([200, 200])
        top_layout.addWidget(details_splitter)

        # Graph Panel
        graph_panel = self._create_graph_panel()
        top_layout.addWidget(graph_panel)

        # --- Bottom Panel (Log Browser) ---
        log_panel = QFrame()
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(0, 0, 0, 0)
        self.text_browser = QTextBrowser()
        self.text_browser.setReadOnly(True)
        log_layout.addWidget(self.text_browser)

        main_splitter.addWidget(top_panel)
        main_splitter.addWidget(log_panel)
        main_splitter.setSizes([400, 200])

    def _create_control_panel(self):
        control_panel = QFrame()
        control_panel.setObjectName("controlPanel")
        control_layout = QHBoxLayout(control_panel)

        self.status_label = QLabel()
        self.start_button = QPushButton(_("start_broker_button"))
        self.stop_button = QPushButton(_("stop_broker_button"))

        control_layout.addWidget(QLabel(_("broker_status_label")))
        control_layout.addWidget(self.status_label)
        control_layout.addStretch()
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)
        return control_panel

    def _create_connection_details_panel(self):
        panel = QFrame()
        layout = QGridLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)

        self.host_label = self._create_stat_label("N/A")
        self.port_label = self._create_stat_label("N/A")

        layout.addWidget(QLabel(_("Host:")), 0, 0)
        layout.addWidget(self.host_label, 0, 1)
        layout.addWidget(QLabel(_("Port:")), 1, 0)
        layout.addWidget(self.port_label, 1, 1)
        layout.setRowStretch(2, 1)
        return panel

    def _create_stats_panel(self):
        stats_panel = QFrame()
        stats_layout = QGridLayout(stats_panel)
        stats_layout.setContentsMargins(10, 10, 10, 10)

        self.clients_label = self._create_stat_label("0")
        self.msg_in_label = self._create_stat_label("0.0")
        self.msg_out_label = self._create_stat_label("0.0")

        stats_layout.addWidget(QLabel(_("Clients Connected:")), 0, 0)
        stats_layout.addWidget(self.clients_label, 0, 1)
        stats_layout.addWidget(QLabel(_("Msg/s In:")), 1, 0)
        stats_layout.addWidget(self.msg_in_label, 1, 1)
        stats_layout.addWidget(QLabel(_("Msg/s Out:")), 2, 0)
        stats_layout.addWidget(self.msg_out_label, 2, 1)
        stats_layout.setRowStretch(3, 1)  # Add stretch at the bottom
        return stats_panel

    def _create_stat_label(self, text):
        label = QLabel(text)
        label.setAlignment(Qt.AlignRight)
        label.setStyleSheet("font-weight: bold; font-size: 14px;")
        return label

    def _create_graph_panel(self):
        graph_panel = pg.PlotWidget()
        graph_panel.setTitle(_("Message Rate (msg/s)"), size="12pt")
        graph_panel.setLabel('left', _("Rate"))
        graph_panel.setLabel('bottom', _("Time (s)"))
        graph_panel.showGrid(x=True, y=True)
        graph_panel.setYRange(0, 10)  # Initial range

        self.plot_data_in = graph_panel.plot(pen=pg.mkPen(color="#2ecc71",
                                                          width=2),
                                             name=_("direction_received"))
        self.plot_data_out = graph_panel.plot(pen=pg.mkPen(color="#3498db",
                                                           width=2),
                                              name=_("direction_published"))

        self.time_axis = list(range(60))
        self.msg_in_history = deque([0] * 60, maxlen=60)
        self.msg_out_history = deque([0] * 60, maxlen=60)

        return graph_panel

    def connect_signals(self):
        self.start_button.clicked.connect(
            lambda: service_manager.start_service('mqtt_broker'))
        self.stop_button.clicked.connect(
            lambda: service_manager.stop_service('mqtt_broker'))
        global_signals.service_state_changed.connect(
            self.on_service_state_changed)
        global_signals.message_published.connect(self.on_message_published)
        global_signals.message_received.connect(self.on_message_received)
        global_signals.mqtt_stats_updated.connect(self._on_stats_updated)

    def _on_stats_updated(self, stats: dict):
        self.clients_label.setText(str(stats.get('client_count', 0)))
        self.msg_in_label.setText(f"{stats.get('msg_recv_rate', 0.0):.1f}")
        self.msg_out_label.setText(f"{stats.get('msg_sent_rate', 0.0):.1f}")

        self.msg_in_history.append(stats.get('msg_recv_rate', 0.0))
        self.msg_out_history.append(stats.get('msg_sent_rate', 0.0))

        self.plot_data_in.setData(self.time_axis, list(self.msg_in_history))
        self.plot_data_out.setData(self.time_axis, list(self.msg_out_history))

    def add_message(self, direction: str, topic: str, payload: str,
                    color: QColor):
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        d_html = f'<strong style="color:{color.name()};">{direction}</strong>'
        header = (f"[{timestamp}] {d_html} | "
                  f"{_('topic_label')} <strong>{topic}</strong>")
        self.text_browser.append(header)
        self.text_browser.append(f"<pre>{payload}</pre><hr>")
        scrollbar = self.text_browser.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def on_message_published(self, topic: str, payload: str):
        color = QColor("#3498db")
        self.add_message(_("direction_published"), topic, payload, color)

    def on_message_received(self, topic: str, payload: str):
        color = QColor("#2ecc71")
        self.add_message(_("direction_received"), topic, payload, color)

    def on_service_state_changed(self, service_name: str, state: ServiceState):
        if service_name == 'mqtt_broker':
            self.update_status()

    def update_status(self):
        state = service_manager.get_service_state('mqtt_broker')
        status_icon = ""
        if state is None:
            translated_state = _("service_status_unregistered")
            status_icon = "⚪"
        else:
            translated_state = translate_service_state(state)

        status_text = f"<strong>{translated_state}</strong>"
        if status_icon:
            status_text = f"{status_icon} {status_text}"

        self.status_label.setText(status_text)

        is_running = state is not None and state == ServiceState.RUNNING
        is_stopped = state is not None and state == ServiceState.STOPPED

        if state is None:
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.status_label.setStyleSheet("color: #7f8c8d;")
            self.host_label.setText("N/A")
            self.port_label.setText("N/A")
            return

        self.start_button.setEnabled(is_stopped)
        self.stop_button.setEnabled(is_running)

        if is_running:
            self.status_label.setStyleSheet("color: #2ecc71;")
            broker_service = service_manager.get_service('mqtt_broker')
            if broker_service is not None:
                details = broker_service.get_connection_details() or {}
                self.host_label.setText(details.get('host', 'N/A'))
                self.port_label.setText(str(details.get('port', 'N/A')))
            else:
                self.host_label.setText("N/A")
                self.port_label.setText("N/A")
        elif is_stopped:
            self.status_label.setStyleSheet("color: #e74c3c;")
            self.host_label.setText("N/A")
            self.port_label.setText("N/A")
        else:
            self.status_label.setStyleSheet("color: #f39c12;")
            self.host_label.setText("...")
            self.port_label.setText("...")
