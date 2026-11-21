"""Melvor Idle 2 简体中文补丁 / Simplified Chinese patch for Melvor Idle 2.

The game ships an unreleased official zh_CN.po draft inside Melvor2.exe. This script
  1. reads that draft (and en_GB.po) from YOUR installed copy of the game,
  2. applies the community corrections in translation/ to it,
  3. writes the result back into the same slot inside Melvor2.exe (backup kept),
  4. replaces the English source text of a few UI elements the game never translates
     (shop descriptions, combat area names, some astrology/combat labels), and
  5. writes override.cfg next to the exe so the game lists Chinese as a language.
No game files are stored in this repository.

usage (close the game first; Python 3.8+, standard library only):
  python melvor2_zh.py install [game_dir]   install / update the patch
  python melvor2_zh.py status  [game_dir]   show current state
  python melvor2_zh.py restore [game_dir]   put all original files back and remove override.cfg
  python melvor2_zh.py build   [game_dir]   only write the merged files to _work/, do not touch the game
"""
import sys, os, re, json, struct, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
EXE_NAME = 'Melvor2.exe'
ZH, EN = 'Locale/zh_CN.po', 'Locale/en_GB.po'
MARK = b'# melvor2-zh patched\n'
BACKUP_DIR = os.path.join(HERE, '_backup')
WORK_DIR = os.path.join(HERE, '_work')
OVERRIDE_CFG = ('[internationalization]\n\n'
                'locale/translations=PackedStringArray("res://Locale/en_GB.po", "res://Locale/zh_CN.po")\n')

try:
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def load_json(name):
    return json.load(open(os.path.join(HERE, 'translation', name), encoding='utf-8'))


# ---------------------------------------------------------------- game location
def steam_libraries():
    roots = []
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam')
        roots.append(winreg.QueryValueEx(k, 'SteamPath')[0])
    except Exception:
        pass
    roots += [r'C:\Program Files (x86)\Steam', os.path.expanduser('~/.steam/steam'),
              os.path.expanduser('~/.local/share/Steam')]
    libs = []
    for r in roots:
        vdf = os.path.join(r, 'steamapps', 'libraryfolders.vdf')
        if os.path.exists(vdf):
            libs += [p.replace('\\\\', '\\') for p in re.findall(r'"path"\s+"([^"]+)"', open(vdf, encoding='utf-8', errors='replace').read())]
        libs.append(r)
    return libs


def find_game(arg):
    cands = [arg] if arg else [os.path.join(l, 'steamapps', 'common', 'Melvor Idle 2') for l in steam_libraries()]
    for d in cands:
        if d and os.path.exists(os.path.join(d, EXE_NAME)):
            return os.path.abspath(d)
    sys.exit('找不到游戏目录，请把游戏目录作为参数传入 / Game folder not found; pass it as an argument, e.g.\n'
             '  python melvor2_zh.py install "D:\\SteamLibrary\\steamapps\\common\\Melvor Idle 2"')


# ---------------------------------------------------------------- PCK access
def find_pck(f):
    f.seek(0, 2); n = f.tell()
    chunk = 1 << 24; pos = 0; tail = b''
    while pos < n:
        f.seek(pos); data = tail + f.read(chunk); start = pos - len(tail)
        i = data.find(b'GDPC')
        while i != -1:
            if i + 24 <= len(data):
                fmt, maj, mi, pa, flags = struct.unpack('<5I', data[i + 4:i + 24])
                if maj == 4 and fmt in (3, 4) and mi < 50:
                    return start + i
            i = data.find(b'GDPC', i + 1)
        tail = data[-3:]; pos += chunk
    sys.exit('PCK header not found (unexpected game build)')


