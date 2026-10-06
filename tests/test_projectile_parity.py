"""Asset-free checks that reject incomplete or divergent projectile evidence."""
import copy
from pathlib import Path
import tempfile
import unittest

from projectile_parity_check import snapshots, owned_snapshots, compare_projectiles


class ProjectileParity(unittest.TestCase):
    def read_owned(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'console.txt'
            path.write_text(text)
            return owned_snapshots(path, 'imp')

    def test_owned_projectiles_preserve_owner_and_wrapped_vectors(self):
        text = ('PARITY_PHASE flight\nPROJECTILE_CHECK frame=11 time=176 count=0\n'
                'OWNED_PROJECTILE_CHECK owner=imp present=1 frame=11 time=176 count=1\n'
                'OWNED_PROJECTILE_ITEM index=9 def=projectile_impfireball hidden=0 '
                'origin=1.000000,2.000000,3.000000 velocity=0.000000,-500.000000,0.000000\n'
                'PARITY_PHASE removed\nOWNED_PROJECTILE_CHECK owner=imp present=0 frame=311 time=4976 count=0\n')
        wrapped = text.replace('present=1', 'pre\nsent=1').replace('impfireball', 'impfire\nball').replace('-500.000000', '-500.00\n0000')
        rows = self.read_owned(text)
        self.assertEqual(rows, self.read_owned(wrapped))
        self.assertEqual((rows[0]['owner'], rows[0]['count'], rows[0]['items'][0]['velocity']), ('imp', 1, (0., -500., 0.)))
        self.assertEqual((rows[1]['present'], rows[1]['count']), (0, 0))

    def test_owned_projectiles_reject_incomplete_and_wrong_owner(self):
        header = 'OWNED_PROJECTILE_CHECK owner=imp present=1 frame=11 time=176 count=0\n'
        for text in ('', header.replace('owner=imp', 'owner=player'),
                     header.replace('count=0', 'count=1'),
                     header.replace('present=1', 'present=0').replace('count=0', 'count=1'),
                     header.replace('time=176', 'time=oops')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.read_owned(text)

    def test_periodic_beam_requires_flight_before_impact_and_cleanup(self):
        rows = []
        phases = ('beam_release', 'beam_before_damage', 'beam_damage1', 'beam_damage2', 'beam_impact')
        for index, phase in enumerate(phases):
            item = dict(index=945, definition='projectile_bfg', hidden=0, origin=(0., 0., 0.),
                        velocity=(0., 350. if index < 4 else 0., 0.))
            rows.append(dict(phase=phase, frame=index, time=index*16, count=1, items=[item]))
        rows.append(dict(phase='beam_removed', frame=500, time=8000, count=0, items=[]))
        self.assertEqual(compare_projectiles(rows, rows, scenario='bfg-beam'), 6)
        rows[3]['items'][0]['velocity'] = (0., 0., 0.)
        with self.assertRaisesRegex(ValueError, 'actual BFG flight'):
            compare_projectiles(rows, rows, scenario='bfg-beam')
        rows[3]['items'][0]['velocity'] = (0., 350., 0.)
        rows[-1] = dict(rows[-2], phase='beam_removed')
        with self.assertRaisesRegex(ValueError, 'cleanup'):
            compare_projectiles(rows, rows, scenario='bfg-beam')

    def read(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'console.txt'
            path.write_text(text)
            return snapshots(path)

    def rows(self):
        rows = []
        for name in ('grenade', 'rocket', 'bfg'):
            item = dict(index=2464, definition='projectile_' + name, hidden=0,
                        origin=(1., 2., 3.), velocity=(100., 0., 0.))
            rows += [dict(phase=name + '_flight', frame=11, time=176, count=1, items=[item]),
                     dict(phase=name + '_end', frame=311, time=4976, count=0, items=[])]
        return rows

    def test_wrapped_and_unwrapped(self):
        text = ('PARITY_PHASE grenade_flight\nPROJECTILE_CHECK frame=11 time=176 count=1\n'
                'PROJECTILE_ITEM index=2464 def=projectile_grenade hidden=0 '
                'origin=1.000000,2.000000,3.000000 velocity=100.000000,0.000000,0.000000\n')
        wrapped = text.replace('projectile_grenade', 'projectile_gre\nnade').replace('velocity', 'velo\ncity').replace('0.000000\n', '0.00\n0000\n')
        self.assertEqual(self.read(text), self.read(wrapped))

    def test_missing_or_malformed_evidence(self):
        for text in ('', 'PROJECTILE_CHECK frame=11 time=176 count=1',
                     'PROJECTILE_CHECK frame=11 time=176 count=0\nPROJECTILE_ITEM index=1',
                     'PROJECTILE_CHECK frame=11 time=176 count=1\nPROJECTILE_ITEM index=1 def=test hidden=0 origin=1,2 velocity=1,2,3'):
            with self.assertRaises(ValueError):
                self.read(text)

    def test_exact_and_rounding(self):
        rows = self.rows()
        web = copy.deepcopy(rows)
        web[0]['items'][0]['origin'] = (1.000244, 2., 3.)
        self.assertEqual(compare_projectiles(rows, web), 6)

    def test_flight_divergence(self):
        for field, value in [('origin', (1.1, 2., 3.)), ('velocity', (101., 0., 0.))]:
            rows = self.rows()
            web = copy.deepcopy(rows)
            web[0]['items'][0][field] = value
            with self.assertRaisesRegex(ValueError, field):
                compare_projectiles(rows, web)

    def test_identity_and_clock_divergence(self):
        for field, value in [('definition', 'projectile_plasma'), ('index', 2465), ('hidden', 1)]:
            rows = self.rows()
            web = copy.deepcopy(rows)
            web[0]['items'][0][field] = value
            with self.assertRaisesRegex(ValueError, field):
                compare_projectiles(rows, web)
        rows = self.rows()
        web = copy.deepcopy(rows)
        web[0]['time'] += 16
        with self.assertRaisesRegex(ValueError, 'time'):
            compare_projectiles(rows, web)

    def test_no_flight_or_removal_even_if_platforms_agree(self):
        rows = self.rows()
        rows[0]['items'][0]['velocity'] = (0., 0., 0.)
        with self.assertRaisesRegex(ValueError, 'flight'):
            compare_projectiles(rows, rows)
        rows = self.rows()
        rows[1] = dict(rows[0], phase='grenade_end')
        with self.assertRaisesRegex(ValueError, 'removal'):
            compare_projectiles(rows, rows)


if __name__ == '__main__':
    unittest.main()
