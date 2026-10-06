"""Verify native/web multi-target BFG acquisition, stock pulse order and cleanup.

Enemy pursuit is disabled by the fixture; this does not prove full combat or
changing occlusion. Beam snapshots are read-only and do not advance the world.
"""
import argparse
import re

from entity_parity_check import snapshots as targets
from gameplay_parity_check import checkpoints, compare as compare_players
from projectile_parity_check import snapshots as projectiles, compare_projectiles
from render_state_parity_check import _records, compare as compare_clocks, states as clocks


PATTERN = re.compile(
    r'BFG_BEAM_(?:CHECK index=(\d+)\s*frame=(\d+)\s*time=(\d+)\s*state=(\d+)\s*'
    r'next_damage=(\d+)\s*count=(\d+)|ITEM slot=(\d+)\s*name=(\S+)\s*'
    r'present=([01])\s*visible=([01]))$')
NAMES = ('codex_beam_a', 'codex_beam_b')
OFFSETS = (0, 50, 51, 71, 73, 93, 95, 117, 317, 617)


def beams(path):
    rows = []
    for fields in _records(path, 'BFG_BEAM_', PATTERN):
        if fields[0] is not None:
            if rows and len(rows[-1]['items']) != rows[-1]['count']:
                raise ValueError('missing beam items')
            index, frame, time, state, next_damage, count = map(int, fields[:6])
            rows.append(dict(index=index, frame=frame, time=time, state=state,
                             next_damage=next_damage, count=count, items=[]))
        else:
            slot, name, present, visible = fields[6:]
            if not rows or int(slot) != len(rows[-1]['items']) or len(rows[-1]['items']) >= rows[-1]['count']:
                raise ValueError('orphan, duplicate or unordered beam item')
            rows[-1]['items'].append(dict(slot=int(slot), name=name,
                                         present=int(present), visible=int(visible)))
    if rows and len(rows[-1]['items']) != rows[-1]['count']:
        raise ValueError('missing beam items')
    return rows


def validate(beam_rows, target_rows):
    if len(target_rows) != 20 or [row['name'] for row in target_rows] != list(NAMES) * 10:
        raise ValueError('missing or unordered multi-target snapshots')
    base = target_rows[0]['frame']
    for phase, offset in enumerate(OFFSETS):
        for target, row in enumerate(target_rows[phase*2:phase*2+2]):
            if row['frame'] != base + offset or row['time'] != row['frame'] * 16:
                raise ValueError('multi-target timing changed')
            if row['present'] != int(phase < 9):
                raise ValueError('target removal was early or absent')
            if phase == 9:
                continue
            if row['definition'] != 'monster_zombie_maint' or row['hidden'] or not row['damageable']:
                raise ValueError('wrong, hidden or nondamageable beam target')
            if phase < 6:
                expected = (50, 50, 50, 50, 40, 30)[phase] if target == 1 else 50
                if row['health'] != expected:
                    raise ValueError('stock first-target periodic damage order changed')
            elif row['health'] >= 0:
                raise ValueError('BFG impact did not kill both targets')
    for target in range(2):
        impact, moving = target_rows[12+target], target_rows[14+target]
        if impact['origin'] == moving['origin'] or moving['velocity'] == (0, 0, 0):
            raise ValueError('both ragdolls must exhibit actual motion')
    if len(beam_rows) != 7:
        raise ValueError('missing multi-target beam checkpoints')
    frame_offsets = (51, 71, 73, 93, 95, 117, 317)
    # Stock Think updates its shared timer after the first target in the loop.
    timers = (333, 333, 669, 1005, 1005, 1005, 1005)
    launch_time = (base + 51) * 16
    for i, row in enumerate(beam_rows):
        if row['frame'] != base + frame_offsets[i] or row['time'] != row['frame'] * 16:
            raise ValueError('beam clock changed')
        if row['index'] != beam_rows[0]['index'] or row['count'] != 2:
            raise ValueError('two acquired targets on one BFG were not observed')
        if row['state'] != (2 if i < 4 else 4) or row['next_damage'] != launch_time + timers[i]:
            raise ValueError('BFG flight/impact or shared damage timer changed')
        if [item['name'] for item in row['items']] != ['codex_beam_b', 'codex_beam_a']:
            raise ValueError('beam acquisition order changed')
        if any(item['slot'] != slot or not item['present'] or item['visible'] != int(i < 4)
               for slot, item in enumerate(row['items'])):
            raise ValueError('beam presence or visibility cleanup changed')


def compare(native_beams, web_beams, native_targets, web_targets):
    validate(native_beams, native_targets)
    validate(web_beams, web_targets)
    if native_beams != web_beams:
        raise ValueError('native/web beam acquisition, state or timer differs')
    if native_targets != web_targets:
        raise ValueError('native/web target health or physics differs (exact comparison)')
    return len(native_beams), len(native_targets)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_log')
    parser.add_argument('web_log')
    args = parser.parse_args()
    compare_players(checkpoints(args.native_log), checkpoints(args.web_log), scenario='bfg-beam')
    compare_projectiles(projectiles(args.native_log), projectiles(args.web_log), scenario='bfg-beam')
    compare_clocks(clocks(args.native_log), clocks(args.web_log))
    beam_count, target_count = compare(beams(args.native_log), beams(args.web_log),
                                      targets(args.native_log, True), targets(args.web_log, True))
    print(f'PASS: {beam_count} beam states and {target_count} exact target snapshots, with player/projectile/clock parity')