def pck_dir(exe):
    """Return {path: entry} for every file in the pack, plus 'godot': version string."""
    with open(exe, 'rb') as f:
        base = find_pck(f)
        f.seek(base + 4)
        fmt, maj, mi, pa, flags = struct.unpack('<5I', f.read(20))
        file_base, dir_off = struct.unpack('<QQ', f.read(16))
        if flags & 1:
            sys.exit('PCK directory is encrypted (unexpected game build)')
        f.seek(base + dir_off if flags & 2 else dir_off)
        cnt, = struct.unpack('<I', f.read(4))
        out = {}
        for _ in range(cnt):
            l, = struct.unpack('<I', f.read(4))
            p = f.read(l).rstrip(b'\0').decode('utf-8', 'replace')
            off, size = struct.unpack('<QQ', f.read(16)); md5 = f.read(16); fl, = struct.unpack('<I', f.read(4))
            out[p] = dict(path=p, abs=(base + file_base + off) if flags & 2 else off, size=size, md5=md5, enc=bool(fl & 1))
        for p in (ZH, EN):
            if p not in out:
                sys.exit(f'{p} not found in the game (did the developers remove the draft?)')
            if out[p]['enc']:
                sys.exit(f'{p} is encrypted (unexpected game build)')
        out['godot'] = f'{maj}.{mi}.{pa}'
        return out


def find_suffix(d, suffix):
    hits = [e for p, e in d.items() if p != 'godot' and p.endswith(suffix) and not e['enc']]
    return hits[0] if len(hits) == 1 else None


def read(exe, e):
    with open(exe, 'rb') as f:
        f.seek(e['abs']); return f.read(e['size'])


def backup_path(e):
    return os.path.join(BACKUP_DIR, f"{os.path.basename(e['path'])}.{e['md5'].hex()}")


def slot_state(exe, e):
    data = read(exe, e)
    if hashlib.md5(data).digest() == e['md5']:
        return 'original'
    if e['path'] == ZH:
        return 'patched' if data.startswith(MARK) else 'unknown'
    return 'patched' if os.path.exists(backup_path(e)) else 'unknown'


def original(exe, e):
    """Return the file's original bytes (from the exe if unpatched, else from our backup), or None."""
    data = read(exe, e)
    if hashlib.md5(data).digest() == e['md5']:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        if not os.path.exists(backup_path(e)):
            open(backup_path(e), 'wb').write(data)
        return data
    bp = backup_path(e)
    if os.path.exists(bp):
        data = open(bp, 'rb').read()
        if hashlib.md5(data).digest() == e['md5']:
            return data
    return None


# ---------------------------------------------------------------- PO handling
def parse(text):
    ents = []; cur = {}; key = None
    for line in text.split('\n'):
        if not line.strip():
            if cur: ents.append(cur); cur = {}; key = None
            continue
        if line.startswith('#'):
            continue
        m = re.match(r'(msgctxt|msgid_plural|msgid|msgstr(?:\[\d\])?) "(.*)"$', line)
        if m:
            key = m.group(1); cur[key] = m.group(2)
        elif line.startswith('"') and key:
            cur[key] += line[1:-1]
    if cur: ents.append(cur)
    return [e for e in ents if e.get('msgid')]


def po_unescape(s):
    return re.sub(r'\\(.)', lambda m: {'n': '\n', 't': '\t'}.get(m.group(1), m.group(1)), s)


def build(zh_text, en_text):
    overrides = load_json('overrides.json')
    extra = load_json('extra_translations.json')
    key = lambda e: (e.get('msgctxt', ''), e['msgid'])
    zh = parse(zh_text); en = parse(en_text)
    header = re.search(r'^msgid ""\nmsgstr ""\n(?:".*"\n)+', zh_text, re.M).group(0).rstrip('\n')
    zk = {key(e): e for e in zh}
    applied = 0; unmatched = []
    for o in overrides:
        e = zk.get((o.get('ctxt', ''), o['en']))
        if not e:
            unmatched.append(o['en']); continue
        e['msgstr' if 'msgstr' in e else 'msgstr[0]'] = o['zh']; applied += 1
    entries = list(zh); added = 0
    for e in en:
        if key(e) in zk:
            continue
        base = zk.get(('', e['msgid']))
        if base and e.get('msgctxt') == 'PluralName':
            entries.append({'msgctxt': 'PluralName', 'msgid': e['msgid'], 'msgid_plural': e['msgid_plural'],
                            'msgstr[0]': base.get('msgstr[0]', base.get('msgstr', ''))})
        elif e['msgid'] in extra:
            entries.append({'msgid': e['msgid'], 'msgstr': extra[e['msgid']]})
        else:
            continue
        added += 1
    q = lambda s: '"' + s + '"'
    out = [header]
    for e in entries:
        ls = []
        if 'msgctxt' in e: ls.append('msgctxt ' + q(e['msgctxt']))
        ls.append('msgid ' + q(e['msgid']))
        if 'msgid_plural' in e:
            ls.append('msgid_plural ' + q(e['msgid_plural']))
            ls.append('msgstr[0] ' + q(e.get('msgstr[0]', e.get('msgstr', ''))))
        else:
            ls.append('msgstr ' + q(e.get('msgstr', '')))
        out.append('\n'.join(ls))
    data = ('\n\n'.join(out) + '\n').encode('utf-8')
    print(f'修正 corrections applied: {applied}/{len(overrides)} | 补充 entries added: {added}')
    if unmatched:
        print(f'{len(unmatched)} 条修正未匹配（游戏文本已更新）/ corrections no longer match the game text:')
        for u in unmatched[:10]: print('   ', u[:70])
    # plain msgid -> msgstr table, used for the game-data replacements
    table = {po_unescape(e['msgid']): po_unescape(e.get('msgstr', e.get('msgstr[0]', '')))
             for e in entries if not e.get('msgctxt')}
    return data, table


