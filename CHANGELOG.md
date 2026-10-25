# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Desktop context input for clipboard text, primary-selection text, image files and portal-approved screenshots. Image requests always route to local VLMs, irrespective of forced text backend. A capability popover reports image, reasoning and tool-use support; the image-file button is disabled unless the loaded model supports vision. Users can load an installed VLM in the overlay and configure auto-loading/preferred vision model.

## [0.3.1] - 2026-10-25

### Added
- General settings now include an opt-in/out login autostart switch; changes create or remove only this app's GNOME autostart entry. The installer respects the stored setting.
- Installer adds an Ubuntu Applications-menu launcher with the brain icon.
- Built-in desktop routines open the browser, home folder, Downloads, terminal, calculator and GNOME system settings without Hermes. The fixed commands can be disabled and their keywords extended in the routines table.

### Fixed
- Google search requests now open the default browser directly with the extracted query instead of relying on Hermes' disabled browser toolset.
- Keyword patterns now allow `*` on any word in a multi-word phrase (for example `öffne* browser`).

## [0.3.0] - 2026-10-25

### Added
- **Routines table** in the settings: every routine has keywords and an action. Users can define their own rows
  (show text, run program without a shell, open URL, send to Hermes, ask the model with a prompt template;
  placeholders `{input}`, `{prompt}`, `{home}`, `{date}`, `{time}`). Built-in rows can be disabled or extended with
  keywords. Example rows ship enabled: web search, file manager, translate.
- **Built-in routines** answered without an LLM: weather (Open-Meteo; place, today/tomorrow/weekday/date/weekend/
  next days, rain and snow questions, ambiguous places via "City, Region", default location, local-only aware) and
  help (feature overview with live status, topic help for hotkey, providers, Hermes, local-only, keywords, models,
  weather).
- **Editable Hermes keyword list** (settings tab) with a broad default list of typical user actions, split into
  English and German. Whole-word matching, trailing `*` for word forms, filler articles are ignored. The tab shows
  only the list of the current UI language; all lists are used for matching.
- **Automatic background start** of the local LM Studio server and the Hermes gateway when they are down (at launch
  and on demand). Switchable in the settings.
- **Prompt window at the top centre** of the screen (on Wayland the app runs through XWayland).
- Hotkey field validates the key combination and reports conflicts with other GNOME shortcuts.
- Minimal, modern look: flat search field with icon, animated answer area, rounded corners, calmer settings window.

### Changed
- `agent_keywords` is now `{en, de}`; old flat lists are migrated. The two `routine_weather`/`routine_help` flags
  moved into the routines table and are migrated too.
- Hermes routing no longer uses a hard-coded pattern; the list lives in the config.

### Fixed
- The global hotkey did nothing when the app was started from a source checkout: the stored shortcut command lacked
  `PYTHONPATH`. The command is now self-contained, repaired automatically at app start and registered when the
  settings are saved (not only via the button).

## [0.2.0] - 2026-10-25

### Added
- Startup check for LM Studio and Hermes; if missing (and the configured endpoint is local), the app offers to run the official install script after confirmation. Switchable in the settings.

### Documentation
- German technical documentation (`docs/TECHNICAL.de.md`) and cross-links between language versions.

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

[0.3.1]: https://github.com/datenklo/lms-hermes-bridge/releases/tag/v0.3.1
[0.3.0]: https://github.com/datenklo/lms-hermes-bridge/releases/tag/v0.3.0
[0.2.0]: https://github.com/datenklo/lms-hermes-bridge/releases/tag/v0.2.0
[0.1.0]: https://github.com/datenklo/lms-hermes-bridge/releases/tag/v0.1.0
