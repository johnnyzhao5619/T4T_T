# T4T Change Log

## v1.0.0 - 2024-06-01

### Added
- Introduced the v1.0 modular task architecture with `manifest.yaml` support for declaring triggers and input parameters.
- Added the built-in MQTT message bus and event-driven scheduling, compatible with external brokers and the embedded service manager.
- Refreshed the desktop UI with task lists, detail tabs, live log panels, and theme/language switching.
- Delivered the thread-pool executor and context-aware logging to keep task execution non-blocking and traceable.

### Fixed
- Unified task lifecycle management to resolve duplicate scheduling that previously caused blocking behavior.
- Improved message publish loop detection to avoid infinite recursion in event pipelines.

### Changed
- Reorganized the configuration directory layout so `config/`, `tasks/`, and theme assets are managed together for easier packaging and deployment.
