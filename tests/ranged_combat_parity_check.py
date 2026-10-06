"""Compare stock imp ranged attacks, shotgun retaliation, death and cleanup.

Requires actual owned-missile flight/impact and damage on both actors, not merely
equal logs. This fixture does not prove other enemies, difficulty levels or maps.
"""
import argparse
from pathlib import Path
import re

from entity_parity_check import snapshots as targets
from gameplay_parity_check import checkpoints
from projectile_parity_check import owned_snapshots, snapshots as player_shots
from render_state_parity_check import states, compare as compare_clocks

PHASES = tuple('ranged_' + name for name in (
    'settle', 'acquire', 'awaken', 'pursuit', 'retaliate', 'prepare', 'flight',
    'approach', 'impact', 'release', 'hit_again', 'recover', 'exchange', 'kill',
    'cleanup', 'removed'))
TICKS = (200, 1, 100, 100, 5, 75, 5, 5, 5, 25, 60, 40, 300, 60, 300, 300)
FRAMES = (210, 211, 311, 411, 416, 491, 496, 501, 506, 531, 591, 631, 931, 991, 1291, 1591)
HEALTH = (100,) * 8 + (89, 89, 78, 78, 45, 34, 34, 34)
AMMO = (20,) * 4 + (19,) * 2 + (18,) * 7 + (17,) * 3
TARGET_HEALTH = (130,) * 3 + (74,) * 3 + (32,) * 6 + (-66,)
OWNER = 'codex_ranged_imp'


def ai_states(path):
    pattern = r'^\s*(\d+):\s+monster_demon_imp\s+codex_ranged_imp\s+(\S+)\s+move:\s*([01])\s*$'
    return [(int(index), state, int(move)) for index, state, move in
            re.findall(pattern, Path(path).read_text(encoding='utf-8', errors='replace'), re.M)]


def distance(a, b):
    return sum((x-y)**2 for x, y in zip(a, b))


