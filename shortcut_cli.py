#!/usr/bin/env python3
"""
shortcut-cli —— 命令 <-> iOS 快捷指令 双向转换 + iCloud 分享链接拉取

子命令:
  info       <file>                看快捷指令概要(名字/动作数/是否签名)
  decompile  <file> [-o out.json] [--pretty]
                                    快捷指令 -> 命令(JSON)。支持已签名(.shortcut AEA)与未签名。
                                    --pretty 输出人类可读伪代码(不可回编译)。
  compile    <spec.json> [-o out.shortcut] [--sign] [--name NAME]
                                    命令(JSON) -> 快捷指令。自动做 canonical 归一化(防导入裁切)。
                                    --sign 用 `shortcuts sign` 出可导入的签名文件。
  sign       <file> [-o out] [--mode anyone|people-who-know-me]
  verify     <file>                验证签名文件内容完整(解包数动作)
  fetch      <icloud_share_url> [-o out.shortcut]
                                    从 https://www.icloud.com/shortcuts/<id> 拉 .shortcut

关键铁律(见全局记忆 reference_ios_shortcut_plist_authoring):
  compile 时 UUID / GroupingIdentifier 必须在 WFWorkflowActionParameters 内,否则新版
  导入器裁切。本工具 compile 强制归一化。
"""
import argparse, plistlib, json, os, sys, struct, subprocess, tempfile, re, urllib.request, uuid, platform, shutil

MAGIC_AEA = b'AEA1'
MAGIC_BPLIST = b'bplist00'

IS_MACOS = platform.system() == 'Darwin'

def require_tool(tool, feature):
    """非 macOS / 缺工具时给清晰报错，而不是崩溃。"""
    if not IS_MACOS:
        sys.exit(f"✗ `{feature}` 需要 macOS（依赖 Apple 系统工具 `{tool}`）。"
                 f"\n  未签名文件的 compile/decompile 及 fetch/info 在任意平台可用。")
    if shutil.which(tool) is None:
        sys.exit(f"✗ 找不到系统工具 `{tool}`（`{feature}` 需要它）。请在 macOS 上运行。")

# --------------------------- 读取(支持签名/未签名) ---------------------------
def _decode_signed(raw, path):
    """AEA1 签名文件 -> WFWorkflow dict。用系统 aea/aa。"""
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
        # 找 .wflow / bplist
        for root, _, files in os.walk(outdir):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    d = plistlib.load(open(fp, 'rb'))
                    if 'WFWorkflowActions' in d:
                        return d
                except Exception:
                    pass
    raise RuntimeError('签名文件里没找到 WFWorkflowActions')

def load_shortcut(path):
    """返回 (workflow_dict, is_signed)。"""
    raw = open(path, 'rb').read()
    if raw[:4] == MAGIC_AEA:
        return _decode_signed(raw, path), True
    if raw[:8] == MAGIC_BPLIST or raw[:6] == b'<?xml ':
        return plistlib.loads(raw), False
    # 有些是 AEA 但魔数偏移/其它, 兜底尝试 plist
    try:
        return plistlib.loads(raw), False
    except Exception:
        raise RuntimeError('无法识别的快捷指令文件格式(既非 AEA1 签名也非 bplist)')

# --------------------------- canonical 归一化 ---------------------------
def normalize(actions):
    """UUID / GroupingIdentifier 必须在参数内(防导入裁切)。"""
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

# --------------------------- 子命令 ---------------------------
def cmd_info(args):
    wf, signed = load_shortcut(args.file)
    acts = wf.get('WFWorkflowActions', [])
    from collections import Counter
    c = Counter(a['WFWorkflowActionIdentifier'].replace('is.workflow.actions.', '') for a in acts)
    print(f"文件      : {args.file}")
    print(f"名称      : {wf.get('WFWorkflowName', '(无, 导入时用文件名)')}")
    print(f"已签名    : {'是 (AEA1)' if signed else '否 (裸 bplist)'}")
    print(f"动作数    : {len(acts)}")
    print(f"动作分布  : {dict(c.most_common())}")
    # 结构健康
    ctrl = [a for a in acts if a['WFWorkflowActionIdentifier'] in
            ('is.workflow.actions.repeat.count', 'is.workflow.actions.conditional',
             'is.workflow.actions.choosefrommenu')]
    top_gi = sum('GroupingIdentifier' in a for a in ctrl)
    top_uuid = sum('UUID' in a for a in acts)
    print(f"结构健康  : GroupingId顶层={top_gi}(应0) 顶层UUID={top_uuid}(应0) "
          f"-> {'✅ canonical' if top_gi==0 and top_uuid==0 else '⚠️ 需归一化(会被导入裁切)'}")

def _pretty(acts):
    lines = []
    depth = 0
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
        out = f"# {wf.get('WFWorkflowName','(无名)')}  ({len(acts)} 动作, {'签名' if signed else '未签名'})\n" + _pretty(acts)
        if args.o:
            open(args.o, 'w').write(out); print(f"已写出可读视图: {args.o}")
        else:
            print(out)
        return
    spec = {'WFWorkflowName': wf.get('WFWorkflowName', ''), 'WFWorkflowActions': acts}
    js = json.dumps(spec, ensure_ascii=False, indent=2)
    if args.o:
        open(args.o, 'w').write(js); print(f"已写出命令(JSON): {args.o}  ({len(acts)} 动作)")
    else:
        print(js)

