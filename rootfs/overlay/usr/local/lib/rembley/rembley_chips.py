"""Chip awareness for the A73's connectivity hardware (Wi-Fi, Bluetooth, GPS, FM, cellular modem).
Collects what the KERNEL was built for (/proc/config.gz or the shipped subset of the stock config), what the running kernel actually registered
(device nodes, sysfs, dmesg), which userspace helpers and firmware are present, and turns that into one verdict per function with the next step.
Nothing here writes anywhere except `adapt()` (symlinks inside /etc/firmware and /etc/rembley/chips.conf)."""
import glob, gzip, os, re, subprocess

ROOT = os.environ.get('REMBLEY_CHIPS_ROOT', '')
CAPS_FALLBACK = '/usr/share/rembley/kernel-caps.txt'
CHIP_RE = re.compile(r'(?<![0-9A-Za-z])(?:MT)?([678]\d{3}[A-Za-z]?)(?![0-9])', re.I)       # 6735, 6737, 6625L, 7668 ...
KNOWN_CONNSYS = {'6735', '6737', '6625', '6580', '6572', '6582', '6592', '6752', '6755', '6797', '6630', '6628', '6620', '6632'}


def rd(p, d=''):
    try: return open(ROOT + p, errors='replace').read()
    except OSError: return d


def sh(cmd, t=10):
    try: return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=t).stdout
    except Exception: return ''


def kernel_config():
    """dict CONFIG_X -> 'y' / '"string"' / 'n' (from /proc/config.gz, else the shipped subset of the stock config); 'source' key says which."""
    txt, src = '', 'unknown'
    try:
        txt = gzip.open(ROOT + '/proc/config.gz', 'rt', errors='replace').read(); src = '/proc/config.gz (the running kernel)'
    except OSError:
        txt = rd(CAPS_FALLBACK); src = 'stock kernel config shipped with Rembley (the kernel was built from it)' if txt else 'unknown'
    cfg = {'source': src}
    for l in txt.splitlines():
        m = re.match(r'^(CONFIG_\w+)=(.*)$', l)
        if m: cfg[m.group(1)] = m.group(2)
        else:
            m = re.match(r'^# (CONFIG_\w+) is not set', l)
            if m: cfg[m.group(1)] = 'n'
    return cfg


def on(cfg, k): return cfg.get(k) in ('y', 'm')


def chip_ids(cfg):
    ids = {}
    for k in ('CONFIG_MTK_COMBO_CHIP', 'CONFIG_MTK_FM_CHIP'):
        v = cfg.get(k, '').strip('"')
        m = CHIP_RE.search(v)
        if m: ids.setdefault(m.group(1), []).append('%s=%s' % (k[7:], v))
    for k, v in cfg.items():
        if k.startswith('CONFIG_MTK_COMBO_CHIP_') and v == 'y':
            m = CHIP_RE.search(k)
            if m: ids.setdefault(m.group(1), []).append(k[7:])
    dm = sh('dmesg 2>/dev/null | grep -iE "wmt|conn|consys|chip ?id|stp|fm_|gps|mt6" | tail -400')
    for l in dm.splitlines():
        if re.search(r'chip ?id|chipid|hw ?ver|consys|WMT-DETECT|COMBO', l, re.I):
            for m in CHIP_RE.finditer(l):
                if m.group(1) in KNOWN_CONNSYS: ids.setdefault(m.group(1), []).append('dmesg: ' + l.strip()[:80])
    soc = rd('/proc/cpuinfo'); m = re.search(r'Hardware\s*:\s*(.+)', soc)
    if m and CHIP_RE.search(m.group(1)): ids.setdefault(CHIP_RE.search(m.group(1)).group(1), []).append('SoC: ' + m.group(1))
    return ids


def have(*globs): return any(glob.glob(ROOT + g) for g in globs)


def nodes():
    d = {n: have('/dev/' + n, '/sys/class/misc/' + n) for n in ('wmtdetect', 'stpwmt', 'wmtWifi', 'stpbt', 'stpgps', 'fm', 'gps')}
    d.update({'ccci': have('/dev/ccci*', '/dev/ttyC0', '/sys/class/misc/ccci*'), 'hci': have('/sys/class/bluetooth/hci*'), 'wlan0': have('/sys/class/net/wlan0'),
              'ppp': have('/sys/class/net/ppp0')})
    return d


