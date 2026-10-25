# LMS Hermes Bridge

A hotkey-driven launcher overlay for Ubuntu (GNOME) that bridges your desktop, [LM Studio](https://lmstudio.ai), [Hermes](https://github.com/NousResearch/hermes-agent) and optional external LLM APIs (Claude, ChatGPT, GitHub Copilot/Models, any OpenAI-compatible service). Think "Windows Copilot" as a search-style popup: press a key, type a question or task, get an answer.

## Features

- **Global hotkey** (default `Ctrl+Alt+Space`) toggles a floating, search-bar style window. `Esc` or clicking elsewhere dismisses it.
- **Tray icon** (stylized brain): left click opens the prompt window, right click opens the settings dialog. Uses the StatusNotifierItem protocol, which Ubuntu's built-in AppIndicator extension supports.
- **Automatic model selection for LM Studio.** Every prompt is classified (`fast`, `balanced`, `deep`, `code`, `agent`) and routed to the best fitting model with tier-specific parameters (context length, temperature, max tokens).
- **Fast by design.** An already loaded model that fits the request is preferred over loading a new one; models that do not fit your RAM are skipped; models are loaded through the `lms` CLI only when needed.
- **Hermes integration** for action-oriented tasks ("open…", "install…", "create a file…") via Hermes' OpenAI-compatible API server.
- **External models** (Claude, ChatGPT, Copilot/GitHub Models, custom OpenAI-compatible endpoints), usable as forced route or as fallback when LM Studio is down.
- **Local-only switch** that guarantees no request leaves your machine.
- **Right-click settings menu** inside the overlay for all endpoints, keys and options.
- **Multilingual UI:** English and German (auto-detected, switchable). New languages are one dictionary in `i18n.py`.

## How routing works

| Step | Logic |
|------|-------|
| 1. Classify | Keyword and length heuristics (no model call, zero latency) |
| 2. Backend | `agent` tasks go to Hermes (if enabled); everything else to LM Studio; fallbacks: Hermes, then external providers (unless local-only) |
| 3. Model | `fast`: smallest model ≤ 9B, loaded one preferred. `code`: a coder model if present. `deep`: largest model that fits ~75% of RAM. `balanced`: ~8B class. Optional per-tier overrides in settings |
| 4. Parameters | Context length (capped by the model maximum), temperature and max tokens per tier |
| 5. Load | `lms unload --all` (optional) then `lms load <model> --context-length N --gpu max` |

You can override automatic routing in settings: always LM Studio, always Hermes, or always a specific external provider.

## Requirements

- Ubuntu 24.04+ with GNOME (X11 or Wayland)
- `python3-gi` and `gir1.2-gtk-4.0`
- LM Studio with its local server enabled (default `http://localhost:1234`) and the `lms` CLI (`~/.lmstudio/bin/lms`)
- Optional: a running Hermes agent API server

## Install

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 pipx
git clone https://github.com/<your-user>/lms-hermes-bridge.git
cd lms-hermes-bridge
./install.sh
```

`install.sh` installs the app with `pipx` (using system site-packages for PyGObject), adds an autostart entry and registers the default hotkey as a GNOME custom shortcut. You can change the hotkey in the settings (right-click the overlay, then **Settings…**).

Run without installing: `PYTHONPATH=src python3 -m lms_hermes_bridge`

## Configuration

Right-click the overlay and choose **Settings…**:

| Tab | Options |
|-----|---------|
| General | Language, local-only mode, routing, global hotkey |
| LM Studio | API URL, auto-load, unload others, per-tier model overrides |
| Hermes | Enable, chat endpoint URL, API key, model name |
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

The routing logic (`router.py`) is pure and unit-tested; UI code lives in `app.py` and `settings_dialog.py`.

## Roadmap

- Desktop context (clipboard, selected text, screenshots) as prompt input
- Conversation history and follow-ups
- Keyring-based secret storage
- Tool/file actions confirmed from the overlay

## License

MIT