# ---------------------------------------------------------------- source-text replacement
def patch_data(orig, size, table, cfg):
    """Replace English DisplayName/Description values of the configured object types with Chinese.
    Edits the JSON text in place (no re-serialisation), so everything else stays byte-identical."""
    text = orig.decode('utf-8')
    objs = json.loads(text).get('Objects', {})
    extra = cfg.get('data_extra', {})
    targets = {}; missing = []
    for t, field in cfg['data_fields']:
        for o in objs.get(t, []):
            v = o.get(field)
            if isinstance(v, str) and v:
                zh = extra.get(v) or table.get(v)
                if zh: targets[(field, v)] = zh
                else: missing.append(v)
    fields = sorted({f for _, f in cfg['data_fields']})
    count = [0]

    def rep(m):
        zh = targets.get((m.group(1), json.loads(m.group(3))))
        if zh is None:
            return m.group(0)
        count[0] += 1
        return f'"{m.group(1)}"{m.group(2)}' + json.dumps(zh, ensure_ascii=False)
    text = re.sub(r'"(%s)"(\s*:\s*)("(?:[^"\\]|\\.)*")' % '|'.join(fields), rep, text)
    data = text.encode('utf-8')
    if len(data) > size:   # strip indentation (JSON strings never contain raw newlines)
        data = re.sub(r'\n[ \t]+', '\n', text).encode('utf-8')
    if len(data) > size:
        return None, f'too big ({len(data)} > {size})'
    json.loads(data)   # must still be valid JSON
    return data + b' ' * (size - len(data)), f'{count[0]} texts replaced' + (f', {len(missing)} without translation' if missing else '')


def godot_string(s):
    b = s.encode('utf-8')
    return struct.pack('<II', 5, len(b) + 1) + b + b'\0'


def patch_scene(orig, pairs):
    """Same-length replacement of String values in a binary Godot scene (.scn)."""
    data = orig; done = 0; skipped = []
    for en, zh in pairs:
        eb, zb = en.encode('utf-8'), zh.encode('utf-8')
        if len(zb) > len(eb):
            skipped.append(en); continue
        old, new = godot_string(en), godot_string(zh + ' ' * (len(eb) - len(zb)))
        n = data.count(old)
        if n == 0:
            skipped.append(en); continue
        data = data.replace(old, new); done += n
    assert len(data) == len(orig)
    return data, f'{done} texts replaced' + (f', not found: {skipped}' if skipped else '')


def source_text_jobs(exe, d, table):
    """Yield (entry, new_bytes or None, message) for every file the source-text replacement touches."""
    cfg = load_json('source_text.json')
    e = d.get(cfg['data_file'])
    if not e or e['enc']:
        yield None, None, f"{cfg['data_file']}: not found, skipped"
    else:
        orig = original(exe, e)
        if orig is None:
            yield e, None, f"{e['path']}: modified by something else and no backup, skipped"
        else:
            data, msg = patch_data(orig, e['size'], table, cfg)
            yield e, data, f"{e['path']}: {msg}"
    for suffix, pairs in cfg['scenes'].items():
        e = find_suffix(d, suffix)
        if not e:
            yield None, None, f'*{suffix}: not found, skipped'; continue
        orig = original(exe, e)
        if orig is None:
            yield e, None, f"{suffix}: modified by something else and no backup, skipped"; continue
        data, msg = patch_scene(orig, pairs)
        yield e, data, f'{suffix.lstrip("-")}: {msg}'