def firmware_files():
    out = []
    for d in ('/vendor/firmware', '/system/etc/firmware', '/vendor/etc/firmware', '/etc/firmware', '/system/etc/wifi', '/vendor/etc/wifi'):
        for f in glob.glob(ROOT + d + '/*'):
            if os.path.isfile(f): out.append(f[len(ROOT):])
    return sorted(set(out))


def fw_groups(files, ids):
    """Group firmware files by the chip number in their name: {'6735': [...], 'other:6620': [...], 'neutral': [...]}.
    Only numbers of known connectivity chips count (a random number in a file name does not make it chip specific)."""
    mine = {i[:4] for i in ids}; known = KNOWN_CONNSYS | mine; g = {}
    for f in files:
        key = 'neutral'
        for m in CHIP_RE.finditer(os.path.basename(f)):
            c = m.group(1)[:4]
            if c in known: key = c if c in mine else 'other:' + c; break
        g.setdefault(key, []).append(f)
    return g


def functions():
    cfg = kernel_config(); ids = chip_ids(cfg); nd = nodes(); fw = firmware_files(); groups = fw_groups(fw, ids)
    helpers = {n: have('/system/bin/' + n, '/vendor/bin/' + n) for n in ('wmt_launcher', 'wmt_loader', 'linker', 'mnld', 'nvram_daemon', 'rild', 'mtkrild')}
    mine = {i[:4] for i in ids}; fwmatch = [f for k, v in groups.items() if k in mine or k == 'neutral' for f in v]
    res = []

    def add(name, chip, state, why, fix=''): res.append({'function': name, 'chip': chip, 'state': state, 'why': why, 'fix': fix})
    combo = cfg.get('CONFIG_MTK_COMBO_CHIP', '?').strip('"')
    # ---- Wi-Fi
    if not (on(cfg, 'CONFIG_MTK_COMBO_WIFI') and on(cfg, 'CONFIG_CFG80211')): add('Wi-Fi', combo, 'BLOCKED', 'в ядре нет драйвера Wi-Fi комбо-чипа/cfg80211', 'нужна пересборка ядра')
    elif nd['wlan0']: add('Wi-Fi', combo, 'RUNNING', 'интерфейс wlan0 есть')
    elif not (nd['wmtdetect'] or nd['stpwmt'] or nd['wmtWifi']): add('Wi-Fi', combo, 'NO-DRIVER-NODE', 'ядро собрано с драйвером, но узлы /dev/wmt* не появились (CONSYS не зарегистрирован)', 'rembley-chips --json; dmesg | grep -i wmt')
    elif not (helpers['wmt_launcher'] and helpers['linker']): add('Wi-Fi', combo, 'NEED-DRIVERS', 'нет wmt_launcher/linker (проприетарные файлы вашей прошивки)', 'rembley-drivers install')
    elif not any(re.search(r'WMT_SOC|patch', os.path.basename(f), re.I) for f in fwmatch): add('Wi-Fi', combo, 'NEED-FIRMWARE', 'нет WMT_SOC.cfg/patch для вашего чипа', 'rembley-drivers install')
    else: add('Wi-Fi', combo, 'READY', 'драйвер, помощники и прошивка на месте, wlan0 ещё не поднят', 'rembley-net auto')
    # ---- Bluetooth
    if not on(cfg, 'CONFIG_BT'): add('Bluetooth', combo, 'BLOCKED', 'в стоковом ядре выключен CONFIG_BT: стека Bluetooth нет, чип доступен только через /dev/stpbt без HCI', 'нужна пересборка ядра с CONFIG_BT/BT_HCIUART (исходников ядра нет в проекте)')
    elif nd['hci']: add('Bluetooth', combo, 'RUNNING', 'hci0 есть')
    else: add('Bluetooth', combo, 'NEED-DRIVERS', 'стек BT в ядре есть, но hci0 не создан', 'rembley-drivers install; rembley-net bt-up')
    # ---- GPS
    if not (on(cfg, 'CONFIG_MTK_COMBO_GPS') or on(cfg, 'CONFIG_MTK_GPS')): add('GPS', combo, 'BLOCKED', 'в ядре нет драйвера GPS', 'нужна пересборка ядра')
    elif not (nd['stpgps'] or nd['gps']): add('GPS', combo, 'NO-DRIVER-NODE', 'узлов /dev/stpgps, /dev/gps нет: GPS включается после старта WMT', 'сначала Wi-Fi: rembley-net auto')
    elif not helpers['mnld']: add('GPS', combo, 'NEED-DRIVERS', 'нет демона mnld из прошивки', 'rembley-drivers install')
    else: add('GPS', combo, 'READY', 'драйвер и mnld есть; для Linux-программ нужен мост NMEA (gpsd) — не настроен автоматически', 'ручная настройка')
    # ---- FM
    fmchip = cfg.get('CONFIG_MTK_FM_CHIP', '?').strip('"')
    if not on(cfg, 'CONFIG_MTK_FMRADIO'): add('FM-радио', fmchip, 'BLOCKED', 'в ядре нет драйвера FM', 'нужна пересборка ядра')
    elif not nd['fm']: add('FM-радио', fmchip, 'NO-DRIVER-NODE', 'нет /dev/fm (появляется после старта WMT); в Linux нет готового приложения для этого интерфейса', 'сначала Wi-Fi: rembley-net auto')
    else: add('FM-радио', fmchip, 'READY', 'узел /dev/fm есть; приложения под него в Ubuntu нет — только ручная работа через ioctl', 'нет авто-настройки')
    # ---- modem
    md = cfg.get('CONFIG_MTK_MD1_SUPPORT', '?')
    if not on(cfg, 'CONFIG_MTK_CCCI_DEVICES'): add('Сотовый модем', 'MD1(%s)' % md, 'BLOCKED', 'в ядре нет CCCI', 'нужна пересборка ядра')
    elif not nd['ccci']: add('Сотовый модем', 'MD1(%s)' % md, 'NO-DRIVER-NODE', 'узлы ccci/ttyC0 не появились (модем не стартовал; у планшета может не быть SIM-модуля)', 'rembley-net modem-probe')
    elif nd['ppp']: add('Сотовый модем', 'MD1(%s)' % md, 'RUNNING', 'ppp0 есть')
    elif not any(re.match(r'md1|modem', os.path.basename(f), re.I) for f in fw): add('Сотовый модем', 'MD1(%s)' % md, 'NEED-FIRMWARE', 'нет прошивки модема md1*', 'rembley-drivers install')
    else: add('Сотовый модем', 'MD1(%s)' % md, 'READY', 'узлы и прошивка есть; настройка APN и AT-команды вручную (после Wi-Fi)', 'rembley-net modem-probe')
    return {'kernel_config_source': cfg['source'], 'chip_ids': ids, 'nodes': nd, 'helpers': helpers, 'firmware_groups': {k: len(v) for k, v in groups.items()},
            'firmware_other_chips': sorted(k for k in groups if k.startswith('other:')), 'functions': res, '_groups': groups}


