import copy
from pathlib import Path
import tempfile
import unittest

from entity_parity_check import compare, snapshots


def fixture():
    return [dict(name='codex_melee_target', definition='monster_zombie_maint',
                 frame=111+offset, time=(111+offset)*16, health=health,
                 hidden=0, damageable=1, origin=(float(i), 2., 3.), velocity=(0., 0., 0.))
            for i, (offset, health) in enumerate(zip((0, 10, 30, 130, 230), (50, 0, -50, -100, -100)))]


class EntityParityTests(unittest.TestCase):
    def beam_fixture(self):
        rows = []
        offsets = (0, 50, 51, 71, 73, 93, 95, 117, 317, 617)
        for index, offset in enumerate(offsets):
            row = dict(name='codex_beam_target', present=int(index < 9), frame=211+offset, time=(211+offset)*16)
            if index < 9:
                row.update(definition='monster_zombie_maint', health=(50, 50, 50, 50, 40, 30, -370, -370, -370)[index],
                           hidden=0, damageable=1, origin=(0., 0., 0.), velocity=(0., 0., 0.))
            rows.append(row)
        return rows

    def test_missing_second_beam_pulse_and_early_impact_fail(self):
        rows = self.beam_fixture()
        rows[5]['health'] = 40
        with self.assertRaisesRegex(ValueError, 'two nonfatal'):
            compare(rows, rows, scenario='bfg-beam')
        rows[5]['health'] = -370
        with self.assertRaisesRegex(ValueError, 'two nonfatal'):
            compare(rows, rows, scenario='bfg-beam')

    def test_beam_target_cleanup_and_timing_are_required(self):
        rows = self.beam_fixture()
        self.assertEqual(compare(rows, rows, scenario='bfg-beam'), 10)
        rows[-1]['present'] = 1
        with self.assertRaisesRegex(ValueError, 'removal'):
            compare(rows, rows, scenario='bfg-beam')
        rows = self.beam_fixture()
        rows[5]['frame'] += 1
        with self.assertRaisesRegex(ValueError, 'timing'):
            compare(rows, rows, scenario='bfg-beam')

    def bfg_fixture(self):
        rows = []
        for phase, offset in enumerate((0, 50, 51, 73, 123, 423)):
            for index, name in enumerate(('codex_bfg_a', 'codex_bfg_b', 'codex_bfg_blocked')):
                row = dict(name=name, present=int(not (phase == 5 and index < 2)),
                           frame=111+offset, time=(111+offset)*16)
                if row['present']:
                    row.update(definition='monster_zombie_maint', health=50 if phase < 3 or index == 2 else -750,
                               hidden=0, damageable=1, origin=(0., 0., 0.), velocity=(0., 0., 0.))
                rows.append(row)
        return rows

    def test_bfg_blocked_target_damage_fails_even_when_equal(self):
        rows = self.bfg_fixture()
        rows[11]['health'] = 40
        with self.assertRaisesRegex(ValueError, 'blocked'):
            compare(rows, rows, scenario='bfg-damage')

    def test_bfg_no_hit_and_premature_removal_fail(self):
        rows = self.bfg_fixture()
        rows[9]['health'] = 50
        with self.assertRaisesRegex(ValueError, 'kill both'):
            compare(rows, rows, scenario='bfg-damage')
        rows = self.bfg_fixture()
        rows[9] = dict(name='codex_bfg_a', present=0, frame=184, time=2944)
        with self.assertRaisesRegex(ValueError, 'removal'):
            compare(rows, rows, scenario='bfg-damage')

    def test_removed_target_record_has_no_invented_health(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'console.txt'
            path.write_text('ENTITY_CHECK name=codex_bfg_a present=0 frame=534 time=8544\n')
            self.assertEqual(snapshots(path, allow_missing=True),
                             [dict(name='codex_bfg_a', present=0, frame=534, time=8544)])

    def test_damage_difference_fails(self):
        native = fixture()
        web = copy.deepcopy(native)
        web[1]['health'] = 10
        with self.assertRaisesRegex(ValueError, 'health'):
            compare(native, web)

    def test_equal_logs_without_hit_or_death_fail(self):
        rows = fixture()
        for row in rows:
            row['health'] = 50
        with self.assertRaisesRegex(ValueError, 'hit and target death'):
            compare(rows, rows)

    def test_missing_checkpoint_and_ragdoll_drift_fail(self):
        rows = fixture()
        with self.assertRaisesRegex(ValueError, 'missing'):
            compare(rows, rows[:-1])
        web = copy.deepcopy(rows)
        web[-1]['origin'] = (4.1, 2., 3.)
        with self.assertRaisesRegex(ValueError, 'origin'):
            compare(rows, web)

    def test_wrapped_vector_and_missing_entity(self):
        text = ('ENTITY_CHECK name=codex_melee_target present=1 frame=111 time=1776 '
                'def=monster_zombie_maint health=50 hidden=0 damageable=1 '
                'origin=-226.000000,-2200.000000,16.250000 '
                'velocity=0.000000,0.000000,0.000000')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'console.txt'
            wrapped = '\n'.join(text[i:i+79] for i in range(0, len(text), 79))
            path.write_text(wrapped)
            row = snapshots(path)[0]
            self.assertEqual(row['origin'], (-226, -2200, 16.25))
            path.write_text('ENTITY_CHECK name=codex_melee_target present=0 frame=111 time=1776\n')
            with self.assertRaises(ValueError):
                snapshots(path)


if __name__ == '__main__':
    unittest.main()
