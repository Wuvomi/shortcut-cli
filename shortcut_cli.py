#!/usr/bin/env python3
"""
shortcut-cli — convert between commands and iOS/macOS Shortcuts, both ways,
plus pull a .shortcut from an iCloud share link.

Bilingual output (English / 中文). Language is picked from:
  1. SHORTCUT_CLI_LANG=en|zh   (explicit override)
  2. your system locale (LANG/LC_ALL containing zh -> Chinese)
  3. English by default

Key rule: when building shortcut plists, UUID / GroupingIdentifier MUST live inside
WFWorkflowActionParameters, not at the action's top level — otherwise the modern importer
silently truncates control-flow blocks. `compile` normalizes this automatically.
"""
import argparse, plistlib, json, os, sys, struct, subprocess, tempfile, re, urllib.request, uuid, platform, shutil, base64

# --- lossless JSON <-> plist: encode bytes (icons/images/data) as base64 so the
#     command JSON round-trips EXACTLY, including binary payloads. ---
_BKEY = '__bytes_b64__'
def _json_default(o):
    if isinstance(o, bytes):
        return {_BKEY: base64.b64encode(o).decode('ascii')}
    raise TypeError(f'not JSON-serializable: {type(o)}')
def _json_restore(obj):
    if isinstance(obj, dict) and list(obj.keys()) == [_BKEY]:
        return base64.b64decode(obj[_BKEY])
    return obj

MAGIC_AEA = b'AEA1'
MAGIC_BPLIST = b'bplist00'
IS_MACOS = platform.system() == 'Darwin'

# Official Shortcuts icon colors (WFWorkflowIconStartColor integer values).
# Source: sebj/iOS-Shortcuts-Reference. Set with `compile --color <name>`.
COLORS = {
    'red': 4282601983, 'dark-orange': 4251333119, 'orange': 4271458815,
    'yellow': 4274264319, 'green': 4292093695, 'teal': 431817727,
    'light-blue': 1440408063, 'blue': 463140863, 'dark-blue': 946986751,
    'violet': 2071128575, 'purple': 3679049983, 'dark-gray': 255,
    'pink': 3980825855, 'taupe': 3031607807, 'gray': 2846468607,
}

def _detect_lang():
    v = os.environ.get('SHORTCUT_CLI_LANG', '').lower()
    if v.startswith('zh'): return 'zh'
    if v.startswith('en'): return 'en'
    loc = (os.environ.get('LC_ALL', '') + os.environ.get('LANG', '')).lower()
    return 'zh' if ('zh' in loc or 'cn' in loc) else 'en'

LANG = _detect_lang()
def L(en, zh): return zh if LANG == 'zh' else en

def require_tool(tool, feature):
    """Fail with a clear message on non-macOS / missing tool instead of crashing."""
    if not IS_MACOS:
        sys.exit(L(f"x `{feature}` requires macOS (needs Apple's `{tool}`)."
                   f"\n  Unsigned compile/decompile plus fetch/info work on any platform.",
                   f"x `{feature}` 需要 macOS（依赖 Apple 系统工具 `{tool}`）。"
                   f"\n  未签名的 compile/decompile 及 fetch/info 在任意平台可用。"))
    if shutil.which(tool) is None:
        sys.exit(L(f"x system tool `{tool}` not found (`{feature}` needs it). Run on macOS.",
                   f"x 找不到系统工具 `{tool}`（`{feature}` 需要它）。请在 macOS 上运行。"))

# --------------------------- read (signed / unsigned) ---------------------------
def _decode_signed(raw, path):
    require_tool('aea', 'decode signed shortcut')
    authlen = struct.unpack('<I', raw[8:12])[0]
    cert = plistlib.loads(raw[12:12+authlen])['SigningCertificateChain'][0]
    with tempfile.TemporaryDirectory() as td:
        der = os.path.join(td, 'c.der'); open(der, 'wb').write(cert)
        pem = os.path.join(td, 'c.pem')
        subprocess.run(['openssl', 'x509', '-inform', 'DER', '-in', der, '-pubkey', '-noout'],
                       stdout=open(pem, 'wb'), check=True)
        aar = os.path.join(td, 'p.aar')
        subprocess.run(['aea', 'decrypt', '-i', path, '-o', aar, '-sign-pub', pem], check=True,
                       capture_output=True)
        outdir = os.path.join(td, 'x'); os.makedirs(outdir)
        subprocess.run(['aa', 'extract', '-i', aar, '-d', outdir], check=True, capture_output=True)
        for root, _, files in os.walk(outdir):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    d = plistlib.load(open(fp, 'rb'))
                    if 'WFWorkflowActions' in d:
                        return d
                except Exception:
                    pass
    raise RuntimeError(L('no WFWorkflowActions found inside the signed file',
                         '签名文件里没找到 WFWorkflowActions'))

