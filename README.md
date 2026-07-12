# shortcut-cli

Convert between **plain-text/JSON "commands" and iOS/macOS Shortcuts** (`.shortcut` files), in both directions — plus pull shortcuts straight from an **iCloud share link**.

- **Command → Shortcut** (`compile`): turn a JSON spec into a real, importable `.shortcut` — **signed by default**.
- **Shortcut → Command** (`decompile`): dump any `.shortcut` (signed **or** unsigned) back to editable JSON, or a human-readable pseudocode view.
- **iCloud link → Shortcut** (`fetch`): download the `.shortcut` behind an `icloud.com/shortcuts/...` link.
- **Import** (`import`): hand a `.shortcut` straight to the Shortcuts app's add dialog (auto-signs first).

It also does the boring-but-critical parts: **signing**, **verification**, and — most importantly — it **won't let your generated shortcuts get silently truncated on import** (see [Why it's reliable](#why-its-reliable)).

> **Signing is on by default.** Unsigned, hand-built shortcuts are the #1 cause of "my shortcut lost half its actions on import." `compile` signs automatically (pass `--no-sign` to skip).

## Platform support

The pure-Python parts run anywhere; anything that touches Apple's signing service or the Apple Encrypted Archive format is **macOS-only** (there is no Windows/Linux equivalent — this is a hard Apple limitation, not a missing feature).

| Command | macOS | Linux / Windows |
|---|:---:|:---:|
| `compile` (unsigned, `--no-sign`) | ✅ | ✅ |
| `compile` (**signed**, default) | ✅ | ❌ needs Apple signing |
| `decompile` unsigned · `info` unsigned | ✅ | ✅ |
| `decompile` **signed** files | ✅ | ❌ needs `aea`/`aa` |
| `fetch` (iCloud) | ✅ | ✅ |
| `sign` · `import` | ✅ | ❌ |

On Linux/Windows the macOS-only commands exit with a clear message instead of crashing.

---

## Requirements

- **macOS** (tested on recent versions). All dependencies ship with the OS:
  - `shortcuts` — Apple's Shortcuts CLI (signing)
  - `aea` — Apple Encrypted Archive tool (decode signed shortcuts)
  - `aa` — Apple Archive tool
  - `openssl`, `python3`
- Signing uses Apple's **iCloud signing service** — you just need to be **signed into iCloud**. **No paid Apple Developer account required.**

## Install

**Option A — prebuilt binary** (no Python needed). Grab `shortcut-cli-macos` / `-linux` / `-windows.exe` from the [Releases](https://github.com/Wuvomi/shortcut-cli/releases) page:
```bash
chmod +x shortcut-cli-macos
./shortcut-cli-macos --help
```

**Option B — from source** (Python 3.8+):
```bash
git clone https://github.com/Wuvomi/shortcut-cli.git
cd shortcut-cli
python3 shortcut_cli.py --help
# optional: put it on PATH
ln -s "$PWD/shortcut_cli.py" ~/.local/bin/shortcut-cli && chmod +x shortcut_cli.py
```

---

## Usage

### `info` — inspect a shortcut
```bash
shortcut-cli info MyShortcut.shortcut
```
```
名称      : My Shortcut
已签名    : 是 (AEA1)
动作数    : 21
动作分布  : {'setvariable': 5, 'getvalueforkey': 6, 'conditional': 3, ...}
结构健康  : GroupingId顶层=0(应0) 顶层UUID=0(应0) -> ✅ canonical
```
Works on both signed and unsigned files. The **structure-health** line tells you whether the shortcut is "canonical" (safe to import) or would get truncated.

### `decompile` — Shortcut → Command
```bash
# Lossless, re-compilable JSON
shortcut-cli decompile MyShortcut.shortcut -o MyShortcut.json

# Human-readable pseudocode (not re-compilable)
shortcut-cli decompile MyShortcut.shortcut --pretty
```
`--pretty` output:
```
# My Shortcut  (21 actions, signed)
  0 comment
  1 ask
  2 setvariable VariableName=youtubeURL
  8 downloadurl HTTPMethod=GET url=https://example.com/config.json
 ...
```
Handles **signed** shortcuts too (decrypts the Apple Encrypted Archive automatically).

### `compile` — Command → Shortcut
```bash
# JSON spec -> signed, importable .shortcut  (signing is the default)
shortcut-cli compile MyShortcut.json --name "My Shortcut"

# skip signing (e.g. on Linux/Windows)
shortcut-cli compile MyShortcut.json --no-sign
```
Produces `MyShortcut.signed.shortcut` (importable without the "untrusted" warning). The compiler **automatically normalizes** the structure so it imports intact (see below).

The JSON "command" format is just the shortcut's `WFWorkflowActions` array wrapped in an object:
```json
{
  "WFWorkflowName": "Hello",
  "WFWorkflowActions": [
    {
      "WFWorkflowActionIdentifier": "is.workflow.actions.alert",
      "WFWorkflowActionParameters": {
        "WFAlertActionTitle": "Hello",
        "WFAlertActionMessage": "Made by shortcut-cli"
      }
    }
  ]
}
```
See [`examples/`](examples/). The easiest way to author a new shortcut is: build a similar one in the Shortcuts app, `decompile` it, tweak the JSON, then `compile --sign`.

### `fetch` — iCloud link → Shortcut
```bash
shortcut-cli fetch https://www.icloud.com/shortcuts/28036b99344148b7b337d30f9821e138
```
Downloads the `.shortcut` (an **unsigned** workflow — so you can immediately `decompile`, edit, and `compile --sign` it).

### `import` — hand it to the Shortcuts app (macOS)
```bash
shortcut-cli import MyShortcut.shortcut
```
Auto-signs if needed, then opens the Shortcuts app's **"Add Shortcut"** dialog — one click to add. (Fully silent, zero-click import is not supported by Apple.)

### `sign` / `verify`
```bash
shortcut-cli sign  MyShortcut.shortcut               # -> MyShortcut.signed.shortcut
shortcut-cli verify MyShortcut.signed.shortcut       # unpacks and counts actions
```

---

## Why it's reliable

When you build `.shortcut` files programmatically, the modern iOS/macOS Shortcuts importer will **silently drop actions** if `UUID` and `GroupingIdentifier` are placed at an action's **top level** instead of inside `WFWorkflowActionParameters`. `GroupingIdentifier` links the start/end of control-flow blocks (menus, `if`, `repeat`); when it's misplaced, the importer can't match the block boundaries and discards the whole block — on macOS you see actions vanish, on iOS the shortcut imports but runs wrong.

`shortcut-cli compile` **always normalizes** these into `WFWorkflowActionParameters`, and `info` will flag any file that isn't canonical. Signing itself (`shortcuts sign`) is lossless — this tool proves it by unpacking signed files and counting actions on a full round-trip.

## Limitations

- **Signing & signed-file decoding are macOS-only** (see the [Platform support](#platform-support) table). Everything else is cross-platform.
- `decompile` produces the shortcut's native action JSON — powerful and lossless, but low-level. There's no high-level DSL (yet).
- `fetch` relies on the current iCloud shortcuts records API shape; if Apple changes it, `fetch` may need an update.

## License

MIT — see [LICENSE](LICENSE).
