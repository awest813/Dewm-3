"""Asset-free regressions for multi-target BFG evidence validation."""
import copy
from pathlib import Path
import tempfile
import unittest

from bfg_beam_parity_check import OFFSETS, beams, compare


def fixture():
    targets = []
    for phase, offset in enumerate(OFFSETS):
        for target, name in enumerate(('codex_beam_a', 'codex_beam_b')):
            row = dict(name=name, present=int(phase < 9), frame=211+offset,
                       time=(211+offset)*16)
            if phase < 9:
                health = 50 if target == 0 else (50, 50, 50, 50, 40, 30)[min(phase, 5)]
                row.update(definition='monster_zombie_maint', hidden=0, damageable=1,
                           health=health if phase < 6 else -350,
                           origin=(float(phase), 0., 0.),
                           velocity=(1., 0., 0.) if phase == 7 else (0., 0., 0.))
            targets.append(row)
    rows = []
    for i, (offset, timer) in enumerate(zip((51, 71, 73, 93, 95, 117, 317),
                                          (333, 333, 669, 1005, 1005, 1005, 1005))):
        rows.append(dict(index=2570, frame=211+offset, time=(211+offset)*16,
                         state=2 if i < 4 else 4, next_damage=4192+timer, count=2,
                         items=[dict(slot=slot, name=name, present=1, visible=int(i < 4))
                                for slot, name in enumerate(('codex_beam_b', 'codex_beam_a'))]))
    return rows, targets


class BFGBeamParityTests(unittest.TestCase):
    def test_complete_fixture(self):
        rows, targets = fixture()
        self.assertEqual(compare(rows, copy.deepcopy(rows), targets, copy.deepcopy(targets)), (7, 20))

    def test_invalid_equal_evidence_is_rejected(self):
        mutations = (
            lambda b, t: b[0]['items'].pop(),
            lambda b, t: b[0]['items'][0].update(name='codex_beam_a'),
            lambda b, t: b[2].update(next_damage=b[2]['next_damage']+1),
            lambda b, t: t[8].update(health=40),
            lambda b, t: t[12].update(present=0),
            lambda b, t: t[14].update(velocity=(0., 0., 0.)),
            lambda b, t: b[4]['items'][0].update(visible=1),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                rows, targets = fixture()
                mutation(rows, targets)
                with self.assertRaises(ValueError):
                    compare(rows, rows, targets, targets)

    def test_physics_difference_is_rejected(self):
        rows, targets = fixture()
        changed = copy.deepcopy(targets)
        changed[0]['origin'] = (0.001, 0., 0.)
        with self.assertRaisesRegex(ValueError, 'physics differs'):
            compare(rows, rows, targets, changed)

    def test_wrapped_records_and_missing_or_orphan_items(self):
        header = 'BFG_BEAM_CHECK index=2570 frame=262 time=4192 state=2 next_damage=4525 count=2\n'
        items = ('BFG_BEAM_ITEM slot=0 name=codex_beam_b present=1 visible=1\n'
                 'BFG_BEAM_ITEM slot=1 name=codex_beam_a present=1 visible=1\n')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'console.txt'
            path.write_text(header.replace('next_damage', '\nnext_damage')+items)
            self.assertEqual(beams(path), fixture()[0][:1])
            for text in (header, items, header+items+items):
                path.write_text(text)
                with self.assertRaises(ValueError):
                    beams(path)


if __name__ == '__main__':
    unittest.main()
