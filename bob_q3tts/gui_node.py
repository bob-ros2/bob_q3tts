# Copyright 2026 Bob Ros
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import threading

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QScrollArea, QSlider, QVBoxLayout, QWidget, QPushButton
)
import rclpy
from rclpy.node import Node
from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue
from rcl_interfaces.srv import GetParameters, SetParameters


class GUInode(Node, QMainWindow):
    """ROS 2 node with a Qt GUI for tuning TTS parameters."""

    def __init__(self):
        """Initialize the GUI node and its UI components."""
        # Initialize ROS node
        Node.__init__(self, 'tts_gui')
        # Initialize Qt Window
        QMainWindow.__init__(self)

        self.setWindowTitle("Qwen3-TTS Parameter Tuner")
        self.setMinimumWidth(600)
        self.setMinimumHeight(700)

        self.target_node = 'tts'
        self.set_cli = self.create_client(
            SetParameters, f'/{self.target_node}/set_parameters'
        )
        self.get_cli = self.create_client(
            GetParameters, f'/{self.target_node}/get_parameters'
        )

        # Setup UI
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # Header with Refresh Button
        self.header = QHBoxLayout()
        self.refresh_btn = QPushButton("Sync from Node")
        self.refresh_btn.clicked.connect(self.sync_parameters)
        self.header.addWidget(QLabel(f"Target: /{self.target_node}"))
        self.header.addStretch()
        self.header.addWidget(self.refresh_btn)
        self.layout.addLayout(self.header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.scroll.setWidget(self.content_widget)
        self.layout.addWidget(self.scroll)

        # Parameter definitions
        # name, type, min, max, scale (for double), default
        self.params = [
            # Area: Generation
            {"name": "do_sample", "type": "bool", "group": "Generation",
             "label": "Enable Sampling (Stage 1)"},
            {"name": "temperature", "type": "double", "min": 0.0, "max": 2.0,
             "scale": 100, "label": "Temperature", "group": "Generation"},
            {"name": "top_p", "type": "double", "min": 0.0, "max": 1.0,
             "scale": 100, "label": "Top-P", "group": "Generation"},
            {"name": "top_k", "type": "int", "min": 1, "max": 100,
             "label": "Top-K", "group": "Generation"},
            {"name": "repetition_penalty", "type": "double", "min": 1.0,
             "max": 2.0, "scale": 100, "label": "Repetition Penalty",
             "group": "Generation"},

            # Area: Subtalker
            {"name": "subtalker_dosample", "type": "bool", "group": "Subtalker",
             "label": "Enable Subtalker Sampling"},
            {"name": "subtalker_temperature", "type": "double", "min": 0.0,
             "max": 2.0, "scale": 100, "label": "Subtalker Temp",
             "group": "Subtalker"},
            {"name": "subtalker_top_p", "type": "double", "min": 0.0, "max": 1.0,
             "scale": 100, "label": "Subtalker Top-P", "group": "Subtalker"},
            {"name": "subtalker_top_k", "type": "int", "min": 1, "max": 100,
             "label": "Subtalker Top-K", "group": "Subtalker"},

            # Area: Logic
            {"name": "flush_timeout", "type": "int", "min": 0, "max": 5000,
             "label": "Flush Timeout (ms)", "group": "Logic"},
            {"name": "language", "type": "string", "label": "Language",
             "group": "Logic"},
            {"name": "play", "type": "bool", "label": "Real-time Playback",
             "group": "Logic"},
            {"name": "audio_device", "type": "string", "label": "Audio Device (ID/Name)",
             "group": "Logic"},
            {"name": "target_sample_rate", "type": "int", "min": 0, "max": 96000,
             "label": "Target SR (0=auto)", "group": "Logic"},
        ]

        self.groups = {}
        self.widgets = {}
        self.value_labels = {}

        self.setup_parameters()

        # Initial Sync
        self.create_timer(1.0, self.initial_sync_timer)

    def initial_sync_timer(self):
        """Try to sync once the services are available."""
        if self.get_cli.service_is_ready():
            self.sync_parameters()
            self.destroy_timer(self.initial_sync_timer)

    def setup_parameters(self):
        """Create GUI widgets for each parameter."""
        for p in self.params:
            group_name = p.get("group", "Other")
            if group_name not in self.groups:
                box = QGroupBox(group_name)
                layout = QVBoxLayout()
                box.setLayout(layout)
                self.content_layout.addWidget(box)
                self.groups[group_name] = layout

            container = QWidget()
            h_layout = QHBoxLayout(container)
            h_layout.setContentsMargins(0, 5, 0, 5)

            # Increased label width as requested
            label = QLabel(p["label"])
            label.setFixedWidth(220)
            h_layout.addWidget(label)

            if p["type"] == "bool":
                widget = QCheckBox()
                widget.stateChanged.connect(
                    lambda state, name=p["name"]: self.on_bool_change(name, state)
                )
            elif p["type"] in ["int", "double"]:
                widget = QSlider(Qt.Horizontal)
                widget.setMinimum(int(p["min"] * p.get("scale", 1)))
                widget.setMaximum(int(p["max"] * p.get("scale", 1)))

                value_label = QLabel("N/A")
                value_label.setFixedWidth(50)
                self.value_labels[p["name"]] = value_label

                if p["type"] == "double":
                    widget.valueChanged.connect(
                        lambda val, name=p["name"], sc=p["scale"], lbl=value_label:
                        self.on_double_change(name, val, sc, lbl)
                    )
                else:
                    widget.valueChanged.connect(
                        lambda val, name=p["name"], lbl=value_label:
                        self.on_int_change(name, val, lbl)
                    )

                h_layout.addWidget(widget)
                h_layout.addWidget(value_label)
            elif p["type"] == "string":
                widget = QLineEdit()
                widget.editingFinished.connect(
                    lambda name=p["name"], w=widget:
                    self.on_string_change(name, w.text())
                )

            h_layout.addWidget(widget)
            self.groups[group_name].addWidget(container)
            self.widgets[p["name"]] = widget

    def sync_parameters(self):
        """Read all current values from the target node."""
        if not self.get_cli.service_is_ready():
            self.get_logger().warn(f"Service {self.get_cli.srv_name} not ready")
            return

        req = GetParameters.Request()
        req.names = [p["name"] for p in self.params]

        future = self.get_cli.call_async(req)
        future.add_done_callback(self.on_sync_response)

    def on_sync_response(self, future):
        """Update GUI widgets based on current ROS parameter values."""
        try:
            res = future.result()
            for i, p_val in enumerate(res.values):
                name = self.params[i]["name"]
                p_type_name = self.params[i]["type"]
                widget = self.widgets[name]

                # Block signals during sync to avoid feedback loop
                widget.blockSignals(True)

                if p_type_name == "bool":
                    widget.setChecked(p_val.bool_value)
                elif p_type_name == "int":
                    val = p_val.integer_value
                    widget.setValue(val)
                    if name in self.value_labels:
                        self.value_labels[name].setText(str(val))
                elif p_type_name == "double":
                    val = p_val.double_value
                    scale = next(item["scale"] for item in self.params
                                 if item["name"] == name)
                    widget.setValue(int(val * scale))
                    if name in self.value_labels:
                        self.value_labels[name].setText(f"{val:.2f}")
                elif p_type_name == "string":
                    widget.setText(p_val.string_value)

                widget.blockSignals(False)
            self.get_logger().info("Successfully synced parameters from node.")
        except Exception as e:
            self.get_logger().error(f"Failed to sync parameters: {e}")

    def on_bool_change(self, name, state):
        """Update a boolean parameter."""
        val = (state == Qt.Checked)
        self.set_ros_param(name, ParameterType.PARAMETER_BOOL, val)

    def on_int_change(self, name, val, label):
        """Update an integer parameter and its label."""
        label.setText(str(val))
        self.set_ros_param(name, ParameterType.PARAMETER_INTEGER, int(val))

    def on_double_change(self, name, val, scale, label):
        """Update a double parameter and its label."""
        real_val = val / float(scale)
        label.setText(f"{real_val:.2f}")
        self.set_ros_param(name, ParameterType.PARAMETER_DOUBLE, float(real_val))

    def on_string_change(self, name, val):
        """Update a string parameter."""
        self.set_ros_param(name, ParameterType.PARAMETER_STRING, str(val))

    def set_ros_param(self, name, p_type, val):
        """Send a SetParameters request to the target node."""
        if not self.set_cli.service_is_ready():
            self.get_logger().warn(f"Service {self.set_cli.srv_name} not ready")
            return

        param = Parameter()
        param.name = name
        p_val = ParameterValue()
        p_val.type = p_type
        if p_type == ParameterType.PARAMETER_BOOL:
            p_val.bool_value = val
        elif p_type == ParameterType.PARAMETER_INTEGER:
            p_val.integer_value = val
        elif p_type == ParameterType.PARAMETER_DOUBLE:
            p_val.double_value = val
        elif p_type == ParameterType.PARAMETER_STRING:
            p_val.string_value = val

        param.value = p_val

        req = SetParameters.Request()
        req.parameters = [param]

        self.get_logger().info(f"Setting parameter {name} to {val}")
        self.set_cli.call_async(req)


def main(args=None):
    """Main entry point for the gui_node."""
    rclpy.init(args=args)

    app = QApplication(sys.argv)
    node = GUInode()

    # Spin ROS in a background thread
    ros_thread = threading.Thread(target=lambda: rclpy.spin(node), daemon=True)
    ros_thread.start()

    node.show()

    try:
        sys.exit(app.exec_())
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