def adapt(log=print):
    """Make the firmware directory match THIS chip: link the files of the detected chip(s) + the chip-neutral ones into /etc/firmware and note
    which files in the Android image belong to other chips (left alone). Writes /etc/rembley/chips.conf."""
    r = functions(); g = r.pop('_groups'); ids = r['chip_ids']; n = 0
    os.makedirs(ROOT + '/etc/firmware', exist_ok=True)
    for k, files in g.items():
        if k.startswith('other:'): continue
        for f in files:
            dst = ROOT + '/etc/firmware/' + os.path.basename(f)
            if not os.path.lexists(dst):
                os.symlink(f, dst); n += 1
    os.makedirs(ROOT + '/etc/rembley', exist_ok=True)
    with open(ROOT + '/etc/rembley/chips.conf', 'w') as fh:
        fh.write('# written by rembley-chips adapt\nCHIPS="%s"\nWIFI_STATE=%s\nBT_STATE=%s\n' % (' '.join(sorted(ids)), *[next((x['state'] for x in r['functions'] if x['function'] == f), '?') for f in ('Wi-Fi', 'Bluetooth')]))
    log('chip(s) %s: linked %d firmware files; %d files belong to other chips: %s' % (', '.join(sorted(ids)) or 'unknown', n, sum(len(g[k]) for k in g if k.startswith('other:')), ', '.join(r['firmware_other_chips']) or '-'))
    return r
