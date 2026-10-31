"""Asset-free regressions for tests/soak_parity_check.py."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = '''USERCMD_CHECK ticks=30 elapsed=480 origin=1.000000,2.000000,3.000000 velocity=0.000000,0.000000,0.000000 ground=1 crouch=0 health=100 clip=8 ammo=20 ready=1 weapon=weapon_shotgun view=0.000000,90.000000,0.000000 noclip=0
PROJECTILE_ITEM index=7 def=projectile_bullet_shotgun hidden=0 origin=-1.500000,2.250000,3.000000 velocity=0.000000,0.000000,0.000000
RENDER_STATE game_time=3360 render_time=3360 frame=210 random_seed=-524420392
'''


def run(native, web):
    with tempfile.TemporaryDirectory() as d:
        n, w = Path(d) / 'n.txt', Path(d) / 'w.txt'
        n.write_text(native, encoding='utf-8')
        w.write_text(web, encoding='utf-8')
        return subprocess.run([sys.executable, str(HERE / 'soak_parity_check.py'), str(n), str(w)],
                              capture_output=True, text=True)


class SoakParityCheck(unittest.TestCase):
    def test_identical_logs_pass(self):
        self.assertEqual(run(LOG, LOG).returncode, 0)

    def test_seed_divergence_fails(self):
        r = run(LOG, LOG.replace('-524420392', '-524420391'))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('STATE DIVERGENCE', r.stdout)

    def test_projectile_divergence_fails(self):
        r = run(LOG, LOG.replace('origin=-1.500000', 'origin=-1.500001'))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('PROJECTILE DIVERGENCE', r.stdout)

    def test_player_divergence_fails(self):
        r = run(LOG, LOG.replace('health=100', 'health=99'))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('PLAYER DIVERGENCE', r.stdout)

    def test_missing_checkpoints_fail(self):
        self.assertNotEqual(run(LOG, LOG.split('RENDER_STATE')[0] + 'RENDER_STATE game_time=1 render_time=1 frame=1 random_seed=1\n' * 2).returncode, 0)


if __name__ == '__main__':
    unittest.main()
