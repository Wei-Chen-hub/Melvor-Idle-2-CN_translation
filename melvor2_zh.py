"""Melvor Idle 2 简体中文补丁 / Simplified Chinese patch for Melvor Idle 2.

The game ships an unreleased official zh_CN.po draft inside Melvor2.exe. This script
  1. reads that draft (and en_GB.po) from YOUR installed copy of the game,
  2. applies the community corrections in translation/ to it,
  3. writes the result back into the same slot inside Melvor2.exe (backup kept), and
  4. writes override.cfg next to the exe so the game lists Chinese as a language.
No game files are stored in this repository.

usage (close the game first; Python 3.8+, standard library only):
  python melvor2_zh.py install [game_dir]   install / update the patch
  python melvor2_zh.py status  [game_dir]   show current state
  python melvor2_zh.py restore [game_dir]   put the original draft back and remove override.cfg
  python melvor2_zh.py build   [game_dir]   only write the merged po to _work/zh_CN.po
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
            if p in (ZH, EN):
                out[p] = dict(abs=(base + file_base + off) if flags & 2 else off, size=size, md5=md5, enc=bool(fl & 1))
        for p in (ZH, EN):
            if p not in out:
                sys.exit(f'{p} not found in the game (did the developers remove the draft?)')
            if out[p]['enc']:
                sys.exit(f'{p} is encrypted (unexpected game build)')
        out['godot'] = f'{maj}.{mi}.{pa}'
        return out


def read(exe, e):
    with open(exe, 'rb') as f:
        f.seek(e['abs']); return f.read(e['size'])


def slot_state(data, e):
    if hashlib.md5(data).digest() == e['md5']:
        return 'original'
    return 'patched' if data.startswith(MARK) else 'unknown'


def backup_path(e):
    return os.path.join(BACKUP_DIR, f"zh_CN.po.{e['md5'].hex()}")


def original_draft(exe, d):
    """Return the official draft bytes, from the exe if unpatched, else from our backup."""
    e = d[ZH]; data = read(exe, e); st = slot_state(data, e)
    if st == 'original':
        os.makedirs(BACKUP_DIR, exist_ok=True)
        if not os.path.exists(backup_path(e)):
            open(backup_path(e), 'wb').write(data)
        return data
    bp = backup_path(e)
    if os.path.exists(bp) and hashlib.md5(open(bp, 'rb').read()).digest() == e['md5']:
        return open(bp, 'rb').read()
    sys.exit('游戏里的中文草稿已被修改，但找不到对应的备份。请在 Steam 里「验证游戏文件完整性」后重试。\n'
             'The draft in the exe is already modified and no matching backup was found. '
             'Verify the game files in Steam, then run install again.')


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


def build(zh_text, en_text):
    overrides = json.load(open(os.path.join(HERE, 'translation', 'overrides.json'), encoding='utf-8'))
    extra = json.load(open(os.path.join(HERE, 'translation', 'extra_translations.json'), encoding='utf-8'))
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
    return data


# ---------------------------------------------------------------- commands
def write_slot(exe, e, data):
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
    st = slot_state(read(exe, e), e)
    print(f'game: {game}\ngodot {d["godot"]} | zh_CN.po: {st} | override.cfg: {"yes" if os.path.exists(cfg) else "no"}')
    if cmd == 'status':
        return
    if cmd == 'restore':
        bp = backup_path(e)
        if st == 'patched':
            if not os.path.exists(bp):
                sys.exit('找不到备份，请用 Steam「验证游戏文件完整性」还原 / No backup; verify game files in Steam instead.')
            write_slot(exe, e, open(bp, 'rb').read())
        if os.path.exists(cfg) and open(cfg, encoding='utf-8').read() == OVERRIDE_CFG:
            os.remove(cfg)
        print('已还原 / restored')
        return
    zh_text = original_draft(exe, d).decode('utf-8')
    en_text = read(exe, d[EN]).decode('utf-8')
    data = build(zh_text, en_text)
    if cmd == 'build':
        os.makedirs(WORK_DIR, exist_ok=True)
        open(os.path.join(WORK_DIR, 'zh_CN.po'), 'wb').write(data)
        print('written', os.path.join(WORK_DIR, 'zh_CN.po'))
        return
    data = MARK + data
    if len(data) > e['size']:
        sys.exit(f'merged file too big for the slot ({len(data)} > {e["size"]})')
    write_slot(exe, e, data + b'\n' * (e['size'] - len(data)))
    if slot_state(read(exe, e), e) != 'patched':
        sys.exit('verification failed')
    if os.path.exists(cfg) and open(cfg, encoding='utf-8').read() != OVERRIDE_CFG:
        os.replace(cfg, cfg + '.bak'); print('existing override.cfg moved to override.cfg.bak')
    open(cfg, 'w', encoding='utf-8', newline='\n').write(OVERRIDE_CFG)
    print('安装完成：启动游戏后在语言选项里选择中文。/ Done: start the game and choose Chinese in the language options.')


if __name__ == '__main__':
    main()
