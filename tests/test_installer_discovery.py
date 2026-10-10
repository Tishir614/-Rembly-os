"""Exercise discovery with fake transports; never contact USB hardware."""
import subprocess
import unittest
from pathlib import Path

CORE = (Path(__file__).resolve().parents[1] / 'rembly-install-core.sh').read_text()
FUNCTIONS = CORE[CORE.index('adb_bounded() {'):CORE.index('\nSTATE_DIR=')]
BASE = r'''
set -Eeuo pipefail
EXPECTED_PRODUCT=K37MV1_BSP
WAIT_SECONDS=4
step() { :; }; sub() { :; }; ok() { :; }; warn() { :; }
die() { echo "$*" >&2; exit 1; }
sleep() { SECONDS=$((SECONDS+2)); }
'''

class DiscoveryTests(unittest.TestCase):
    def run_case(self, mocks):
        return subprocess.run(['bash', '-c', BASE + FUNCTIONS + '\n' + mocks],
                              capture_output=True, text=True, timeout=5)

    def test_fastboot_present(self):
        r = self.run_case('''
list_fastboot() { echo tablet; }
timeout() { :; }
wait_for_fastboot
[[ "$FB_SERIAL" == tablet ]]
''')
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_late_adb_then_fastboot(self):
        r = self.run_case('''
ready=0
list_fastboot() { if (( ready )); then echo tablet; fi; }
timeout() { if (( SECONDS >= 2 && ! ready )); then printf 'List of devices attached\ntablet device\n'; fi; }
probe_existing_adb() { ready=1; }
wait_for_fastboot
[[ "$FB_SERIAL" == tablet && "$ready" == 1 ]]
''')
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_multiple_transports_rejected(self):
        r = self.run_case('''
list_fastboot() { echo tablet; }
timeout() { printf 'List of devices attached\nother device\n'; }
wait_for_fastboot
''')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('несколько', r.stderr)

    def test_absent_device_timeout(self):
        r = self.run_case('''
list_fastboot() { :; }
timeout() { :; }
wait_for_fastboot
''')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('за 4 с', r.stderr)

    def test_wrong_adb_model_never_rebooted(self):
        r = self.run_case('''
list_adb() { echo tablet; }
adb_bounded() { :; }
timeout() { echo other_model; }
probe_existing_adb
''')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('не подтверждено', r.stderr)

    def test_recovery_is_eligible_but_unauthorized_is_not(self):
        r = self.run_case('''
timeout() { printf 'List of devices attached\na recovery\nb unauthorized\nc offline\nd device\n'; }
[[ "$(list_adb)" == $'a\\nd' ]]
''')
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_locked_bootloader_rejected(self):
        r = self.run_case('''
fbget() { if [[ "$1" == product ]]; then echo K37MV1_BSP; else echo no; fi; }
verify_fastboot_device
''')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('Bootloader закрыт', r.stderr)

    def test_swapped_adb_rejected(self):
        r = self.run_case('''
HAD_ADB_PROBE=1
ADB_SERIAL=original
list_adb() { echo replacement; }
adb_bounded() { :; }
probe_existing_adb
''')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('сменилось', r.stderr)

if __name__ == '__main__':
    unittest.main()