def load_shortcut(path):
    """Return (workflow_dict, is_signed)."""
    raw = open(path, 'rb').read()
    if raw[:4] == MAGIC_AEA:
        return _decode_signed(raw, path), True
    if raw[:8] == MAGIC_BPLIST or raw[:6] == b'<?xml ':
        return plistlib.loads(raw), False
    try:
        return plistlib.loads(raw), False
    except Exception:
        raise RuntimeError(L('unrecognized shortcut file (neither AEA1-signed nor bplist)',
                             '无法识别的快捷指令文件（既非 AEA1 签名也非 bplist）'))

# --------------------------- canonical normalization ---------------------------
def normalize(actions):
    """UUID / GroupingIdentifier must be inside the params dict (prevents import truncation)."""
    for a in actions:
        p = a.setdefault('WFWorkflowActionParameters', {})
        for k in ('UUID', 'GroupingIdentifier'):
            if k in a:
                p[k] = a.pop(k)
    return actions

WRAPPER_DEFAULTS = {
    'WFWorkflowClientVersion': '2702.0.4',
    'WFWorkflowHasShortcutInputVariables': False,
    'WFWorkflowIcon': {'WFWorkflowIconGlyphNumber': 59751, 'WFWorkflowIconStartColor': 4282601983},
    'WFWorkflowImportQuestions': [],
    'WFWorkflowInputContentItemClasses': ['WFURLContentItem', 'WFStringContentItem'],
    'WFWorkflowMinimumClientVersion': 900, 'WFWorkflowMinimumClientVersionString': '900',
    'WFWorkflowOutputContentItemClasses': [],
    'WFWorkflowTypes': ['ActionExtension', 'NCWidget', 'WatchKit'],
}

# --------------------------- subcommands ---------------------------
def cmd_info(args):
    wf, signed = load_shortcut(args.file)
    acts = wf.get('WFWorkflowActions', [])
    from collections import Counter
    c = Counter(a['WFWorkflowActionIdentifier'].replace('is.workflow.actions.', '') for a in acts)
    print(L('file      ', '文件      ') + f": {args.file}")
    print(L('name      ', '名称      ') + f": {wf.get('WFWorkflowName', L('(none; import uses file name)', '(无，导入时用文件名)'))}")
    print(L('signed    ', '已签名    ') + f": {L('yes (AEA1)','是 (AEA1)') if signed else L('no (raw bplist)','否 (裸 bplist)')}")
    print(L('actions   ', '动作数    ') + f": {len(acts)}")
    print(L('breakdown ', '动作分布  ') + f": {dict(c.most_common())}")
    ctrl = [a for a in acts if a['WFWorkflowActionIdentifier'] in
            ('is.workflow.actions.repeat.count', 'is.workflow.actions.conditional',
             'is.workflow.actions.choosefrommenu')]
    top_gi = sum('GroupingIdentifier' in a for a in ctrl)
    top_uuid = sum('UUID' in a for a in acts)
    ok = top_gi == 0 and top_uuid == 0
    verdict = L('OK canonical', 'OK canonical') if ok else L('NEEDS normalize (would truncate on import)', '需归一化（会被导入裁切）')
    print(L('structure ', '结构健康  ') + f": top-level GroupingId={top_gi}(0) UUID={top_uuid}(0) -> {verdict}")

def _pretty(acts):
    lines, depth = [], 0
    for i, a in enumerate(acts):
        ident = a['WFWorkflowActionIdentifier'].replace('is.workflow.actions.', '')
        p = a.get('WFWorkflowActionParameters', {})
        mode = p.get('WFControlFlowMode')
        if mode == 2:
            depth = max(0, depth - 1)
        pad = '  ' * depth
        extra = ''
        for k in ('WFVariableName', 'WFDictionaryKey', 'WFMenuItemTitle', 'WFHTTPMethod',
                  'WFHTTPBodyType', 'WFRepeatCount', 'WFDelayTime'):
            if k in p:
                extra += f" {k.replace('WF','').replace('Action','')}={p[k]}"
        url = p.get('WFURL')
        if isinstance(url, dict):
            s = url.get('Value', {}).get('string')
            if s:
                extra += f" url={s}"
        lines.append(f"{i:3} {pad}{ident}{extra}")
        if mode == 0:
            depth += 1
    return '\n'.join(lines)

