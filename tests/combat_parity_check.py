"""Check stock zombie pursuit, melee damage and player death replay evidence.

This encounter leaves stock AI, navigation, attack scripts and protection enabled.
It does not cover ranged combat, retaliation, campaign progression or rendering.
"""
import argparse
from pathlib import Path
import re

from entity_parity_check import snapshots
from gameplay_parity_check import checkpoints
from projectile_parity_check import snapshots as projectiles
from render_state_parity_check import compare as compare_clocks, states

TICKS = (200, 1, 60, 100, 200, 300, 300)
FRAMES = (210, 211, 271, 371, 571, 871, 1171)
HEALTH = (100, 100, 100, 72, 30, -12, -12)
AI_STATES = ('monster_zombie::state_Begin',) + ('monster_base::state_Combat',) * 3 + ('monster_zombie::state_Idle',) * 2


def ai_states(path):
    pattern = r'^\s*(\d+):\s+monster_zombie_maint\s+codex_combat_zombie\s+(\S+)\s+move:\s*([01])\s*$'
    return [(int(index), state, int(move)) for index, state, move in
            re.findall(pattern, Path(path).read_text(encoding='utf-8', errors='replace'), re.M)]


def validate(players, targets, ai, shots, clocks):
    if len(players) != 7 or [row.get('phase') for row in players] != ['combat_settle'] + [f'combat_{i}' for i in range(6)]:
        raise ValueError('missing or unordered combat checkpoints')
    if tuple(row['ticks'] for row in players) != TICKS or any(row['elapsed'] != row['ticks']*16 or row['noclip'] for row in players):
        raise ValueError('combat replay timing or collision changed')
    if tuple(row['health'] for row in players) != HEALTH:
        raise ValueError('stock melee damage and player death were not exercised')
    for row in players[:5]:
        if row['weapon'] != 'weapon_shotgun' or (row['clip'], row['ammo'], row['ready']) != (8, 20, 1):
            raise ValueError('live player weapon changed or fired')
    for row in players[5:]:
        if row['weapon'] != 'object' or (row['clip'], row['ammo'], row['ready']) != (0, -1, 0):
            raise ValueError('player death did not release the weapon')
    if players[3]['origin'] == players[1]['origin']:
        raise ValueError('melee knockback was not observed')
    if players[5]['velocity'] == (0, 0, 0) or players[6]['velocity'] != (0, 0, 0):
        raise ValueError('player ragdoll motion and settling were not observed')
    if len(targets) != 6:
        raise ValueError('missing combat target snapshots')
    for row, frame in zip(targets, FRAMES[1:]):
        if (row['name'], row['definition'], row['health'], row['hidden'], row['damageable'], row['present']) != ('codex_combat_zombie', 'monster_zombie_maint', 50, 0, 1, 1):
            raise ValueError('combat target was altered or damaged')
        if row['frame'] != frame or row['time'] != frame*16:
            raise ValueError('combat target clock changed')
    def distance(target, player):
        return sum((a-b)**2 for a, b in zip(target['origin'], player['origin']))
    if distance(targets[1], players[2]) >= distance(targets[0], players[1]) or targets[1]['velocity'] == (0, 0, 0):
        raise ValueError('actual zombie pursuit was not observed')
    if len(ai) != 6 or tuple(row[1] for row in ai) != AI_STATES or any(row[0] != ai[0][0] or row[2] != 1 for row in ai):
        raise ValueError('stock combat and return-to-idle states were not observed')
    if len(shots) != 7 or any(row['count'] or row['items'] for row in shots):
        raise ValueError('player projectile attack or missing evidence')
    if any(row['frame'] != frame or row['time'] != frame*16 or row['phase'] != player['phase']
           for row, frame, player in zip(shots, FRAMES, players)):
        raise ValueError('projectile checkpoint timing changed')
    if len(clocks) != 7 or tuple(row['frame'] for row in clocks) != FRAMES:
        raise ValueError('missing combat clock checkpoints')
    if any(row['game_time'] != row['frame']*16 or row['render_time'] != row['frame']*16 for row in clocks):
        raise ValueError('combat game/render clock changed')


def compare(native, web, tolerance=0.001):
    for evidence in (native, web):
        validate(*evidence)
    left, right = native[0], web[0]
    compare_clocks(native[4], web[4])
    for name, a, b in zip(('target', 'AI', 'projectile'), native[1:4], web[1:4]):
        if a != b:
            raise ValueError(f'native/web {name} evidence differs')
    for index, (a, b) in enumerate(zip(left, right)):
        if set(a) != set(b):
            raise ValueError('player evidence fields differ')
        for field in a:
            if field in ('origin', 'velocity', 'view'):
                delta = max(abs(x-y) for x, y in zip(a[field], b[field]))
                if delta > tolerance:
                    raise ValueError(f'player checkpoint {index} {field} differs: {a[field]} / {b[field]} (delta {delta})')
            elif a[field] != b[field]:
                raise ValueError(f'player checkpoint {index} {field} differs')
    return len(left), len(native[1])


def evidence(path):
    return checkpoints(path), snapshots(path), ai_states(path), projectiles(path), states(path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_log')
    parser.add_argument('web_log')
    args = parser.parse_args()
    try:
        players, targets = compare(evidence(args.native_log), evidence(args.web_log))
    except (OSError, ValueError) as error:
        parser.exit(1, f'Combat comparison failed: {error}\n')
    print(f'PASS: {players} player and {targets} target checkpoints with AI, projectile and clock parity')
