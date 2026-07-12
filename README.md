# shortcut-cli

> **Lossless, verifiable** conversion between agent-readable commands (JSON) and iOS/macOS Shortcuts (`.shortcut`) — both directions.

![round-trip: lossless](https://img.shields.io/badge/round--trip-lossless-2ea44f)
![actions preserved: 100%](https://img.shields.io/badge/actions%20preserved-100%25-2ea44f)
[![benchmark: verified](https://img.shields.io/badge/benchmark-verified-1f6feb)](BENCHMARK.md)
![platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey)
![license: MIT](https://img.shields.io/badge/license-MIT-blue)

**English** · [中文说明](README.zh.md)

Turn a Shortcut into JSON, edit it (or have an AI edit it), and turn it back — **without losing a single action**. Not just "conversion": a proven **lossless** round-trip ([see the benchmark](BENCHMARK.md)).

- **Command → Shortcut** (`compile`): turn a JSON spec into a real, importable `.shortcut` — **signed by default**.
- **Shortcut → Command** (`decompile`): dump any `.shortcut` (signed **or** unsigned) to editable JSON or readable pseudocode.
- **iCloud link → Shortcut** (`fetch`): download the `.shortcut` behind an `icloud.com/shortcuts/...` link.
- **Import** (`import`): hand a `.shortcut` straight to the Shortcuts app's add dialog.

macOS-native (signing/decoding); the rest is cross-platform. Bilingual output (English / 中文).

---

## Who is this for? (Why this exists)

If you've ever asked **Claude, ChatGPT, Codex, Gemini, Copilot, Cursor, or any AI coding agent to generate an iOS Shortcut** and it **lost half its actions the moment you imported it** — this tool exists because I hit that wall over and over.

The cause isn't the AI and it isn't signing. When a `.shortcut` is built programmatically, the modern Shortcuts importer **silently drops whole control-flow blocks** if `UUID` / `GroupingIdentifier` are placed at an action's top level instead of inside `WFWorkflowActionParameters`. On macOS the actions just vanish; on iOS the shortcut imports but runs wrong.

`shortcut-cli` **fixes that root cause automatically** (canonical normalization) and **signs by default**, so an **AI-generated / auto-generated Shortcut actually imports intact**. It also goes the other way — decompile any shortcut to readable JSON — and can pull shortcuts from iCloud share links.

If a few keywords brought you here — *convert command to Shortcut, generate iOS Shortcut programmatically, Claude / Codex / ChatGPT / AI agent create Shortcut, decompile .shortcut, Shortcut import loses actions, sign Shortcut without a developer account* — you're in the right place, and hopefully you'll skip the detours I didn't.

---

## Platform support

The pure-Python parts run anywhere; anything touching Apple's signing service or the Apple Encrypted Archive is **macOS-only** (a hard Apple limitation, not a missing feature).

| Command | macOS | Linux / Windows |
|---|:---:|:---:|
| `compile` (unsigned, `--no-sign`) | ✅ | ✅ |
| `compile` (**signed**, default) | ✅ | ❌ needs Apple signing |
| `decompile` / `info` — unsigned files | ✅ | ✅ |
| `decompile` — **signed** files | ✅ | ❌ needs `aea`/`aa` |
| `fetch` (iCloud) | ✅ | ✅ |
| `sign` · `import` | ✅ | ❌ |

macOS-only commands exit with a clear message on other platforms instead of crashing.

## Install

**Prebuilt binary** (no Python needed) — grab `shortcut-cli-macos` / `-linux` / `-windows.exe` from [Releases](https://github.com/Wuvomi/shortcut-cli/releases):
```bash
chmod +x shortcut-cli-macos && ./shortcut-cli-macos --help
```

**From source** (Python 3.8+):
```bash
git clone https://github.com/Wuvomi/shortcut-cli.git
cd shortcut-cli
python3 shortcut_cli.py --help
# optional: put it on PATH
ln -s "$PWD/shortcut_cli.py" ~/.local/bin/shortcut-cli && chmod +x shortcut_cli.py
```

Requirements for the macOS-only bits: be **signed into iCloud** (signing uses Apple's iCloud service — **no paid Developer account needed**). Built-in tools used: `shortcuts`, `aea`, `aa`, `openssl`.

## Usage

### `info` — inspect a shortcut
```bash
shortcut-cli info MyShortcut.shortcut
```
```
name      : My Shortcut
signed    : yes (AEA1)
actions   : 21
structure : top-level GroupingId=0(0) UUID=0(0) -> OK canonical
```
The `structure` line tells you whether the shortcut is canonical (safe to import) or would be truncated.

### `decompile` — Shortcut → Command
```bash
shortcut-cli decompile MyShortcut.shortcut -o MyShortcut.json   # re-compilable JSON
shortcut-cli decompile MyShortcut.shortcut --pretty             # readable pseudocode
```
Handles **signed** shortcuts too (decrypts the Apple Encrypted Archive automatically).

### `compile` — Command → Shortcut
```bash
shortcut-cli compile MyShortcut.json --name "My Shortcut"   # signs by default
shortcut-cli compile MyShortcut.json --no-sign              # skip signing
```
Auto-normalizes structure so it imports intact, then signs → `MyShortcut.signed.shortcut`.

The command format is the shortcut's `WFWorkflowActions` array wrapped in an object — see [`examples/`](examples/):
```json
{
  "WFWorkflowName": "Hello",
  "WFWorkflowActions": [
    { "WFWorkflowActionIdentifier": "is.workflow.actions.alert",
      "WFWorkflowActionParameters": { "WFAlertActionTitle": "Hello" } }
  ]
}
```
Easiest authoring flow: build a similar shortcut in the app → `decompile` it → tweak the JSON → `compile`.

### `fetch` — iCloud link → Shortcut
```bash
shortcut-cli fetch https://www.icloud.com/shortcuts/<id>
```
Downloads the `.shortcut` (unsigned — so you can immediately decompile/edit/compile it).

### `import` — hand it to the Shortcuts app (macOS)
```bash
shortcut-cli import MyShortcut.shortcut   # auto-signs, opens the "Add Shortcut" dialog
```

### `sign` / `verify`
```bash
shortcut-cli sign  MyShortcut.shortcut
shortcut-cli verify MyShortcut.signed.shortcut   # unpacks and counts actions
```

## Bilingual output

Output follows your locale automatically, or force it:
```bash
SHORTCUT_CLI_LANG=zh shortcut-cli info x.shortcut   # 中文
SHORTCUT_CLI_LANG=en shortcut-cli info x.shortcut   # English
```

## Why it's reliable

`compile` always moves `UUID` and `GroupingIdentifier` into `WFWorkflowActionParameters`, and `info` flags any file that isn't canonical. Signing itself (`shortcuts sign`) is **lossless** — this tool proves it by unpacking signed files and counting actions on a full round-trip (`decompile → compile → sign → verify`, action count preserved).

## Reliability / round-trip fidelity

**→ Full numbers, diagrams, and a re-runnable script: [BENCHMARK.md](BENCHMARK.md).** Verified lossless on real Shortcuts up to 61 actions with nested `if`/`repeat`.

`decompile` captures the **entire** workflow (every top-level field + all actions; binary payloads like icons are base64-encoded), so `decompile → compile` is **content-lossless**. Verified on real shortcuts:

- **`original == recompiled`** by deep value comparison — **zero content loss** (all actions and workflow fields preserved).
- **`compile` is deterministic** — same input → byte-identical output.
- **Multi-round converges to a stable fixed point** (`decompile → compile → decompile` is stable after the first pass).
- Actions survive **signing** unchanged (two signatures decode to identical content).

What is **not** byte-identical, by design (metadata, not your logic):
- The binary-plist serializer normalizes dict **key order**, so re-encoded bytes/size differ slightly from Apple's original — values are unchanged.
- **Signed files are non-deterministic**: Apple's signature embeds a timestamp, so each `sign` produces different bytes (size ±1). This is fundamental, not a tool defect.
- On signing, Apple stamps its own `WFWorkflowClientVersion`; nothing else changes.

## Limitations

- Signing & signed-file decoding are **macOS-only** (see table above).
- `decompile` emits the shortcut's native action JSON — lossless but low-level; there's no high-level DSL yet.
- `fetch` depends on the current iCloud shortcuts records API shape.

## Keywords

iOS Shortcuts CLI · convert command to Shortcut · generate `.shortcut` programmatically · Claude / Codex / ChatGPT / Gemini / Copilot / Cursor / AI / LLM / agent create iOS Shortcut · auto-generate Shortcuts · decompile Shortcut · sign Shortcut without developer account · fix Shortcut import truncation / missing actions · Apple Shortcuts `WFWorkflowActions` · iCloud shortcut download.

## License

MIT — see [LICENSE](LICENSE).