def cmd_decompile(args):
    wf, signed = load_shortcut(args.file)
    acts = wf.get('WFWorkflowActions', [])
    if args.pretty:
        tag = L('signed', '签名') if signed else L('unsigned', '未签名')
        head = f"# {wf.get('WFWorkflowName', L('(unnamed)','(无名)'))}  ({len(acts)} {L('actions','动作')}, {tag})\n"
        out = head + _pretty(acts)
        if args.o:
            open(args.o, 'w').write(out); print(L(f"wrote readable view: {args.o}", f"已写出可读视图: {args.o}"))
        else:
            print(out)
        return
    # Lossless: dump the ENTIRE workflow dict (wrapper + actions), bytes as base64.
    js = json.dumps(wf, ensure_ascii=False, indent=2, default=_json_default)
    if args.o:
        open(args.o, 'w').write(js); print(L(f"wrote command (JSON): {args.o}  ({len(acts)} actions)",
                                             f"已写出命令(JSON): {args.o}  ({len(acts)} 动作)"))
    else:
        print(js)

def cmd_compile(args):
    spec = json.load(open(args.spec, encoding='utf-8'), object_hook=_json_restore)
    # spec may be a bare actions list, or a full workflow dict (lossless decompile output).
    if isinstance(spec, list):
        wf = dict(WRAPPER_DEFAULTS); wf['WFWorkflowActions'] = spec
    else:
        wf = dict(spec)                       # preserve the spec's own key order (fixed-point round-trip)
        for k, v in WRAPPER_DEFAULTS.items():
            wf.setdefault(k, v)               # only append wrapper keys the spec is missing
        wf.setdefault('WFWorkflowActions', [])
    acts = wf['WFWorkflowActions']
    normalize(acts)
    if args.name:
        wf['WFWorkflowName'] = args.name
    if getattr(args, 'color', None) or getattr(args, 'glyph', None) is not None:
        icon = dict(wf.get('WFWorkflowIcon', {}))
        if args.color:
            c = COLORS.get(args.color.lower().replace('_', '-'))
            icon['WFWorkflowIconStartColor'] = c if c is not None else int(args.color)
        if args.glyph is not None:
            icon['WFWorkflowIconGlyphNumber'] = int(args.glyph)
        wf['WFWorkflowIcon'] = icon
    out = args.o or os.path.splitext(args.spec)[0] + '.shortcut'
    plistlib.dump(wf, open(out, 'wb'), fmt=plistlib.FMT_BINARY)
    print(L(f"compiled: {out}  ({len(acts)} actions, canonical-normalized)",
            f"已编译: {out}  ({len(acts)} 动作, 已 canonical 归一化)"))
    if args.sign:
        require_tool('shortcuts', 'sign')
        signed = os.path.splitext(out)[0] + '.signed.shortcut'
        subprocess.run(['shortcuts', 'sign', '--mode', 'anyone', '-i', out, '-o', signed], check=True)
        print(L(f"signed  : {signed}  (ready to import)", f"已签名: {signed}  (导入即用)"))

def cmd_sign(args):
    require_tool('shortcuts', 'sign')
    out = args.o or os.path.splitext(args.file)[0] + '.signed.shortcut'
    subprocess.run(['shortcuts', 'sign', '--mode', args.mode, '-i', args.file, '-o', out], check=True)
    print(L(f"signed: {out}", f"已签名: {out}"))

def cmd_import(args):
    """(macOS) Open the .shortcut in the Shortcuts app's add dialog. Auto-signs if unsigned."""
    require_tool('shortcuts', 'import')
    path = args.file
    _, signed = load_shortcut(path)
    if not signed:
        out = os.path.splitext(path)[0] + '.signed.shortcut'
        subprocess.run(['shortcuts', 'sign', '--mode', 'anyone', '-i', path, '-o', out], check=True)
        print(L(f"unsigned -> auto-signed: {out}", f"未签名 → 已自动签名: {out}"))
        path = out
    subprocess.run(['open', path], check=True)
    print(L('Opened the Shortcuts "Add Shortcut" dialog — click Add to finish.',
            '已在快捷指令 App 打开"添加快捷指令"对话框，点一下即完成。'))
    print(L('(Fully silent / zero-click import is not supported by Apple.)',
            '（完全静默/零点击导入 Apple 不支持；这是最接近"直接导入"的官方方式。）'))