def source_text_entries(d):
    cfg = load_json('source_text.json')
    es = [d.get(cfg['data_file'])] + [find_suffix(d, s) for s in cfg['scenes']]
    return [e for e in es if e and not e['enc']]


# ---------------------------------------------------------------- commands
def write_slot(exe, e, data):
    assert len(data) == e['size']
    try:
        with open(exe, 'r+b') as f:
            f.seek(e['abs']); f.write(data)
    except PermissionError:
        sys.exit('无法写入 Melvor2.exe，请先关闭游戏 / Cannot write Melvor2.exe — close the game first.')


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('install', 'status', 'restore', 'build'):
        sys.exit(__doc__)
    cmd = sys.argv[1]
    game = find_game(sys.argv[2] if len(sys.argv) > 2 else None)
    exe = os.path.join(game, EXE_NAME); cfg = os.path.join(game, 'override.cfg')
    d = pck_dir(exe); e = d[ZH]
    st = slot_state(exe, e)
    print(f'game: {game}\ngodot {d["godot"]} | zh_CN.po: {st} | override.cfg: {"yes" if os.path.exists(cfg) else "no"}')
    others = source_text_entries(d)
    print('source text: ' + ', '.join(f"{os.path.basename(x['path']).split('-')[-1]} {slot_state(exe, x)}" for x in others))
    if cmd == 'status':
        return
    if cmd == 'restore':
        for x in [e] + others:
            if slot_state(exe, x) == 'patched':
                bp = backup_path(x)
                if not os.path.exists(bp):
                    sys.exit('找不到备份，请用 Steam「验证游戏文件完整性」还原 / No backup; verify game files in Steam instead.')
                write_slot(exe, x, open(bp, 'rb').read())
        if os.path.exists(cfg) and open(cfg, encoding='utf-8').read() == OVERRIDE_CFG:
            os.remove(cfg)
        print('已还原 / restored')
        return
    draft = original(exe, e)
    if draft is None:
        sys.exit('游戏里的中文草稿已被修改，但找不到对应的备份。请在 Steam 里「验证游戏文件完整性」后重试。\n'
                 'The draft in the exe is already modified and no matching backup was found. '
                 'Verify the game files in Steam, then run install again.')
    data, table = build(draft.decode('utf-8'), read(exe, d[EN]).decode('utf-8'))
    jobs = list(source_text_jobs(exe, d, table))
    for _, _, msg in jobs:
        print('  ' + msg)
    if cmd == 'build':
        os.makedirs(WORK_DIR, exist_ok=True)
        open(os.path.join(WORK_DIR, 'zh_CN.po'), 'wb').write(data)
        for x, new, _ in jobs:
            if new is not None:
                open(os.path.join(WORK_DIR, os.path.basename(x['path'])), 'wb').write(new)
        print('written to', WORK_DIR)
        return
    data = MARK + data
    if len(data) > e['size']:
        sys.exit(f'merged file too big for the slot ({len(data)} > {e["size"]})')
    write_slot(exe, e, data + b'\n' * (e['size'] - len(data)))
    if slot_state(exe, e) != 'patched':
        sys.exit('verification failed')
    for x, new, _ in jobs:
        if new is not None:
            write_slot(exe, x, new)
            if read(exe, x) != new:
                sys.exit(f"verification failed: {x['path']}")
    if os.path.exists(cfg) and open(cfg, encoding='utf-8').read() != OVERRIDE_CFG:
        os.replace(cfg, cfg + '.bak'); print('existing override.cfg moved to override.cfg.bak')
    open(cfg, 'w', encoding='utf-8', newline='\n').write(OVERRIDE_CFG)
    print('安装完成：启动游戏后在语言选项里选择中文。/ Done: start the game and choose Chinese in the language options.')


if __name__ == '__main__':
    main()
