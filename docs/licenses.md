# Third-Party Licenses

This document summarizes the licensing status of the direct runtime dependencies listed in `requirements.txt` and how each one interacts with the project's MIT license. Revisit this table whenever dependencies change.

| Dependency | Upstream License | MIT Compatibility | Notes |
| --- | --- | --- | --- |
| PyQt5 | GPL v3 (default) / Commercial | ⚠️ Conditioned | Shipping binaries under MIT requires either distributing the full source code under GPL v3 terms or holding a commercial PyQt license from Riverbank Computing. Document the chosen path in release materials. |
| psutil | BSD 3-Clause | ✅ Compatible | Permissive terms align with MIT requirements. |
| PyYAML | MIT | ✅ Compatible | Same license family; no additional obligations. |
| paho-mqtt | Eclipse Distribution License 1.0 | ✅ Compatible | Permissive license compatible with MIT redistribution. |
| APScheduler | MIT | ✅ Compatible | Same license family; no additional obligations. |
| qtawesome | MIT | ✅ Compatible | Same license family; no additional obligations. |
| amqtt | MIT | ✅ Compatible | Same license family; no additional obligations. |
| pyqtgraph | MIT | ✅ Compatible | Same license family; no additional obligations. |
| PyAutoGUI | BSD 3-Clause | ✅ Compatible | Permissive terms align with MIT requirements. |
| Markdown 3.4.4 | BSD 3-Clause | ✅ Compatible | Permissive terms align with MIT requirements. |

## Review Checklist

* Confirm that the `requirements.txt` file matches this inventory before every release.
* Re-run license identification (e.g., `pip-licenses` or manual verification) whenever dependencies are added or version-pinned to ensure compatibility remains unchanged.
* Capture any non-permissive obligations in deployment notes so downstream operators understand redistribution requirements.