def cmd_verify(args):
    wf, signed = load_shortcut(args.file)
    n = len(wf.get('WFWorkflowActions', []))
    tag = L('signed', '签名文件') if signed else L('unsigned', '未签名')
    print(f"{tag}: " + L(f"unpacked {n} actions", f"解包出 {n} 个动作") + (L(" (contents intact)", "（内容完整可读）") if n else ""))

def cmd_fetch(args):
    m = re.search(r'/shortcuts/(?:api/records/)?([0-9A-Fa-f]{8,})', args.url)
    if not m:
        sys.exit(L("could not parse a shortcut ID (expect https://www.icloud.com/shortcuts/<id>)",
                   "无法从链接解析 shortcut ID（应形如 https://www.icloud.com/shortcuts/<id>）"))
    sid = m.group(1)
    api = f"https://www.icloud.com/shortcuts/api/records/{sid}"
    req = urllib.request.Request(api, headers={'User-Agent': 'Mozilla/5.0'})
    data = json.load(urllib.request.urlopen(req, timeout=30))
    dl = data['fields']['shortcut']['value']['downloadURL']
    name = data['fields'].get('name', {}).get('value', sid)
    out = args.o or f"{name}.shortcut"
    urllib.request.urlretrieve(dl, out)
    print(L(f"fetched: {out}  (from iCloud, name: {name})", f"已拉取: {out}  (来自 iCloud, 名称: {name})"))
    print(L("Tip: iCloud returns an unsigned workflow — decompile/edit/compile it freely.",
            "提示: iCloud 返回的是未签名 workflow，可直接 decompile/改/compile。"))

def cmd_colors(args):
    print(L("Official Shortcuts icon colors (use `compile --color <name>`):",
            "官方快捷指令图标颜色（用 `compile --color <名字>`）:"))
    for name, val in COLORS.items():
        print(f"  {name:<12} {val}")

def main():
    ap = argparse.ArgumentParser(
        prog='shortcut-cli',
        description=L('Convert commands <-> iOS/macOS Shortcuts, plus fetch from iCloud links.',
                      '命令 <-> iOS/macOS 快捷指令 双向转换 + iCloud 链接拉取。'))
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('info', help=L('summary of a .shortcut', '快捷指令概要')); p.add_argument('file'); p.set_defaults(fn=cmd_info)
    p = sub.add_parser('decompile', help=L('shortcut -> command (JSON / --pretty)', '快捷指令 -> 命令'))
    p.add_argument('file'); p.add_argument('-o'); p.add_argument('--pretty', action='store_true'); p.set_defaults(fn=cmd_decompile)
    p = sub.add_parser('compile', help=L('command (JSON) -> shortcut; signs by default (--no-sign to skip)',
                                         '命令(JSON) -> 快捷指令，默认签名(--no-sign 关闭)'))
    p.add_argument('spec'); p.add_argument('-o'); p.add_argument('--name')
    p.add_argument('--no-sign', dest='sign', action='store_false',
                   help=L('do not sign (signs by default)', '不签名(默认会签名)'))
    p.add_argument('--color', help=L('icon color name (see `colors`) or raw integer', '图标颜色名(见 colors)或整数'))
    p.add_argument('--glyph', type=int, help=L('icon glyph number', '图标 glyph 编号'))
    p.set_defaults(fn=cmd_compile, sign=True)
    p = sub.add_parser('colors', help=L('list official icon colors', '列出官方图标颜色')); p.set_defaults(fn=cmd_colors)
    p = sub.add_parser('sign', help=L('(macOS) sign a .shortcut', '(macOS)签名')); p.add_argument('file'); p.add_argument('-o'); p.add_argument('--mode', default='anyone'); p.set_defaults(fn=cmd_sign)
    p = sub.add_parser('verify', help=L('unpack a file and count actions', '解包数动作验完整')); p.add_argument('file'); p.set_defaults(fn=cmd_verify)
    p = sub.add_parser('fetch', help=L('iCloud share link -> .shortcut', 'iCloud分享链接 -> .shortcut')); p.add_argument('url'); p.add_argument('-o'); p.set_defaults(fn=cmd_fetch)
    p = sub.add_parser('import', help=L('(macOS) open in the Shortcuts app; auto-signs if needed',
                                        '(macOS)送进快捷指令App导入，未签名自动先签名'))
    p.add_argument('file'); p.set_defaults(fn=cmd_import)
    args = ap.parse_args()
    args.fn(args)

if __name__ == '__main__':
    main()