def cmd_compile(args):
    spec = json.load(open(args.spec, encoding='utf-8'))
    acts = spec.get('WFWorkflowActions', spec if isinstance(spec, list) else [])
    normalize(acts)
    wf = dict(WRAPPER_DEFAULTS)
    wf['WFWorkflowActions'] = acts
    wf['WFWorkflowName'] = args.name or spec.get('WFWorkflowName', '') or ''
    out = args.o or os.path.splitext(args.spec)[0] + '.shortcut'
    plistlib.dump(wf, open(out, 'wb'), fmt=plistlib.FMT_BINARY)
    print(f"已编译: {out}  ({len(acts)} 动作, 已 canonical 归一化)")
    if args.sign:
        require_tool('shortcuts', 'sign')
        signed = os.path.splitext(out)[0] + '.signed.shortcut'
        subprocess.run(['shortcuts', 'sign', '--mode', 'anyone', '-i', out, '-o', signed], check=True)
        print(f"已签名: {signed}  (导入即用)")

def cmd_sign(args):
    require_tool('shortcuts', 'sign')
    out = args.o or os.path.splitext(args.file)[0] + '.signed.shortcut'
    subprocess.run(['shortcuts', 'sign', '--mode', args.mode, '-i', args.file, '-o', out], check=True)
    print(f"已签名: {out}")

def cmd_import(args):
    """在 macOS 上把 .shortcut 送进 Shortcuts App 的导入对话框（点一下即添加）。未签名会自动先签名。"""
    require_tool('shortcuts', 'import')
    path = args.file
    _, signed = load_shortcut(path)
    if not signed:
        out = os.path.splitext(path)[0] + '.signed.shortcut'
        subprocess.run(['shortcuts', 'sign', '--mode', 'anyone', '-i', path, '-o', out], check=True)
        print(f"未签名 → 已自动签名: {out}")
        path = out
    subprocess.run(['open', path], check=True)
    print('已在 Shortcuts App 打开导入对话框，点"添加快捷指令"即完成。')
    print('（说明：完全静默/零点击导入 Apple 不支持；这是最接近"直接导入"的官方方式。）')

def cmd_verify(args):
    wf, signed = load_shortcut(args.file)
    n = len(wf.get('WFWorkflowActions', []))
    print(f"{'✅ 签名文件' if signed else '⚠️ 未签名'}: 解包出 {n} 个动作" + ("(内容完整可读)" if n else ""))

def cmd_fetch(args):
    m = re.search(r'/shortcuts/(?:api/records/)?([0-9A-Fa-f]{8,})', args.url)
    if not m:
        sys.exit("无法从链接解析 shortcut ID(应形如 https://www.icloud.com/shortcuts/<id>)")
    sid = m.group(1)
    api = f"https://www.icloud.com/shortcuts/api/records/{sid}"
    req = urllib.request.Request(api, headers={'User-Agent': 'Mozilla/5.0'})
    data = json.load(urllib.request.urlopen(req, timeout=30))
    dl = data['fields']['shortcut']['value']['downloadURL']
    name = data['fields'].get('name', {}).get('value', sid)
    out = args.o or f"{name}.shortcut"
    urllib.request.urlretrieve(dl, out)
    print(f"已拉取: {out}  (来自 iCloud, 名称: {name})")
    print("提示: iCloud 分享的是已签名文件, 可直接 `shortcut-cli decompile` 查看或 import。")

def main():
    ap = argparse.ArgumentParser(prog='shortcut-cli', description='命令<->快捷指令双向转换 + iCloud拉取')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('info'); p.add_argument('file'); p.set_defaults(fn=cmd_info)
    p = sub.add_parser('decompile'); p.add_argument('file'); p.add_argument('-o'); p.add_argument('--pretty', action='store_true'); p.set_defaults(fn=cmd_decompile)
    p = sub.add_parser('compile', help='命令(JSON)->快捷指令，默认自动签名(--no-sign 关闭)')
    p.add_argument('spec'); p.add_argument('-o'); p.add_argument('--name')
    p.add_argument('--no-sign', dest='sign', action='store_false', help='不签名(默认会签名)')
    p.set_defaults(fn=cmd_compile, sign=True)
    p = sub.add_parser('sign'); p.add_argument('file'); p.add_argument('-o'); p.add_argument('--mode', default='anyone'); p.set_defaults(fn=cmd_sign)
    p = sub.add_parser('verify'); p.add_argument('file'); p.set_defaults(fn=cmd_verify)
    p = sub.add_parser('fetch'); p.add_argument('url'); p.add_argument('-o'); p.set_defaults(fn=cmd_fetch)
    p = sub.add_parser('import', help='(macOS)把 .shortcut 送进快捷指令App导入对话框，未签名自动先签名')
    p.add_argument('file'); p.set_defaults(fn=cmd_import)
    args = ap.parse_args()
    args.fn(args)

if __name__ == '__main__':
    main()
