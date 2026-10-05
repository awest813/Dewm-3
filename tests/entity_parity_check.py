"""Compare real target damage, ragdoll and removal snapshots.

The fixtures disable enemy pursuit. Matching them does not prove full combat,
multi-target beam scheduling, player death, or full campaign fidelity.
"""
import argparse
import math
import re

from gameplay_parity_check import checkpoints, compare as compare_players
from render_state_parity_check import _records


PATTERN = re.compile(
    r'ENTITY_CHECK name=(\S+)\s*present=([01])\s*frame=(\d+)\s*time=(\d+)(?:\s*'
    r'def=(\S+)\s*health=(-?\d+)\s*hidden=([01])\s*damageable=([01])\s*'
    r'origin=([-\d.,]+)\s*velocity=([-\d.,]+))?$')


def snapshots(path, allow_missing=False):
    rows = []
    for values in _records(path, 'ENTITY_CHECK ', PATTERN):
        name, present, frame, time, definition, health, hidden, damageable, origin, velocity = values
        if present == '0':
            if not allow_missing or definition is not None:
                raise ValueError('unexpected missing target')
            rows.append(dict(name=name, present=0, frame=int(frame), time=int(time)))
            continue
        if definition is None:
            raise ValueError('incomplete present target')
        vectors = [tuple(map(float, value.split(','))) for value in (origin, velocity)]
        if any(len(vector) != 3 or not all(map(math.isfinite, vector)) for vector in vectors):
            raise ValueError('incomplete or nonfinite target vector')
        rows.append(dict(name=name, present=1, frame=int(frame), time=int(time), definition=definition,
                         health=int(health), hidden=int(hidden), damageable=int(damageable),
                         origin=vectors[0], velocity=vectors[1]))
    return rows


def validate(rows):
    if len(rows) != 5:
        raise ValueError('missing chainsaw target checkpoints')
    if any(not row.get('present', 1) for row in rows):
        raise ValueError('unexpected missing melee target')
    if any(row['name'] != 'codex_melee_target' or row['definition'] != 'monster_zombie_maint'
           or row['hidden'] or not row['damageable'] for row in rows):
        raise ValueError('wrong, hidden, or nondamageable target')
    if rows[0]['health'] <= 0 or rows[1]['health'] >= rows[0]['health'] or rows[-1]['health'] > 0:
        raise ValueError('replay did not exercise a hit and target death')
    if any(row['time'] != row['frame'] * 16 for row in rows):
        raise ValueError('target simulation clock changed')
    if [row['frame'] - rows[0]['frame'] for row in rows] != [0, 10, 30, 130, 230]:
        raise ValueError('target checkpoints are out of order or incomplete')
    if rows[-1]['origin'] == rows[0]['origin'] or rows[-1]['velocity'] != (0, 0, 0):
        raise ValueError('ragdoll movement and settling were not exercised')


def validate_bfg(rows):
    names = ('codex_bfg_a', 'codex_bfg_b', 'codex_bfg_blocked')
    if len(rows) != 18 or [row['name'] for row in rows] != list(names) * 6:
        raise ValueError('missing or unordered BFG target checkpoints')
    for index, row in enumerate(rows):
        if row['time'] != row['frame'] * 16 or row['frame'] - rows[0]['frame'] != (0, 50, 51, 73, 123, 423)[index // 3]:
            raise ValueError('BFG target clock or checkpoint order changed')
        expected_present = not (index // 3 == 5 and index % 3 < 2)
        if bool(row['present']) != expected_present:
            raise ValueError('BFG target removal happened early or never completed')
        if not expected_present:
            continue
        if row['definition'] != 'monster_zombie_maint' or row['hidden'] or not row['damageable']:
            raise ValueError('wrong or nondamageable BFG target')
        if index % 3 == 2 or index // 3 < 3:
            if row['health'] != 50:
                raise ValueError('BFG damaged a blocked target or fired before release')
        elif row['health'] >= 0:
            raise ValueError('BFG did not kill both exposed targets')


def validate_beam(rows):
    if len(rows) != 10 or any(row['name'] != 'codex_beam_target' or not row['present'] for row in rows[:9]):
        raise ValueError('missing periodic beam target checkpoints')
    for index, (row, offset) in enumerate(zip(rows, (0, 50, 51, 71, 73, 93, 95, 117, 317, 617))):
        if row['frame'] - rows[0]['frame'] != offset or row['time'] != row['frame'] * 16:
            raise ValueError('periodic beam checkpoint timing changed')
        if index == 9:
            if row['present']:
                raise ValueError('dead beam target removal was not observed')
            continue
        if row['definition'] != 'monster_zombie_maint' or row['hidden'] or not row['damageable']:
            raise ValueError('wrong or nondamageable beam target')
    health = [row['health'] for row in rows[:9]]
    if health[:4] != [50] * 4 or not (0 < health[5] < health[4] < health[3]):
        raise ValueError('two nonfatal periodic beam pulses were not observed before impact')
    if health[3] - health[4] != health[4] - health[5]:
        raise ValueError('periodic beam pulse damage changed')
    if any(value >= 0 for value in health[6:]) or rows[-2]['velocity'] != (0, 0, 0):
        raise ValueError('beam impact/death and ragdoll settling were not exercised')


def compare(native, web, tolerance=0.001, scenario='melee-hit'):
    validator = {'bfg-damage': validate_bfg, 'bfg-beam': validate_beam}.get(scenario, validate)
    validator(native)
    validator(web)
    for index, (left, right) in enumerate(zip(native, web), 1):
        for field in left:
            if field in ('origin', 'velocity'):
                delta = max(abs(a-b) for a, b in zip(left[field], right[field]))
                if delta > tolerance:
                    raise ValueError(f'target {index} {field}: {left[field]} / {right[field]} (delta {delta})')
            elif left[field] != right[field]:
                raise ValueError(f'target {index} {field}: {left[field]} / {right[field]}')
    return len(native)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_log')
    parser.add_argument('web_log')
    parser.add_argument('--scenario', choices=('melee-hit', 'bfg-damage', 'bfg-beam'), default='melee-hit')
    args = parser.parse_args()
    compare_players(checkpoints(args.native_log), checkpoints(args.web_log), scenario=args.scenario)
    allow_missing = args.scenario in ('bfg-damage', 'bfg-beam')
    count = compare(snapshots(args.native_log, allow_missing), snapshots(args.web_log, allow_missing), scenario=args.scenario)
    if args.scenario == 'bfg-beam':
        from projectile_parity_check import snapshots as projectile_snapshots, compare_projectiles
        compare_projectiles(projectile_snapshots(args.native_log), projectile_snapshots(args.web_log), scenario='bfg-beam')
    print(f'PASS: {count} native/web {args.scenario} target checkpoints (tolerance 0.001 units)')
