"""Reject incomplete combat evidence and preserve the existing movement tolerance."""
import copy
import unittest

from combat_parity_check import AI_STATES, FRAMES, HEALTH, TICKS, compare


def fixture():
    players = [dict(phase='combat_settle' if i == 0 else f'combat_{i-1}',
                    ticks=tick, elapsed=tick*16, noclip=0, health=health,
                    weapon='weapon_shotgun' if i < 5 else 'object',
                    clip=8 if i < 5 else 0, ammo=20 if i < 5 else -1,
                    ready=int(i < 5), ground=int(i < 5), crouch=0,
                    origin=(-226.+int(i >= 3), -2254., 16.), view=(0., 90., 0.),
                    velocity=(1., 0., 0.) if i == 5 else (0., 0., 0.))
               for i, (tick, health) in enumerate(zip(TICKS, HEALTH))]
    targets = [dict(name='codex_combat_zombie', definition='monster_zombie_maint',
                    present=1, frame=frame, time=frame*16, health=50, hidden=0, damageable=1,
                    origin=(-190., -2190.-20*int(i > 0), 16.),
                    velocity=(1., 0., 0.) if i == 1 else (0., 0., 0.))
               for i, frame in enumerate(FRAMES[1:])]
    ai = [(486, state, 1) for state in AI_STATES]
    shots = [dict(phase=row['phase'], frame=frame, time=frame*16, count=0, items=[])
             for row, frame in zip(players, FRAMES)]
    clocks = [dict(game_time=frame*16, render_time=frame*16, frame=frame, random_seed=i)
              for i, frame in enumerate(FRAMES)]
    return players, targets, ai, shots, clocks


class CombatParityTests(unittest.TestCase):
    def test_complete_encounter(self):
        native = fixture()
        self.assertEqual(compare(native, copy.deepcopy(native)), (7, 6))

    def test_equal_incomplete_evidence_fails(self):
        for mutation in (
            lambda p, t, a, s, c: p[3].update(health=100),
            lambda p, t, a, s, c: p[3].update(ammo=19),
            lambda p, t, a, s, c: p[5].update(weapon='weapon_shotgun'),
            lambda p, t, a, s, c: p[5].update(velocity=(0., 0., 0.)),
            lambda p, t, a, s, c: p[6].update(velocity=(1., 0., 0.)),
            lambda p, t, a, s, c: t[1].update(origin=t[0]['origin']),
            lambda p, t, a, s, c: t[2].update(health=0),
            lambda p, t, a, s, c: a.__setitem__(1, (486, AI_STATES[0], 1)),
            lambda p, t, a, s, c: s[1].update(count=1),
            lambda p, t, a, s, c: c.pop(),
            lambda p, t, a, s, c: c[3].update(game_time=0),
            lambda p, t, a, s, c: s[3].update(frame=0),
        ):
            with self.subTest(mutation=mutation):
                native = fixture()
                mutation(*native)
                with self.assertRaises(ValueError):
                    compare(native, native)

    def test_settled_ragdoll_drift_is_not_relaxed(self):
        native, web = fixture(), fixture()
        web[0][6]['origin'] = (-224.998, -2254., 16.)
        with self.assertRaisesRegex(ValueError, 'checkpoint 6 origin differs'):
            compare(native, web)

    def test_matching_health_does_not_hide_seed_difference(self):
        native, web = fixture(), fixture()
        web[4][5]['random_seed'] += 1
        with self.assertRaisesRegex(ValueError, 'random_seed'):
            compare(native, web)


if __name__ == '__main__':
    unittest.main()
