"""Verify live grenade save/load replay against the project's native engine.

This checks each engine's own save round trip and then native/web equivalence.
It does not claim stock Steam executable or cross-platform save compatibility.
"""
import argparse
import math

from gameplay_parity_check import checkpoints
from projectile_parity_check import snapshots
from render_state_parity_check import states


PHASES = ('selected', 'held', 'released', 'flight', 'saved',
          'uninterrupted_30', 'uninterrupted_90', 'uninterrupted_300',
          'restored', 'replayed_30', 'replayed_90', 'replayed_300')
TICKS = (100, 30, 1, 45, 0, 30, 90, 300, 0, 30, 90, 300)
REPLAY_PAIRS = ((4, 8), (5, 9), (6, 10), (7, 11))


def equivalent(left, right, tolerance, label):
    if set(left) != set(right):
        raise ValueError(f'{label}: evidence fields differ')
    for key in left:
        if key == 'phase':
            continue
        a, b = left[key], right[key]
        if key in ('origin', 'velocity', 'view'):
            if (len(a) != 3 or len(b) != 3 or
                    not all(math.isfinite(v) for v in (*a, *b)) or
                    max(abs(x-y) for x, y in zip(a, b)) > tolerance):
                raise ValueError(f'{label}: {key} differs')
        elif key == 'items':
            if len(a) != len(b):
                raise ValueError(f'{label}: projectile items differ')
            for index, (item_a, item_b) in enumerate(zip(a, b)):
                equivalent(item_a, item_b, tolerance, f'{label} projectile {index}')
        elif a != b:
            raise ValueError(f'{label}: {key} differs')


def validate(players, projectiles, clocks, tolerance=0.001, require_seed_continuity=False):
    if (tuple(r.get('phase') for r in players) != PHASES or
            tuple(r.get('phase') for r in projectiles) != PHASES or
            len(clocks) != len(PHASES)):
        raise ValueError('save replay is incomplete or out of order')
    for index, (player, projectile, clock, ticks) in enumerate(zip(players, projectiles, clocks, TICKS)):
        if player['ticks'] != ticks or player['elapsed'] != ticks*16:
            raise ValueError(f'{PHASES[index]}: fixed tick replay differs')
        if player['weapon'] != 'weapon_handgrenade' or player['noclip'] or player['health'] <= 0:
            raise ValueError(f'{PHASES[index]}: wrong weapon, bypassed collision or dead player')
        if (projectile['count'] != len(projectile['items']) or
                any(item['definition'] != 'projectile_grenade' for item in projectile['items'])):
            raise ValueError(f'{PHASES[index]}: wrong or missing projectile evidence')
        # A loaded game's render view is constructed on the next tick. Keep
        # this native lifecycle state visible rather than treating it as a
        # fully rendered view at the zero-tick restored checkpoint.
        expected_render_time = -1 if index == 8 else clock['game_time']
        if (clock['game_time'] != projectile['time'] or clock['frame'] != projectile['frame'] or
                clock['render_time'] != expected_render_time):
            raise ValueError(f'{PHASES[index]}: clock evidence differs')
        if index and index != 8:
            previous = projectiles[index-1]
            if projectile['time']-previous['time'] != ticks*16 or projectile['frame']-previous['frame'] != ticks:
                raise ValueError(f'{PHASES[index]}: replay clock did not advance by fixed ticks')
        equivalent(player, player, tolerance, PHASES[index])
        for item in projectile['items']:
            equivalent(item, item, tolerance, PHASES[index])
    saved = projectiles[4]
    if (saved['count'] != 1 or saved['items'][0]['hidden'] or
            max(map(abs, saved['items'][0]['velocity'])) <= 1):
        raise ValueError('save must contain a visible moving grenade')
    if players[4]['ammo'] >= players[0]['ammo']:
        raise ValueError('grenade ammunition was not consumed')
    if (projectiles[5]['count'] != 1 or projectiles[5]['items'][0]['origin'] == saved['items'][0]['origin']):
        raise ValueError('grenade flight did not advance after saving')
    if players[7]['health'] >= players[4]['health'] or not players[7]['ready']:
        raise ValueError('grenade damage and weapon recovery were not exercised')
    if projectiles[7]['count'] or projectiles[11]['count']:
        raise ValueError('grenade removal was not exercised')
    for before, after in REPLAY_PAIRS:
        equivalent(players[before], players[after], tolerance, PHASES[after])
        equivalent(projectiles[before], projectiles[after], tolerance, PHASES[after])
        # RestoreObjects runs after the serialized RNG seed is read. The
        # native engine consumes more random values during this lifecycle.
        # Check physical/tick replay here and retain exact native/web seed
        # comparisons below; keep continuity as an explicit stronger audit.
        excluded = {'render_time'} if after == 8 else set()
        if not require_seed_continuity:
            excluded.add('random_seed')
        equivalent({k: v for k, v in clocks[before].items() if k not in excluded},
                   {k: v for k, v in clocks[after].items() if k not in excluded},
                   tolerance, PHASES[after])
    return len(PHASES)


def compare_logs(native_log, web_log, tolerance=0.001, require_seed_continuity=False):
    native = (checkpoints(native_log), snapshots(native_log), states(native_log))
    web = (checkpoints(web_log), snapshots(web_log), states(web_log))
    validate(*native, tolerance, require_seed_continuity)
    validate(*web, tolerance, require_seed_continuity)
    for kind, left_rows, right_rows in zip(('player', 'projectile', 'clock'), native, web):
        for phase, left, right in zip(PHASES, left_rows, right_rows):
            equivalent(left, right, tolerance, f'{phase} native/web {kind}')
    return len(PHASES)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_log')
    parser.add_argument('web_log')
    parser.add_argument('--require-seed-continuity', action='store_true',
                        help='also require uninterrupted/reloaded RNG seeds to match; currently fails on native restoration')
    args = parser.parse_args()
    try:
        count = compare_logs(args.native_log, args.web_log, require_seed_continuity=args.require_seed_continuity)
    except (ValueError, OSError) as error:
        parser.exit(1, f'Save replay failed: {error}\n')
    print(f'PASS: {count} native/web player, projectile and clock/seed checkpoints; four physical/tick save replay pairs per engine (0.001-unit tolerance)')
    for label, path in (('native', args.native_log), ('web', args.web_log)):
        clocks = states(path)
        print(f'{label} save/restore RNG seed: {clocks[4]["random_seed"]} -> {clocks[8]["random_seed"]} (continuity is a separate audit)')
