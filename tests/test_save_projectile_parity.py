"""Asset-free rejection checks for the licensed-data save replay verifier."""
import copy
import unittest

from save_projectile_parity_check import PHASES, TICKS, equivalent, validate


def evidence():
    players, projectiles, clocks = [], [], []
    frame = 10
    for index, (phase, ticks) in enumerate(zip(PHASES, TICKS)):
        frame = 186 if index == 8 else frame+ticks
        player = dict(phase=phase, ticks=ticks, elapsed=ticks*16,
                      origin=(1., 2., 3.), velocity=(0., 0., 0.), view=(0., 90., 0.),
                      ground=1, crouch=0, noclip=0, health=60 if index in (7, 11) else 100,
                      clip=0, ammo=50 if index < 3 else 49, ready=1, weapon='weapon_handgrenade')
        items = []
        if index in (3, 4, 5, 6, 8, 9, 10):
            segment = 0 if index in (3, 4, 8) else (1 if index in (5, 9) else 2)
            items.append(dict(index=486, definition='projectile_grenade', hidden=int(segment == 2),
                              origin=(2.+segment, 3., 4.), velocity=(0., 90., 20.) if segment < 2 else (0., 0., 0.)))
        players.append(player)
        projectiles.append(dict(phase=phase, frame=frame, time=frame*16, count=len(items), items=items))
        clocks.append(dict(frame=frame, game_time=frame*16, render_time=-1 if index == 8 else frame*16,
                           random_seed=123+frame))
    return players, projectiles, clocks


class SaveReplay(unittest.TestCase):
    def test_complete_evidence(self):
        self.assertEqual(validate(*evidence()), 12)

    def test_missing_or_reordered_stages(self):
        for category in range(3):
            rows = evidence()
            rows[category].pop()
            with self.subTest(category=category), self.assertRaisesRegex(ValueError, 'incomplete'):
                validate(*rows)
        rows = evidence()
        rows[0][4], rows[0][5] = rows[0][5], rows[0][4]
        with self.assertRaisesRegex(ValueError, 'out of order'):
            validate(*rows)

    def test_save_must_contain_a_moving_visible_grenade(self):
        for field, value in (('velocity', (0., 0., 0.)), ('hidden', 1), ('definition', 'projectile_rocket')):
            rows = evidence()
            rows[1][4]['items'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(*rows)

    def test_ammunition_damage_recovery_and_removal_are_required(self):
        for index, field, value in ((4, 'ammo', 50), (7, 'health', 100), (7, 'ready', 0)):
            rows = evidence()
            rows[0][index][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(*rows)
        rows = evidence()
        rows[1][7]['items'] = copy.deepcopy(rows[1][6]['items'])
        rows[1][7]['count'] = 1
        with self.assertRaisesRegex(ValueError, 'removal'):
            validate(*rows)

    def test_stationary_trajectory_is_rejected(self):
        rows = evidence()
        rows[1][5]['items'] = copy.deepcopy(rows[1][4]['items'])
        with self.assertRaisesRegex(ValueError, 'did not advance'):
            validate(*rows)

    def test_replay_cannot_diverge_on_both_platforms(self):
        for category, index, field, value in ((0, 8, 'ammo', 48), (0, 11, 'origin', (2., 2., 3.)),
                                             (2, 8, 'game_time', 0)):
            rows = evidence()
            rows[category][index][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'differs'):
                validate(*rows)
        rows = evidence()
        rows[1][9]['items'][0]['velocity'] = (0., 91., 20.)
        with self.assertRaisesRegex(ValueError, 'velocity differs'):
            validate(*rows)

    def test_ticks_clocks_collision_and_weapon_are_checked(self):
        for category, index, field, value in ((0, 5, 'elapsed', 481), (0, 4, 'noclip', 1),
                                             (0, 4, 'weapon', 'weapon_pistol'),
                                             (1, 5, 'frame', 215), (2, 5, 'render_time', -1)):
            rows = evidence()
            rows[category][index][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(*rows)

    def test_nonfinite_vectors_are_rejected(self):
        for category in (0, 1):
            rows = evidence()
            target = rows[0][4] if category == 0 else rows[1][4]['items'][0]
            target['origin'] = (float('nan'), 2., 3.)
            with self.subTest(category=category), self.assertRaisesRegex(ValueError, 'origin differs'):
                validate(*rows)

    def test_tolerance_and_identity(self):
        a = evidence()[1][4]['items'][0]
        b = copy.deepcopy(a)
        b['origin'] = (2.000244, 3., 4.)
        equivalent(a, b, .001, 'native/web')
        for field, value in (('origin', (2.01, 3., 4.)), ('index', 487)):
            b = copy.deepcopy(a)
            b[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'differs'):
                equivalent(a, b, .001, 'native/web')

    def test_rng_continuity_is_reported_without_hiding_native_web_divergence(self):
        rows = evidence()
        rows[2][8]['random_seed'] = 0
        self.assertEqual(validate(*rows), 12)
        with self.assertRaisesRegex(ValueError, 'random_seed differs'):
            validate(*rows, require_seed_continuity=True)
        with self.assertRaisesRegex(ValueError, 'random_seed differs'):
            equivalent(evidence()[2][8], rows[2][8], .001, 'native/web clock')


if __name__ == '__main__':
    unittest.main()
