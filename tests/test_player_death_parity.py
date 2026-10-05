"""Reject incomplete death evidence even when native and web logs agree."""
import copy
import unittest

from gameplay_parity_check import compare
from projectile_parity_check import compare_projectiles


class PlayerDeathChecks(unittest.TestCase):
    def setUp(self):
        phases = ('death_selected', 'death_shot1', 'death_impact1', 'death_shot2',
                  'death_impact2', 'death_shot3', 'death_impact3', 'death_fall', 'death_settled')
        ticks = (100, 1, 120, 1, 120, 1, 30, 90, 300)
        health = (100, 100, 59, 59, 18, 18, -23, -23, -23)
        ammo = (96, 95, 95, 94, 94, 93, -1, -1, -1)
        self.players = [dict(phase=phase, ticks=tick, elapsed=tick * 16,
                             origin=(float(i), 0., 16.),
                             velocity=(1., 0., 0.) if i in (6, 7) else (0., 0., 0.),
                             view=(0., 0., 0.), ground=int(i < 6), crouch=0,
                             health=health[i], ammo=ammo[i], clip=5-i//2 if i < 6 else 0,
                             ready=int(i < 6), noclip=0,
                             weapon='weapon_rocketlauncher' if i < 6 else 'object')
                        for i, (phase, tick) in enumerate(zip(phases, ticks))]
        self.projectiles = []
        for i, phase in enumerate(phases):
            items = [] if i in (0, 8) else [dict(index=486, definition='projectile_rocket',
                                                hidden=0, origin=(0., 0., 0.),
                                                velocity=(900., 0., 0.) if i in (1, 3, 5) else (0., 0., 0.))]
            self.projectiles.append(dict(phase=phase, frame=i, time=i*16, count=len(items), items=items))

    def test_complete_coverage(self):
        self.assertEqual(compare(self.players, self.players, scenario='player-death'), 9)
        self.assertEqual(compare_projectiles(self.projectiles, self.projectiles, scenario='player-death'), 9)

    def test_missing_death_or_timing(self):
        for field, value in (('health', 18), ('ticks', 1)):
            rows = copy.deepcopy(self.players)
            rows[6][field] = value
            with self.assertRaises(ValueError):
                compare(rows, rows, scenario='player-death')

    def test_weapon_retained_or_ragdoll_missing(self):
        for index, field, value in ((6, 'weapon', 'weapon_rocketlauncher'),
                                    (6, 'ammo', 93), (8, 'velocity', (1., 0., 0.))):
            rows = copy.deepcopy(self.players)
            rows[index][field] = value
            with self.assertRaises(ValueError):
                compare(rows, rows, scenario='player-death')
        rows = copy.deepcopy(self.players)
        for row in rows:
            row['velocity'] = (0., 0., 0.)
        with self.assertRaisesRegex(ValueError, 'motion'):
            compare(rows, rows, scenario='player-death')

    def test_missing_launch_impact_or_cleanup(self):
        for index, velocity in ((3, (0., 0., 0.)), (4, (900., 0., 0.))):
            rows = copy.deepcopy(self.projectiles)
            rows[index]['items'][0]['velocity'] = velocity
            with self.assertRaises(ValueError):
                compare_projectiles(rows, rows, scenario='player-death')
        rows = copy.deepcopy(self.projectiles)
        rows[-1]['items'] = copy.deepcopy(rows[-2]['items'])
        rows[-1]['count'] = 1
        with self.assertRaisesRegex(ValueError, 'cleanup'):
            compare_projectiles(rows, rows, scenario='player-death')

    def test_platform_difference_and_missing_phase(self):
        web = copy.deepcopy(self.players)
        web[6]['view'] = (0., 10., 0.)
        with self.assertRaisesRegex(ValueError, 'view'):
            compare(self.players, web, scenario='player-death')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            compare(self.players[:-1], self.players[:-1], scenario='player-death')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            compare_projectiles(self.projectiles[:-1], self.projectiles[:-1], scenario='player-death')


if __name__ == '__main__':
    unittest.main()
