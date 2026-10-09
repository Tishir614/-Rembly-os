"""Offline tests of rembly_servers.py (command lines, quick connect, validation, store). Run: python3 tests/test_rembly_servers.py"""
import os, stat, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, '..', 'rootfs', 'overlay', 'usr', 'local', 'lib', 'rembly'))
os.environ['REMBLY_CONFIG_DIR'] = tempfile.mkdtemp(); os.environ['HOME'] = tempfile.mkdtemp()
import rembly_servers as s
ok = fail = 0


def check(n, c, extra=''):
    global ok, fail
    if c: ok += 1; print('  OK  ', n)
    else: fail += 1; print('  FAIL', n, extra)


for t, exp in (('root@10.0.0.5', 'root@10.0.0.5:22'), ('user@host:2222', 'user@host:2222'), ('example.org', 'example.org:22'), ('ssh://bob@h.io:2200', 'bob@h.io:2200'), ('[::1]:2022', '::1:2022'), ('bad host!', None), ('', None), ('a@b:99999', None)):
    c = s.parse_quick(t); got = None if c is None else '%s%s:%d' % ((c['user'] + '@') if c['user'] else '', c['host'], c['port']); check('parse_quick(%r)' % t, got == exp, got)
c = s.parse_quick('root@10.0.0.5:2222'); c.update(key='~/.ssh/id_ed25519', extra='-L 8080:localhost:80', startup='tmux new -As main'); cmd = s.build_command(c)
check('ssh command', cmd[0] == 'ssh' and cmd[-2] == 'root@10.0.0.5' and cmd[-1] == 'tmux new -As main' and '-t' in cmd and '-L' in cmd and 'IdentitiesOnly=yes' in cmd and 'ServerAliveInterval=30' in cmd and 'StrictHostKeyChecking=accept-new' in cmd)
check('shell metacharacters in host rejected', s.validate(s.new_conn(name='x', host='h; rm -rf /', user='u')) != [])
check('user with a space rejected', s.validate(s.new_conn(name='x', host='h', user='a b')) != [])
check('serial', s.build_command(s.new_conn(name='r', kind='serial', device='/dev/ttyUSB1', baud='9600')) == ['picocom', '-b', '9600', '/dev/ttyUSB1'])
r = s.build_command(s.new_conn(name='w', kind='rdp', host='10.1.1.2', port=3389, user='admin', domain='CORP', size='1280x720'))
check('rdp (certificate is trusted on first use, never ignored)', r[0] == 'xfreerdp' and '/cert:tofu' in r and '/cert:ignore' not in r and '/size:1280x720' in r and '/d:CORP' in r)
check('vnc', s.build_command(s.new_conn(name='v', kind='vnc', host='srv', port=5901))[:2] == ['xtightvncviewer', 'srv::5901'])
check('telnet', s.build_command(s.new_conn(name='t', kind='telnet', host='sw', port=23)) == ['telnet', 'sw', '23'])
s.save([c]); check('servers.json is 0600 and holds no password', stat.S_IMODE(os.stat(s.store_path()).st_mode) == 0o600 and 'password' not in open(s.store_path()).read().lower())
check('mount_dir never escapes ~/Servers', all(os.path.dirname(s.mount_dir(s.new_conn(name=n))) == os.path.join(os.environ['HOME'], 'Servers') for n in ('..', '.', 'a/../b', 'Мой сервер')))
print('\n%d passed, %d failed' % (ok, fail)); sys.exit(1 if fail else 0)
