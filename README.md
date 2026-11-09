# LMS Hermes Bridge

🇬🇧 English | 🇩🇪 [Deutsch](README.de.md)

A hotkey-driven launcher overlay for GNOME on Ubuntu and Arch-based systems that bridges your desktop, [LM Studio](https://lmstudio.ai) or [Strata](https://stratallm.org/), [Hermes](https://github.com/NousResearch/hermes-agent) or [Pi](https://pi.dev/), and optional external LLM APIs. Press a key, type a question or task, and get an answer.

## Features

- **Global hotkey** (default `Ctrl+Alt+Space`) toggles a floating, search-bar style window. `Esc` or clicking elsewhere dismisses it.
- **Top placement:** the prompt window appears centred at the top edge of the screen. On Wayland the app therefore runs through XWayland (`GDK_BACKEND=x11`), because Wayland does not let apps position their own windows.
- **Background start:** when selected, the local LM Studio server (`lms server start`) and enabled Hermes gateway (`hermes gateway start`) can be started at launch and on demand. Only local, installed services are started; switchable in the settings. Strata and Pi are managed separately.
- **Built-in routines** (no LLM needed, instant): *Weather* ("What will the weather be like in Berlin tomorrow?", "Will it rain in Hamburg this weekend?", "weather in Springfield, Illinois", "weather in 3 days in Vienna", with a default location from the settings) and *Help* ("What can this tool do?", "help hotkey", "how do I add Claude?") that shows the features plus the live status of LM Studio, Hermes and providers. Weather data comes from [Open-Meteo](https://open-meteo.com) (only the place name and coordinates are sent; disabled in local-only mode). Can be switched off in the settings.
- **Your own routines:** under right-click → **Settings…** → **Routines** a table lists all routines with keywords and action. Add rows with your own keywords and one of these actions: *show text*, *run program* (no shell), *open URL*, *send to agent*, *ask the model* (prompt template). Placeholders: `{input}` (request without the keyword), `{prompt}`, `{home}`, `{date}`, `{time}`. Examples that ship with the app: web search, file manager, translate. The built-in weather and help rows can be switched off or extended with extra keywords.
- **Google searches:** requests such as “open the browser and search Google for capybara doorstops” open the default browser directly to Google results. This is a local routine and does not require Hermes' browser toolset.
- **Simple desktop actions:** built-in routines can open the browser, home folder, Downloads, terminal, calculator, and GNOME system settings without contacting Hermes. Disable or add keywords for each in the Routines table; the commands are fixed and run without a shell.
- **Tray icon** (stylized brain): left click opens the prompt window, right click shows a menu with Settings, About (GitHub link, license) and Quit. Uses the StatusNotifierItem protocol, which Ubuntu's built-in AppIndicator extension supports.
- **Self-update:** choose **Update…** in the app/tray menu to fast-forward the clean `main` checkout and reinstall the pipx app. Local checkout changes are never overwritten; the app asks before updating and offers a restart afterward.
- **Periodic update check:** enabled by default, checks the GitHub `main` branch every six hours (configurable under Settings → General). When an update is available, the menu changes to **Update now…** with a blue dot. The check only fetches Git metadata; installing still requires confirmation.
- **Always on top:** the prompt overlay requests GNOME's above state and reapplies it when shown or reactivated.
- **Automatic model selection for LM Studio.** Every prompt is classified (`fast`, `balanced`, `deep`, `code`, `agent`) and routed to the best fitting model with tier-specific parameters (context length, temperature, max tokens).
- **Desktop context:** add clipboard text, selected text, an image file or a portal-approved screenshot. Image requests use a vision model from the selected model backend, even if text routing is forced to an agent or an external provider. The image-file button is disabled unless a loaded model supports vision. LM Studio can load an installed vision model from the overlay; Strata manages its models separately. A capability popover shows image, thinking and tool-use support.
- **Editable system prompt:** the settings include separate German and English prompts. The supplied default asks for fact-grounded, concise answers, transparent sources and clear uncertainty; edit either language or reset it independently.
- **Fast by design.** An already loaded model that fits the request is preferred over loading a new one; models that do not fit your RAM are skipped; models are loaded through the `lms` CLI only when needed.
- **Agent integration:** route action-oriented tasks ("open…", "install…", "create a file…") to the selected Hermes API server or Pi installation.
- **External models** (Claude, ChatGPT, Copilot/GitHub Models, custom OpenAI-compatible endpoints), usable as forced route or as fallback when the selected model backend is unavailable.
- **Local-only switch** that blocks requests to configured remote model and agent endpoints.
- **Graphical setup:** on first start, choose Pi or Hermes, LM Studio, Strata and model/API endpoints. Reopen it from the app or tray menu. Missing selected components can be installed with their official scripts after confirmation.
- **Right-click settings menu** inside the overlay for all endpoints, keys and options.
- **Multilingual UI:** English and German, selectable in settings or automatically detected from the system locale. Unsupported locales fall back to English.

## How routing works

| Step | Logic |
| ------ | ------- |
| 1. Classify | Keyword and length heuristics (no model call, zero latency) |
| 2. Backend | `agent` tasks go to the selected enabled agent (Hermes or Pi); everything else to the selected local backend (LM Studio or Strata); fallbacks: the selected agent, then external providers (unless local-only) |
| 3. Model | `fast`: smallest model ≤ 9B, loaded one preferred. `code`: a coder model if present. `deep`: largest model that fits ~75% of RAM. `balanced`: ~8B class. Optional per-tier overrides in settings |
| 4. Parameters | Context length (capped by the model maximum), temperature and max tokens per tier |
| 5. Load | LM Studio can load models via `lms`; Strata manages model loading itself |

The setup selects **Local, then LAN, then Internet** for ordinary model requests. It tries enabled endpoints in that order and switches to the next only when an attempt fails before producing output. A LAN provider selected in setup is treated as LAN even when it uses a hostname; other hostnames are treated as Internet. Local-only mode still blocks LAN and Internet requests. Image requests only use configured model backends with known vision support.

For agent tasks with a configured Pi endpoint, priority routing also tries available model endpoints in that order using Pi for each attempt. It does not retry after text output, tool activity, an invalid event or an ambiguous process failure. These attempts disable Pi extensions and MCP. Hermes manages its own models and internal fallback; the bridge cannot enforce this order or the tool-activity boundary inside Hermes.

You can change routing in settings: automatic, local/LAN/Internet priority, always the selected model backend, always the selected agent, or always a specific external provider.

**Agent keywords:** a request goes to the selected agent when it contains a word or phrase from the built-in list of user actions. Both English and German lists are used for matching; the settings tab shows the current UI language. Edit them under right-click → **Settings…** → **Agent keywords** (one entry per line; a trailing `*` also matches longer forms).

## Requirements

- Ubuntu 24.04+ or Arch Linux / Arch-based distributions such as CachyOS with GNOME (X11 or Wayland; on Wayland the app runs through XWayland so the window can be placed at the top)
- GTK 4 and PyGObject (`python3-gi` and `gir1.2-gtk-4.0` on Ubuntu; `python-gobject` and `gtk4` on Arch)
- LM Studio with its local server and `lms` CLI, or a running Strata server
- Optional: a running Hermes agent API server or an installed and configured Pi

## Install

```bash
git clone https://github.com/datenklo/lms-hermes-bridge.git
cd lms-hermes-bridge
./install.sh
```

On Ubuntu/Debian and Arch/CachyOS, the terminal installer checks system packages, displays the missing packages and the `sudo apt-get` or `sudo pacman` command, and asks for confirmation before installing them. It stops if confirmation is declined or installation fails. This terminal step runs before graphical setup so GTK and PyGObject can be installed first. Git and a terminal are required to start the installation.

Enable the tray extension with `gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com` (log out and back in first if GNOME does not find the newly installed extension). Another StatusNotifierItem host can be used instead. The global shortcut requires a GNOME session; window placement requires XWayland and `DISPLAY` under Wayland.

`install.sh` installs the app with `pipx` (using system site-packages for PyGObject), adds **LMS Hermes Bridge** to the Applications menu with the brain icon, applies the login autostart setting and registers the default hotkey as a GNOME custom shortcut. Login autostart can be changed later in right-click → **Settings…** → **General**.

To uninstall, choose **Uninstall…** in **Settings…** and confirm. The app removes its pipx installation, shortcut, autostart and application menu entry, then quits. Configuration including API keys, system packages, other components and the Git checkout remain.

Run without installing: `PYTHONPATH=src python3 -m lms_hermes_bridge`

## Configuration

Right-click the overlay and choose **Settings…**:

To use [Strata](https://github.com/Niko1221/Strata) instead of LM Studio, select **Strata** as the local model backend under **General**, and configure its server URL and optional API key under **Strata**. On the next start, the app offers its official installer for a missing local Strata installation only when a GPU with more than 11 GiB of dedicated VRAM is detected. If memory cannot be determined, no installation is offered. Start a model with Strata (for example `strata launch`). Enable image support only when the served model supports it. Remote Strata servers are configured separately and do not require a local GPU.

To use [Pi](https://pi.dev/) instead of Hermes, enter an OpenAI-compatible model API base URL (typically ending in `/v1`), model and optional key in **Setup…**. Without LM Studio, the Pi URL must be remote. The bridge starts Pi with an isolated temporary agent configuration for that endpoint; existing Pi settings, extensions and credentials are not loaded in this mode. Pi may execute tools and modify files in its working directory. Pi is unavailable while local-only mode is enabled because the bridge cannot verify Pi's provider or tool network access.

Local-only mode blocks configured remote API endpoints, but cannot restrict network access by agent tools, user-defined commands, the backend itself, or other application features such as update checks.

| Tab | Options |
| ----- | --------- |
| General | Language, local-only mode, routing, global hotkey (validated, conflicts shown), login autostart, install check, automatic backend start, periodic update check and interval |
| System prompt | Edit or reset the German and English assistant instructions independently |
| LM Studio | API URL, auto-load, unload others, per-tier model overrides, preferred vision model and automatic VLM loading |
| Strata | API URL, optional API key and image support |
| Hermes | Enable, chat endpoint URL, API key, model name |
| Pi | Enable, executable, working directory, optional provider and model |
| Routines | Table of all routines: keywords, action, value; master switch; default weather location |
| Agent keywords | Words/phrases (per UI language) that send a request to the selected agent |
| External models | Add presets (Claude, ChatGPT, Copilot) or custom endpoints with URL, key and model |

Settings are stored in `~/.config/lms-hermes-bridge/config.json` (file mode `0600`, API keys are stored in plain text there).

### Provider notes

- **Claude:** endpoint `https://api.anthropic.com/v1/messages`, type *Anthropic*.
- **ChatGPT:** endpoint `https://api.openai.com/v1/chat/completions`, type *OpenAI-compatible*.
- **Copilot:** uses GitHub Models (`https://models.github.ai/inference/chat/completions`) with a GitHub token that has the `models` scope. There is no public API for the Microsoft/GitHub Copilot chat itself.
- **Hermes:** enable the API server in Hermes and point the endpoint to its `/v1/chat/completions` URL.

## Development

```bash
PYTHONPATH=src python3 -m pytest
```

The routing logic (`router.py`) is pure and unit-tested; UI code lives in `app.py` and `settings_dialog.py`. See [docs/TECHNICAL.md](docs/TECHNICAL.md) (also in [German](docs/TECHNICAL.de.md)) for the architecture and [CHANGELOG.md](CHANGELOG.md) for release notes.

## Roadmap

- Conversation history and follow-ups
- Keyring-based secret storage
- Tool/file actions confirmed from the overlay

## License

MIT