def validate(players, enemies, missiles, shots, ai, clocks):
    if len(players) != 16 or tuple(row.get('phase') for row in players) != PHASES:
        raise ValueError('missing or unordered ranged combat checkpoints')
    if tuple(row['ticks'] for row in players) != TICKS or any(row['elapsed'] != tick*16 or row['noclip'] for row, tick in zip(players, TICKS)):
        raise ValueError('ranged replay timing or collision changed')
    if tuple(row['health'] for row in players) != HEALTH:
        raise ValueError('stock ranged damage and surviving player were not observed')
    if tuple(row['ammo'] for row in players) != AMMO or tuple(row['clip'] for row in players) != tuple(ammo-12 for ammo in AMMO):
        raise ValueError('three shotgun shots were not observed')
    if any(row['weapon'] != 'weapon_shotgun' for row in players) or not players[-1]['ready']:
        raise ValueError('shotgun identity or recovery changed')
    if players[8]['origin'] == players[7]['origin']:
        raise ValueError('ranged impact knockback was not observed')
    if len(enemies) != 15:
        raise ValueError('missing ranged enemy snapshots')
    for i, (row, frame) in enumerate(zip(enemies, FRAMES[1:])):
        if row['name'] != OWNER or row['frame'] != frame or row['time'] != frame*16 or row['present'] != int(i < 13):
            raise ValueError('enemy identity, clock or delayed removal changed')
        if i < 13 and (row['definition'], row['health'], row['hidden'], row['damageable']) != ('monster_demon_imp', TARGET_HEALTH[i], 0, 1):
            raise ValueError('stock imp retaliation damage or death was not observed')
    if enemies[2]['velocity'] == (0, 0, 0) or distance(enemies[2]['origin'], players[3]['origin']) >= distance(enemies[0]['origin'], players[1]['origin']):
        raise ValueError('imp pursuit was not observed')
    if distance(enemies[7]['origin'], players[8]['origin']) <= 100**2:
        raise ValueError('player damage was not sampled at ranged separation')
    if enemies[12]['velocity'] == (0, 0, 0) or enemies[12]['origin'] == enemies[11]['origin']:
        raise ValueError('dead imp ragdoll motion was not observed')
    if len(missiles) != 15:
        raise ValueError('missing owned enemy missile snapshots')
    for i, (row, phase, frame) in enumerate(zip(missiles, PHASES[1:], FRAMES[1:])):
        if (row['phase'], row['frame'], row['time'], row['owner'], row['present']) != (phase, frame, frame*16, OWNER, int(i < 13)):
            raise ValueError('enemy missile owner or checkpoint timing changed')
        if row['count'] != len(row['items']) or any(item['definition'] != 'projectile_impfireball' or item['hidden'] for item in row['items']):
            raise ValueError('wrong or incomplete enemy missile evidence')
    if missiles[0]['count'] or any(row['count'] for row in missiles[-2:]):
        raise ValueError('enemy missile delayed cleanup was not observed')
    flight, approach, impact = missiles[5:8]
    candidates = [item for item in flight['items'] if item['velocity'][1] < -400]
    observed_hit = False
    for item in candidates:
        moving = next((row for row in approach['items'] if row['index'] == item['index']), None)
        stopped = next((row for row in impact['items'] if row['index'] == item['index']), None)
        if moving and stopped and moving['velocity'][1] < -400 and stopped['velocity'] == (0, 0, 0):
            if distance(moving['origin'], players[7]['origin']) < distance(item['origin'], players[6]['origin']):
                observed_hit = True
    if not observed_hit:
        raise ValueError('same enemy missile flight, approach and impact were not observed')
    expected_ai = ('monster_demon_imp::state_Begin',) * 2 + ('monster_base::state_Combat',) * 10 + ('monster_base::state_Dead',)
    if len(ai) != 13 or tuple(row[1] for row in ai) != expected_ai or any(row[0] != ai[0][0] for row in ai):
        raise ValueError('stock imp combat and death states were not observed')
    if len(shots) != 16 or len(clocks) != 16:
        raise ValueError('missing player projectile or clock checkpoints')
    for row, clock, phase, frame in zip(shots, clocks, PHASES, FRAMES):
        if (row['phase'], row['frame'], row['time']) != (phase, frame, frame*16) or row['count'] != len(row['items']):
            raise ValueError('player projectile checkpoint timing changed')
        if (clock['frame'], clock['game_time'], clock['render_time']) != (frame, frame*16, frame*16):
            raise ValueError('ranged combat game/render clock changed')


def compare(native, web, tolerance=0.001):
    for evidence in (native, web):
        validate(*evidence)
    compare_clocks(native[-1], web[-1])
    for name, a, b in zip(('enemy', 'enemy missile', 'player projectile', 'AI'), native[1:5], web[1:5]):
        if a != b:
            raise ValueError(f'native/web {name} evidence differs (exact comparison)')
    for i, (a, b) in enumerate(zip(native[0], web[0])):
        if set(a) != set(b):
            raise ValueError('player fields differ')
        for field in a:
            if field in ('origin', 'velocity', 'view'):
                if max(abs(x-y) for x, y in zip(a[field], b[field])) > tolerance:
                    raise ValueError(f'player checkpoint {i} {field} differs')
            elif a[field] != b[field]:
                raise ValueError(f'player checkpoint {i} {field} differs')
    return len(native[0]), len(native[1]), len(native[2])


def evidence(path):
    return checkpoints(path), targets(path, True), owned_snapshots(path, OWNER), player_shots(path), ai_states(path), states(path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_log')
    parser.add_argument('web_log')
    args = parser.parse_args()
    try:
        counts = compare(evidence(args.native_log), evidence(args.web_log))
    except (OSError, ValueError) as error:
        parser.exit(1, f'Ranged combat comparison failed: {error}\n')
    print(f'PASS: {counts[0]} player, {counts[1]} enemy and {counts[2]} owned-missile checkpoints with retaliation, AI and clock parity')
