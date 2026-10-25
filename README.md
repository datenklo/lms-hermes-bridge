# LMS Hermes Bridge

🇬🇧 English | 🇩🇪 [Deutsch](README.de.md)

A hotkey-driven launcher overlay for Ubuntu (GNOME) that bridges your desktop, [LM Studio](https://lmstudio.ai), [Hermes](https://github.com/NousResearch/hermes-agent) and optional external LLM APIs (Claude, ChatGPT, GitHub Copilot/Models, any OpenAI-compatible service). Think "Windows Copilot" as a search-style popup: press a key, type a question or task, get an answer.

## Features

- **Global hotkey** (default `Ctrl+Alt+Space`) toggles a floating, search-bar style window. `Esc` or clicking elsewhere dismisses it.
- **Top placement:** the prompt window appears centred at the top edge of the screen. On Wayland the app therefore runs through XWayland (`GDK_BACKEND=x11`), because Wayland does not let apps position their own windows.
- **Background start:** if the local LM Studio server (`lms server start`) or the Hermes gateway (`hermes gateway start`) is not running, the app starts it at launch and again on demand when a request needs it. Only local, installed services are started; switchable in the settings.
- **Built-in routines** (no LLM needed, instant): *Weather* ("What will the weather be like in Berlin tomorrow?", "Will it rain in Hamburg this weekend?", "weather in Springfield, Illinois", "weather in 3 days in Vienna", with a default location from the settings) and *Help* ("What can this tool do?", "help hotkey", "how do I add Claude?") that shows the features plus the live status of LM Studio, Hermes and providers. Weather data comes from [Open-Meteo](https://open-meteo.com) (only the place name and coordinates are sent; disabled in local-only mode). Can be switched off in the settings.
- **Your own routines:** under right-click → **Settings…** → **Routines** a table lists all routines with keywords and action. Add rows with your own keywords and one of these actions: *show text*, *run program* (no shell), *open URL*, *send to Hermes*, *ask the model* (prompt template). Placeholders: `{input}` (request without the keyword), `{prompt}`, `{home}`, `{date}`, `{time}`. Examples that ship with the app: web search, file manager, translate. The built-in weather and help rows can be switched off or extended with extra keywords.
- **Google searches:** requests such as “open the browser and search Google for capybara doorstops” open the default browser directly to Google results. This is a local routine and does not require Hermes' browser toolset.
- **Simple desktop actions:** built-in routines can open the browser, home folder, Downloads, terminal, calculator, and GNOME system settings without contacting Hermes. Disable or add keywords for each in the Routines table; the commands are fixed and run without a shell.
- **Tray icon** (stylized brain): left click opens the prompt window, right click shows a menu with Settings, About (GitHub link, license) and Quit. Uses the StatusNotifierItem protocol, which Ubuntu's built-in AppIndicator extension supports.
- **Automatic model selection for LM Studio.** Every prompt is classified (`fast`, `balanced`, `deep`, `code`, `agent`) and routed to the best fitting model with tier-specific parameters (context length, temperature, max tokens).
- **Fast by design.** An already loaded model that fits the request is preferred over loading a new one; models that do not fit your RAM are skipped; models are loaded through the `lms` CLI only when needed.
- **Hermes integration** for action-oriented tasks ("open…", "install…", "create a file…") via Hermes' OpenAI-compatible API server.
- **External models** (Claude, ChatGPT, Copilot/GitHub Models, custom OpenAI-compatible endpoints), usable as forced route or as fallback when LM Studio is down.
- **Local-only switch** that guarantees no request leaves your machine.
- **Install on start:** if LM Studio (headless daemon + `lms` CLI) or Hermes is not found on this machine, the app asks whether to install it with the vendor's official install script. The exact command is shown before anything runs; nothing is installed without confirmation. Can be switched off in the settings.
- **Right-click settings menu** inside the overlay for all endpoints, keys and options.
- **Multilingual UI:** English and German (auto-detected, switchable). New languages are one dictionary in `i18n.py`.

## How routing works

| Step | Logic |
|------|-------|
| 1. Classify | Keyword and length heuristics (no model call, zero latency) |
| 2. Backend | `agent` tasks (keyword list, editable) go to Hermes (if enabled); everything else to LM Studio; fallbacks: Hermes, then external providers (unless local-only) |
| 3. Model | `fast`: smallest model ≤ 9B, loaded one preferred. `code`: a coder model if present. `deep`: largest model that fits ~75% of RAM. `balanced`: ~8B class. Optional per-tier overrides in settings |
| 4. Parameters | Context length (capped by the model maximum), temperature and max tokens per tier |
| 5. Load | `lms unload --all` (optional) then `lms load <model> --context-length N --gpu max` |

You can override automatic routing in settings: always LM Studio, always Hermes, or always a specific external provider.

**Hermes keywords:** a request goes to Hermes when it contains one of the words or phrases from a built-in list of typical user actions (open, install, delete, create file, send email, remind me, … and their German equivalents). There is one list per language (English, German); all of them are used for matching, but the settings tab only shows the list of the current UI language. The lists are editable under right-click → **Settings…** → **Hermes keywords** (one entry per line, whole words only; a trailing `*` also matches longer forms, e.g. `install*`; articles between words are ignored, so `create file` matches "create a file").

## Requirements

- Ubuntu 24.04+ with GNOME (X11 or Wayland; on Wayland the app runs through XWayland so the window can be placed at the top)
- `python3-gi` and `gir1.2-gtk-4.0`
- LM Studio with its local server enabled (default `http://localhost:1234`) and the `lms` CLI (`~/.lmstudio/bin/lms`)
- Optional: a running Hermes agent API server

## Install

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 pipx
git clone https://github.com/datenklo/lms-hermes-bridge.git
cd lms-hermes-bridge
./install.sh
```

`install.sh` installs the app with `pipx` (using system site-packages for PyGObject), adds **LMS Hermes Bridge** to Ubuntu's Applications menu with the brain icon, adds an autostart entry and registers the default hotkey as a GNOME custom shortcut. You can change the hotkey in the settings (right-click the overlay, then **Settings…**).

Run without installing: `PYTHONPATH=src python3 -m lms_hermes_bridge`

## Configuration

Right-click the overlay and choose **Settings…**:

| Tab | Options |
|-----|---------|
| General | Language, local-only mode, routing, global hotkey (validated, conflicts shown), install check at start, automatic start of LM Studio/Hermes |
| LM Studio | API URL, auto-load, unload others, per-tier model overrides |
| Hermes | Enable, chat endpoint URL, API key, model name |
| Routines | Table of all routines: keywords, action, value; master switch; default weather location |
| Hermes keywords | Words/phrases (per UI language) that send a request to Hermes |
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

- Desktop context (clipboard, selected text, screenshots) as prompt input
- Conversation history and follow-ups
- Keyring-based secret storage
- Tool/file actions confirmed from the overlay

## License

MIT
