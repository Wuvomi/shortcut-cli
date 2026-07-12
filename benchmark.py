#!/usr/bin/env python3
"""
benchmark.py — reproducible round-trip integrity test for shortcut-cli.

Runs the full loop on a shortcut and reports whether content survives, whether
it's reproducible, and whether the multi-round result is a stable fixed point:

    fetch (if iCloud URL) -> decompile -> compile -> decompile -> compile
                          -> sign -> decompile-signed
    then DEEP VALUE comparison (ignores key order & byte encoding; that's the
    only correct definition of "no content loss").

Usage:
    python3 benchmark.py <file.shortcut | https://www.icloud.com/shortcuts/ID>
"""
import plistlib, subprocess, os, sys, json, base64, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, 'shortcut_cli.py')

def cli(*a):
    return subprocess.run(['python3', CLI, *a], capture_output=True, text=True,
                          env={**os.environ, 'SHORTCUT_CLI_LANG': 'en'})

def _restore(o):
    if isinstance(o, dict) and list(o.keys()) == ['__bytes_b64__']:
        return base64.b64decode(o['__bytes_b64__'])
    return o

def load(path):
    raw = open(path, 'rb').read()
    if raw[:4] == b'AEA1':               # signed -> decode via the tool
        j = path + '.json'
        cli('decompile', path, '-o', j)
        return json.load(open(j), object_hook=_restore)
    return plistlib.loads(raw)

def cf_modes(actions, ident):
    return [a['WFWorkflowActionParameters'].get('WFControlFlowMode')
            for a in actions if a['WFWorkflowActionIdentifier'] == ident]

def bench(src):
    with tempfile.TemporaryDirectory() as td:
        orig = os.path.join(td, 'orig.shortcut')
        if src.startswith('http'):
            cli('fetch', src, '-o', orig)
        else:
            import shutil; shutil.copy(src, orig)

        def p(n): return os.path.join(td, n)
        cli('decompile', orig, '-o', p('j1.json'))
        cli('compile', p('j1.json'), '-o', p('r1.shortcut'), '--no-sign')
        cli('decompile', p('r1.shortcut'), '-o', p('j2.json'))
        cli('compile', p('j2.json'), '-o', p('r2.shortcut'), '--no-sign')
        cli('decompile', p('r2.shortcut'), '-o', p('j3.json'))

        o = plistlib.loads(open(orig, 'rb').read())
        r = plistlib.loads(open(p('r1.shortcut'), 'rb').read())
        oa, ra = o['WFWorkflowActions'], r['WFWorkflowActions']
        j2, j3 = open(p('j2.json')).read(), open(p('j3.json')).read()
        r1b, r2b = open(p('r1.shortcut'), 'rb').read(), open(p('r2.shortcut'), 'rb').read()

        signed = p('s.signed.shortcut')
        cli('compile', p('j1.json'), '-o', p('s.shortcut'))     # signs by default
        ds = load(signed) if os.path.exists(signed) else None

        n = len(oa)
        checks = [
            ('actions preserved (count)',        len(oa) == len(ra), f'{len(ra)}/{n}'),
            ('every action deep-equal',          len(oa) == len(ra) and all(oa[i] == ra[i] for i in range(n)), ''),
            ('all top-level fields equal',        {k: o[k] for k in o if k != 'WFWorkflowActions'} == {k: r[k] for k in r if k != 'WFWorkflowActions'}, ''),
            ('original == recompiled (deep)',    o == r, ''),
            ('multi-round fixed point (j2==j3)', j2 == j3, ''),
            ('compile deterministic (r1==r2)',   r1b == r2b, ''),
        ]
        for ident, nm in [('is.workflow.actions.conditional', 'if'),
                          ('is.workflow.actions.repeat.count', 'repeat')]:
            om = cf_modes(oa, ident)
            if om:
                checks.append((f'control-flow "{nm}" modes preserved', om == cf_modes(ra, ident), str(om)))
        if ds is not None:
            checks.append(('actions survive signing', oa == ds['WFWorkflowActions'], f"{len(ds['WFWorkflowActions'])}/{n}"))
            sdiff = [k for k in set(o) | set(ds) if o.get(k) != ds.get(k)]
            checks.append(('signing changes only client-version', sdiff == ['WFWorkflowClientVersion'], ','.join(sdiff)))

        return n, checks

def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    n, checks = bench(sys.argv[1])
    print(f"\n  shortcut: {n} actions\n  " + "-" * 52)
    allok = True
    for name, ok, note in checks:
        allok &= ok
        mark = 'PASS' if ok else 'FAIL'
        print(f"  [{mark}] {name:<38} {note}")
    print("  " + "-" * 52)
    print(f"  => {'ALL PASS — content losslessly preserved' if allok else 'FAILURES ABOVE'}\n")
    sys.exit(0 if allok else 1)

if __name__ == '__main__':
    main()
