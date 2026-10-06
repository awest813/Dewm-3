"""Reject equal but incomplete ranged-combat evidence without licensed assets."""
import copy
import unittest

from ranged_combat_parity_check import PHASES, TICKS, FRAMES, HEALTH, AMMO, TARGET_HEALTH, OWNER, compare


def fixture():
    players = [dict(phase=phase, ticks=tick, elapsed=tick*16, health=health,
                    ammo=ammo, clip=ammo-12, weapon='weapon_shotgun', ready=1,
                    ground=1, crouch=0, noclip=0, view=(0., 90., 0.),
                    origin=(-226.+2*int(i >= 8), -2254., 16.), velocity=(0., 0., 0.))
               for i, (phase, tick, health, ammo) in enumerate(zip(PHASES, TICKS, HEALTH, AMMO))]
    enemies, missiles, shots, ai = [], [], [], []
    for i, (phase, frame) in enumerate(zip(PHASES[1:], FRAMES[1:])):
        enemy = dict(name=OWNER, frame=frame, time=frame*16, present=int(i < 13))
        if i < 13:
            enemy.update(definition='monster_demon_imp', health=TARGET_HEALTH[i], hidden=0, damageable=1,
                         origin=(-226., -2030. if i < 2 else -2100.+10*int(i == 12), 16.),
                         velocity=(1., -100., 0.) if i in (2, 12) else (0., 0., 0.))
            state = ('monster_demon_imp::state_Begin' if i < 2 else
                     'monster_base::state_Dead' if i == 12 else 'monster_base::state_Combat')
            ai.append((486, state, int(i > 0)))
        enemies.append(enemy)
        items = []
        if i in (5, 6, 7):
            items = [dict(index=2578, definition='projectile_impfireball', hidden=0,
                          origin=(-226., (-2190., -2230., -2236.)[i-5], 75.),
                          velocity=(0., -500., 0.) if i < 7 else (0., 0., 0.))]
        missiles.append(dict(phase=phase, frame=frame, time=frame*16, owner=OWNER,
                             present=int(i < 13), count=len(items), items=items))
    shots = [dict(phase=phase, frame=frame, time=frame*16, count=0, items=[])
             for phase, frame in zip(PHASES, FRAMES)]
    clocks = [dict(frame=frame, game_time=frame*16, render_time=frame*16, random_seed=i)
              for i, frame in enumerate(FRAMES)]
    return players, enemies, missiles, shots, ai, clocks


class RangedCombatParityTests(unittest.TestCase):
    def test_complete_exchange(self):
        native = fixture()
        self.assertEqual(compare(native, copy.deepcopy(native)), (16, 15, 15))

    def test_equal_incomplete_exchange_fails(self):
        for mutation in (
            lambda p, e, m, s, a, c: p[8].update(health=100),
            lambda p, e, m, s, a, c: p[6].update(ammo=19),
            lambda p, e, m, s, a, c: p[8].update(origin=p[7]['origin']),
            lambda p, e, m, s, a, c: p[-1].update(ready=0),
            lambda p, e, m, s, a, c: e[2].update(velocity=(0., 0., 0.)),
            lambda p, e, m, s, a, c: e[6].update(health=74),
            lambda p, e, m, s, a, c: e[7].update(origin=p[8]['origin']),
            lambda p, e, m, s, a, c: e[12].update(health=32),
            lambda p, e, m, s, a, c: e[12].update(velocity=(0., 0., 0.)),
            lambda p, e, m, s, a, c: e[-1].update(present=1),
            lambda p, e, m, s, a, c: m[5].update(owner='player'),
            lambda p, e, m, s, a, c: m[5]['items'][0].update(velocity=(0., 0., 0.)),
            lambda p, e, m, s, a, c: m[6]['items'][0].update(index=2579),
            lambda p, e, m, s, a, c: m[7]['items'][0].update(velocity=(0., -500., 0.)),
            lambda p, e, m, s, a, c: m[-1].update(count=1),
            lambda p, e, m, s, a, c: s[2].update(frame=0),
            lambda p, e, m, s, a, c: a.__setitem__(2, a[0]),
            lambda p, e, m, s, a, c: c.pop(),
            lambda p, e, m, s, a, c: c[7].update(render_time=0),
        ):
            with self.subTest(mutation=mutation):
                native = fixture()
                mutation(*native)
                with self.assertRaises(ValueError):
                    compare(native, native)

    def test_exact_enemy_missile_and_seed_comparison(self):
        for mutation in (
            lambda p, e, m, s, a, c: e[5].update(origin=(-225.999, -2100., 16.)),
            lambda p, e, m, s, a, c: m[5]['items'][0].update(origin=(-225.999, -2190., 75.)),
            lambda p, e, m, s, a, c: c[7].update(random_seed=12345),
        ):
            with self.subTest(mutation=mutation):
                native, web = fixture(), fixture()
                mutation(*web)
                with self.assertRaises(ValueError):
                    compare(native, web)

    def test_player_tolerance_is_not_relaxed(self):
        native, web = fixture(), fixture()
        web[0][-1].update(origin=(-223.998, -2254., 16.))
        with self.assertRaisesRegex(ValueError, 'checkpoint 15 origin'):
            compare(native, web)


if __name__ == '__main__':
    unittest.main()
