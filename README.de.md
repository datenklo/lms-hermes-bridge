# LMS Hermes Bridge

🇬🇧 [English](README.md) | 🇩🇪 Deutsch

Ein per Tastenkombination aufrufbares Overlay für Ubuntu (GNOME), das den Desktop, [LM Studio](https://lmstudio.ai), [Hermes](https://github.com/NousResearch/hermes-agent) und optionale externe LLM-APIs (Claude, ChatGPT, GitHub Copilot/Models, beliebige OpenAI-kompatible Dienste) verbindet. Ähnlich wie Windows Copilot als Suchfenster: Taste drücken, Frage oder Aufgabe eintippen, Antwort erhalten.

## Funktionen

- **Globale Tastenkombination** (Standard `Strg+Alt+Leertaste`) blendet ein schwebendes Suchfenster ein und aus. `Esc` oder ein Klick daneben schließt es.
- **Platzierung oben:** Das Fragefenster erscheint mittig am oberen Bildschirmrand. Unter Wayland läuft die App dafür über XWayland (`GDK_BACKEND=x11`), da Wayland Apps nicht erlaubt, ihre Fenster selbst zu positionieren.
- **Start im Hintergrund:** Läuft der lokale LM-Studio-Server (`lms server start`) oder das Hermes-Gateway (`hermes gateway start`) nicht, startet die App beides beim Start und bei Bedarf erneut, wenn eine Anfrage es braucht. Es werden nur lokale, installierte Dienste gestartet; in den Einstellungen abschaltbar.
- **Eingebaute Routinen** (ohne LLM, sofort): *Wetter* („Wie wird das Wetter morgen in Berlin?“, „Regnet es am Wochenende in Hamburg?“, „Wetter in Springfield, Illinois“, „Wetter in 3 Tagen in Wien“, mit Standardort aus den Einstellungen) und *Hilfe* („Was kann dieses Tool?“, „Hilfe Hotkey“, „Wie füge ich Claude hinzu?“), die Funktionen plus den aktuellen Status von LM Studio, Hermes und Anbietern zeigt. Die Wetterdaten stammen von [Open-Meteo](https://open-meteo.com) (nur Ortsname und Koordinaten werden gesendet; im Nur-lokal-Modus aus). In den Einstellungen abschaltbar.
- **Eigene Routinen:** Unter Rechtsklick → **Einstellungen…** → **Routinen** listet eine Tabelle alle Routinen mit Stichwörtern und Aktion. Neue Zeilen mit eigenen Stichwörtern und einer dieser Aktionen: *Text anzeigen*, *Programm starten* (ohne Shell), *URL öffnen*, *An Hermes senden*, *Modell fragen* (Prompt-Vorlage). Platzhalter: `{input}` (Anfrage ohne das Stichwort), `{prompt}`, `{home}`, `{date}`, `{time}`. Mitgelieferte Beispiele: Websuche, Dateimanager, Übersetzen. Die eingebauten Zeilen Wetter und Hilfe lassen sich abschalten oder um Stichwörter erweitern.
- **Google-Suche:** Anfragen wie „Öffne den Browser und suche bei Google nach Capybara-Türstoppern“ öffnen den Standardbrowser direkt mit den Google-Ergebnissen. Das ist eine lokale Routine und braucht Hermes' Browser-Toolset nicht.
- **Einfache Desktop-Aktionen:** Eingebaute Routinen öffnen Browser, persönlichen Ordner, Downloads, Terminal, Rechner und GNOME-Systemeinstellungen ohne Hermes. Jede Zeile kann in der Routinen-Tabelle abgeschaltet oder um Stichwörter ergänzt werden; die Befehle sind fest vorgegeben und laufen ohne Shell.
- **Trayicon** (stilisiertes Gehirn): Linksklick öffnet das Fragefenster, Rechtsklick zeigt ein Menü mit Einstellungen, Über (GitHub-Link, Lizenz) und Beenden. Nutzt das StatusNotifierItem-Protokoll, das die in Ubuntu enthaltene AppIndicator-Erweiterung unterstützt.
- **Selbst-Update:** Über **Aktualisieren…** im App-/Tray-Menü wird der saubere `main`-Checkout per Fast-Forward aktualisiert und die pipx-App neu installiert. Lokale Änderungen werden nie überschrieben; vor dem Update wird gefragt, danach kann die App neu gestartet werden.
- **Regelmäßige Update-Prüfung:** Standardmäßig aktiviert; prüft alle sechs Stunden den GitHub-Branch `main` (Intervall unter Einstellungen → Allgemein änderbar). Bei einem Update wechselt der Menüpunkt zu **Jetzt aktualisieren…** und erhält einen blauen Punkt. Die Prüfung lädt nur Git-Metadaten; die Installation braucht weiterhin eine Bestätigung.
- **Immer im Vordergrund:** Das Overlay fordert GNOME's „above“-Status an und setzt ihn beim Anzeigen oder Reaktivieren erneut.
- **Automatische Modellwahl für LM Studio.** Jede Anfrage wird eingeordnet (`fast`, `balanced`, `deep`, `code`, `agent`) und mit stufenspezifischen Parametern (Kontextlänge, Temperatur, maximale Tokens) an das passendste Modell geleitet.
- **Desktop-Kontext:** Zwischenablage-Text, markierten Text, eine Bilddatei oder einen über das Desktop-Portal bestätigten Screenshot anhängen. Bildanfragen verwenden immer ein lokales VLM, auch wenn Textanfragen fest an Hermes oder einen externen Anbieter geleitet werden. Der Bilddatei-Knopf ist deaktiviert, solange kein bildfähiges Modell geladen ist; ein installiertes Vision-Modell kann direkt im Overlay geladen werden. Ein Fähigkeits-Popover zeigt Bild-, Thinking- und Werkzeugunterstützung. Bevorzugtes Vision-Modell und automatisches Nachladen stehen unter Einstellungen → LM Studio.
- **Editierbarer Systemprompt:** Die Einstellungen enthalten getrennte Prompts für Deutsch und Englisch. Der Standard verlangt faktenbasierte, knappe Antworten, transparente Quellen und einen offenen Umgang mit Unsicherheit. Beide Sprachen lassen sich unabhängig bearbeiten oder zurücksetzen.
- **Auf Geschwindigkeit ausgelegt.** Ein bereits geladenes, passendes Modell wird bevorzugt; Modelle, die nicht in den RAM passen, werden übersprungen; geladen wird nur bei Bedarf über die `lms`-CLI.
- **Hermes-Anbindung** für aktionsorientierte Aufgaben („öffne…“, „installiere…“, „erstelle eine Datei…“) über den OpenAI-kompatiblen API-Server von Hermes.
- **Externe Modelle** (Claude, ChatGPT, Copilot/GitHub Models, eigene OpenAI-kompatible Endpunkte) als feste Route oder als Fallback, wenn LM Studio nicht läuft.
- **„Nur lokal“-Schalter**, der garantiert, dass keine Anfrage den Rechner verlässt.
- **Installation beim Start:** Wird LM Studio (Headless-Daemon + `lms`-CLI) oder Hermes auf diesem Rechner nicht gefunden, fragt die App, ob es mit dem offiziellen Installationsskript des Herstellers installiert werden soll. Der genaue Befehl wird vorher angezeigt; ohne Bestätigung wird nichts installiert. In den Einstellungen abschaltbar.
- **Rechtsklick-Einstellungen** im Overlay für alle Endpunkte, Schlüssel und Optionen.
- **Mehrsprachige Oberfläche:** Englisch und Deutsch (automatisch erkannt, umschaltbar). Neue Sprachen benötigen nur ein weiteres Wörterbuch in `i18n.py`.

## So funktioniert das Routing

| Schritt | Logik |
|---------|-------|
| 1. Einordnen | Heuristik aus Stichwörtern und Länge (kein Modellaufruf, keine Verzögerung) |
| 2. Backend | `agent`-Aufgaben gehen an Hermes (falls aktiv), alles andere an LM Studio; Fallbacks: Hermes, danach externe Anbieter (außer im Nur-lokal-Modus) |
| 3. Modell | `fast`: kleinstes Modell ≤ 9B, geladenes bevorzugt. `code`: ein Coder-Modell, falls vorhanden. `deep`: größtes Modell, das in ca. 75 % des RAM passt. `balanced`: ca. 8B-Klasse. Optionale Überschreibung pro Stufe in den Einstellungen |
| 4. Parameter | Kontextlänge (begrenzt durch das Modellmaximum), Temperatur und maximale Tokens pro Stufe |
| 5. Laden | `lms unload --all` (optional), dann `lms load <Modell> --context-length N --gpu max` |

In den Einstellungen lässt sich das Routing überschreiben: immer LM Studio, immer Hermes oder immer ein bestimmter externer Anbieter.

**Hermes-Stichwörter:** Eine Anfrage geht an Hermes, wenn sie ein Wort oder eine Wortgruppe aus einer eingebauten Liste typischer Benutzeraktionen enthält (öffne, installiere, lösche, erstelle Datei, sende E-Mail, erinnere mich, … sowie die englischen Entsprechungen). Es gibt je eine Liste pro Sprache (Englisch, Deutsch); beim Abgleich werden alle genutzt, die Einstellungen zeigen aber nur die Liste der aktuellen Oberflächensprache. Die Listen sind per Rechtsklick → **Einstellungen…** → **Hermes-Stichwörter** editierbar (ein Eintrag pro Zeile, nur ganze Wörter; ein `*` am Ende erfasst auch längere Formen, z. B. `installier*`; Artikel zwischen den Wörtern werden ignoriert, `erstelle datei` trifft also „erstelle eine Datei“).

## Voraussetzungen

- Ubuntu 24.04+ mit GNOME (X11 oder Wayland; unter Wayland läuft die App über XWayland, damit das Fenster oben platziert werden kann)
- `python3-gi` und `gir1.2-gtk-4.0`
- LM Studio mit aktiviertem lokalem Server (Standard `http://localhost:1234`) und der `lms`-CLI (`~/.lmstudio/bin/lms`)
- Optional: ein laufender Hermes-Agent-API-Server

## Installation

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 pipx
git clone https://github.com/datenklo/lms-hermes-bridge.git
cd lms-hermes-bridge
./install.sh
```

`install.sh` installiert die App mit `pipx` (mit System-Site-Packages für PyGObject), fügt **LMS Hermes Bridge** mit Gehirn-Icon zum Ubuntu-Anwendungsmenü hinzu, übernimmt die Autostart-Einstellung nach der Anmeldung und registriert die Standard-Tastenkombination als GNOME-Shortcut. Der Autostart lässt sich später unter Rechtsklick → **Einstellungen…** → **Allgemein** ändern.

Ohne Installation starten: `PYTHONPATH=src python3 -m lms_hermes_bridge`

## Konfiguration

Rechtsklick auf das Overlay oder das Trayicon, dann **Einstellungen…**:

| Reiter | Optionen |
|--------|----------|
| Allgemein | Sprache, Nur-lokal-Modus, Routing, globale Tastenkombination (mit Prüfung und Konfliktanzeige), Login-Autostart, Installationsprüfung, automatischer Backend-Start, regelmäßige Update-Prüfung und Intervall |
| Systemprompt | Deutsche und englische Assistentenanweisungen getrennt bearbeiten oder zurücksetzen |
| LM Studio | API-URL, automatisches Laden, andere Modelle entladen, Modell-Überschreibung pro Stufe, bevorzugtes Vision-Modell und automatisches VLM-Laden |
| Hermes | Aktivieren, Chat-Endpunkt-URL, API-Schlüssel, Modellname |
| Routinen | Tabelle aller Routinen: Stichwörter, Aktion, Wert; Hauptschalter; Standardort für das Wetter |
| Hermes-Stichwörter | Wörter/Wortgruppen (je Oberflächensprache), die eine Anfrage an Hermes schicken |
| Externe Modelle | Vorlagen (Claude, ChatGPT, Copilot) oder eigene Endpunkte mit URL, Schlüssel und Modell |

Die Einstellungen liegen in `~/.config/lms-hermes-bridge/config.json` (Dateirechte `0600`; API-Schlüssel stehen dort im Klartext).

### Hinweise zu Anbietern

- **Claude:** Endpunkt `https://api.anthropic.com/v1/messages`, Typ *Anthropic*.
- **ChatGPT:** Endpunkt `https://api.openai.com/v1/chat/completions`, Typ *OpenAI-kompatibel*.
- **Copilot:** nutzt GitHub Models (`https://models.github.ai/inference/chat/completions`) mit einem GitHub-Token mit dem Scope `models`. Für den Microsoft-/GitHub-Copilot-Chat selbst gibt es keine öffentliche API.
- **Hermes:** den API-Server in Hermes aktivieren und den Endpunkt auf dessen `/v1/chat/completions`-URL setzen.

## Entwicklung

```bash
PYTHONPATH=src python3 -m pytest
```

Die Routing-Logik (`router.py`) ist rein funktional und per Unit-Tests abgedeckt; die Oberfläche liegt in `app.py` und `settings_dialog.py`. Details siehe [docs/TECHNICAL.de.md](docs/TECHNICAL.de.md).

## Roadmap

- Desktop-Kontext (Zwischenablage, markierter Text, Screenshots) als Eingabe
- Gesprächsverlauf und Rückfragen
- Ablage der Schlüssel im Schlüsselbund
- Werkzeug-/Dateiaktionen mit Bestätigung im Overlay

## Lizenz

MIT
