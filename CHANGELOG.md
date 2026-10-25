# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-25

### Added
- Overlay window with global hotkey (GNOME custom shortcut, default `Ctrl+Alt+Space`).
- Automatic routing between LM Studio models by task tier (`fast`, `balanced`, `deep`, `code`, `agent`) with per-tier parameters and automatic model loading via the `lms` CLI.
- Hermes integration via its OpenAI-compatible API.
- External providers: Claude (Anthropic), ChatGPT (OpenAI), Copilot (GitHub Models) and custom OpenAI-compatible endpoints.
- Local-only mode.
- Tray icon (stylized brain) with left click to open the prompt window and a right-click menu (Settings, About, Quit).
- Settings dialog for endpoints, keys, routing, language and hotkey.
- About dialog with GitHub link and license.
- English and German user interface.
- English and German README, technical documentation, installer script, unit tests for the routing logic.

[0.1.0]: https://github.com/datenklo/lms-hermes-bridge/releases/tag/v0.1.0
