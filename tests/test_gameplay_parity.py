"""Asset-free regression checks for the real-run comparison tool."""
import copy
from pathlib import Path
import tempfile
import unittest

from gameplay_parity_check import checkpoints, compare


class ParityChecks(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(ticks=1, elapsed=16, origin=(float(i), 0., float(i)),
                          velocity=(0., 0., 0.), ground=int(i != 2),
                          crouch=int(i == 3), health=100, clip=clip, ammo=20,
                          ready=1, noclip=0)
                     for i, clip in enumerate([12, 11, 10, 10, 12])]

    def read(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'console.txt'
            path.write_text(text)
            return checkpoints(path)

    def test_wrapped_native_and_unwrapped_web(self):
        text = ('USERCMD_CHECK ticks=1 elapsed=16 origin=0.000000,0.000000,0.000000 '
                'velocity=0.000000,0.000000,0.000000 ground=1 crouch=0 health=100 '
                'clip=12 ammo=20 ready=1 noclip=0')
        # Wrap in a field label and at a space trimmed by native condump.
        wrapped = text.replace('velocity', 'velo\ncity').replace(' ground', '\nground')
        self.assertEqual(self.read(text), self.read(wrapped))

    def test_small_float_rounding(self):
        web = copy.deepcopy(self.rows)
        web[2]['origin'] = (2.000244, 0., 2.)
        self.assertEqual(compare(self.rows, web), 5)

    def test_physical_divergence(self):
        web = copy.deepcopy(self.rows)
        web[2]['origin'] = (2.1, 0., 2.)
        with self.assertRaisesRegex(ValueError, 'origin'):
            compare(self.rows, web)

    def test_weapon_divergence(self):
        web = copy.deepcopy(self.rows)
        web[2]['ammo'] = 19
        with self.assertRaisesRegex(ValueError, 'ammo'):
            compare(self.rows, web)

    def test_missing_reload_coverage(self):
        self.rows[-1]['clip'] = 10
        with self.assertRaisesRegex(ValueError, 'reload'):
            compare(self.rows, self.rows)

    def test_missing_checkpoints(self):
        with self.assertRaisesRegex(ValueError, 'count'):
            compare(self.rows, self.rows[:-1])
        with self.assertRaises(ValueError):
            self.read('USERCMD_CHECK ticks=1 elapsed=16 origin=0,0,0')

    def test_interrupted_sequence(self):
        with self.assertRaisesRegex(ValueError, 'interrupted'):
            self.read('testUsercmd: stopped after 1 ticks at a session/cinematic transition')

    def test_wrong_time_or_noclip(self):
        text = ('USERCMD_CHECK ticks=1 elapsed=16 origin=0,0,0 velocity=0,0,0 '
                'ground=1 crouch=0 health=100 clip=12 ammo=20 ready=1 noclip=0')
        for bad in [text.replace('elapsed=16', 'elapsed=32'), text.replace('noclip=0', 'noclip=1')]:
            with self.assertRaisesRegex(ValueError, 'bypassed'):
                self.read(bad)

    def test_wrapped_view_weapon_and_phase(self):
        text = ('PARITY_PHASE save_before\nUSERCMD_CHECK ticks=0 elapsed=0 '
                'origin=0,0,0 velocity=0,0,0 ground=1 crouch=0 health=100 '
                'clip=12 ammo=20 ready=1 weapon=weapon_pistol view=0,145,0 noclip=0')
        wrapped = text.replace('weapon_pistol', 'weapon_pis\ntol').replace(' view', '\nview')
        self.assertEqual(self.read(text), self.read(wrapped))
        self.assertEqual(self.read(text)[0]['phase'], 'save_before')
        for bad in [text.replace('weapon=weapon_pistol ', ''), text.replace('view=0,145,0', 'view=0,145')]:
            with self.assertRaises(ValueError):
                self.read(bad)

    def save_rows(self):
        saved = dict(self.rows[0], ticks=0, elapsed=0, weapon='weapon_pistol',
                     view=(0., 145., 0.), phase='save_before')
        changed = dict(saved, origin=(10., 0., 0.), clip=10, phase='changed')
        rows = [saved] + [dict(changed) for _ in range(3)]
        rows += [dict(saved, phase='save_after') for _ in range(2)]
        for phase in ('shotgun', 'machinegun', 'chaingun', 'plasmagun'):
            selected = dict(saved, phase=phase, weapon='weapon_' + phase, clip=8, ammo=80)
            fired = dict(selected, clip=7, ammo=79)
            rows += [selected, fired, dict(fired), dict(selected, ammo=79)]
        return rows

    def test_save_weapon_coverage(self):
        rows = self.save_rows()
        self.assertEqual(compare(rows, rows, scenario='save-weapons'), 22)

    def test_save_restore_divergence_even_when_platforms_agree(self):
        for field, value in [('view', (0., 0., 0.)), ('weapon', 'weapon_shotgun'), ('clip', 10)]:
            rows = self.save_rows()
            rows[4][field] = value
            with self.assertRaisesRegex(ValueError, 'restore'):
                compare(rows, rows, scenario='save-weapons')

    def test_missing_save_or_weapon_coverage(self):
        rows = self.save_rows()
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            compare(rows[:-1], rows[:-1], scenario='save-weapons')
        rows[-1]['clip'] = 7
        with self.assertRaisesRegex(ValueError, 'reload'):
            compare(rows, rows, scenario='save-weapons')

    def test_save_requires_settled_player(self):
        rows = self.save_rows()
        rows[0]['ground'] = rows[4]['ground'] = 0
        with self.assertRaisesRegex(ValueError, 'floor'):
            compare(rows, rows, scenario='save-weapons')

    def test_camera_or_identity_mismatch(self):
        rows = self.save_rows()
        for field, value in [('view', (0., 146., 0.)), ('weapon', 'weapon_shotgun')]:
            web = copy.deepcopy(rows)
            web[0][field] = value
            with self.assertRaisesRegex(ValueError, field):
                compare(rows, web, scenario='save-weapons')

    def test_evidence_schema_mismatch(self):
        web = copy.deepcopy(self.rows)
        web[0]['view'] = (0., 0., 0.)
        with self.assertRaisesRegex(ValueError, 'fields differ'):
            compare(self.rows, web)

    def explosive_rows(self):
        groups = [('grenade', 'weapon_handgrenade', ('selected', 'hold', 'release', 'flight', 'flight2', 'end', 'removed')),
                  ('rocket', 'weapon_rocketlauncher', ('selected', 'fire', 'flight', 'recovery', 'reload')),
                  ('bfg', 'weapon_bfg', ('selected', 'charge', 'release', 'flight', 'recovery', 'reload', 'removed')),
                  ('chainsaw', 'weapon_chainsaw', ('selected', 'attack', 'recovery'))]
        rows = []
        for name, weapon, phases in groups:
            for phase in phases:
                selected = phase == 'selected'
                rows.append(dict(self.rows[0], phase=name + '_' + phase, weapon=weapon,
                                 ammo=80 if selected else 79,
                                 clip=8 if selected or phase in ('reload', 'removed') else 7))
        return rows

    def test_explosive_weapon_coverage(self):
        rows = self.explosive_rows()
        self.assertEqual(compare(rows, rows, scenario='explosive-weapons'), 22)

    def test_explosive_missing_coverage_or_ammo(self):
        rows = self.explosive_rows()
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            compare(rows[:-1], rows[:-1], scenario='explosive-weapons')
        for row in rows:
            row['ammo'] = 80
        with self.assertRaisesRegex(ValueError, 'ammunition'):
            compare(rows, rows, scenario='explosive-weapons')

    def test_explosive_death_or_reload(self):
        rows = self.explosive_rows()
        rows[0]['health'] = 0
        with self.assertRaisesRegex(ValueError, 'died'):
            compare(rows, rows, scenario='explosive-weapons')
        rows = self.explosive_rows()
        next(row for row in rows if row['phase'] == 'rocket_reload')['clip'] = 7
        with self.assertRaisesRegex(ValueError, 'reload'):
            compare(rows, rows, scenario='explosive-weapons')


if __name__ == '__main__':
    unittest.main()
