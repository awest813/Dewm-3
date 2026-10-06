"""Compare actual player-owned projectile snapshots from the two engine runs.

Checks launch, motion and removal evidence, alongside weapon/tick/ammo parity.
This does not prove enemy damage, BFG target selection or chainsaw hit accuracy.
"""
import argparse
import math
from pathlib import Path
import re

from gameplay_parity_check import checkpoints, compare

HEADER = re.compile(r'PROJECTILE_CHECK frame=(\d+)\s*time=(\d+)\s*count=(\d+)$')
ITEM = re.compile(r'PROJECTILE_ITEM index=(\d+)\s*def=(\S+?)\s*hidden=([01])\s*origin=([-\d.,]+)\s*velocity=([-\d.,]+)$')


def snapshots(path):
    return _snapshots(Path(path).read_text(encoding='utf-8', errors='replace'))


def owned_snapshots(path, owner):
    """Parse the read-only named-owner command, retaining absent-owner evidence."""
    owners = []
    pattern = re.compile(r'OWNED_PROJECTILE_CHECK owner=(\S+)\s*present=([01])\s*frame=(\d+)\s*time=(\d+)\s*count=(\d+)$')
    from render_state_parity_check import _records
    for values in _records(path, 'OWNED_PROJECTILE_CHECK ', pattern):
        name, present, frame, time, count = values
        if name != owner or (present == '0' and count != '0'):
            raise ValueError('wrong or absent projectile owner with live missiles')
        owners.append(dict(owner=name, present=int(present), frame=int(frame), time=int(time), count=int(count)))
    # Reuse the wrapped item/vector parser, excluding player-owned snapshots.
    lines = []
    pending = False
    headers = iter(owners)
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        if line.startswith('PARITY_PHASE '):
            lines.append(line)
            pending = False
        elif line.startswith('OWNED_PROJECTILE_CHECK '):
            # Headers are reconstructed from the strictly parsed records below.
            row = next(headers)
            lines.append(f'PROJECTILE_CHECK frame={row["frame"]} time={row["time"]} count={row["count"]}')
            pending = False
        elif line.startswith('OWNED_PROJECTILE_ITEM '):
            lines.append(line.replace('OWNED_PROJECTILE_ITEM ', 'PROJECTILE_ITEM ', 1))
            pending = True
        elif pending:
            if ITEM.fullmatch(lines[-1]) and not re.fullmatch(r'[-\d.,]+', line):
                pending = False
            else:
                lines[-1] += line
    rows = _snapshots('\n'.join(lines))
    if len(rows) != len(owners):
        raise ValueError('owned projectile checkpoint count differs')
    for row, identity in zip(rows, owners):
        row.update(owner=identity['owner'], present=identity['present'])
    return rows


def _snapshots(text):
    rows = []
    phase = ''
    pending = ''

    def finish(text):
        if text.startswith('PROJECTILE_CHECK '):
            match = HEADER.fullmatch(text)
            if not match:
                raise ValueError('incomplete projectile header')
            frame, time, count = map(int, match.groups())
            rows.append(dict(phase=phase, frame=frame, time=time, count=count, items=[]))
        else:
            match = ITEM.fullmatch(text)
            if not match or not rows:
                raise ValueError('incomplete projectile item')
            index, definition, hidden, origin, velocity = match.groups()
            vectors = [tuple(map(float, value.split(','))) for value in (origin, velocity)]
            if any(len(vector) != 3 or not all(map(math.isfinite, vector)) for vector in vectors):
                raise ValueError('incomplete or nonfinite projectile vector')
            rows[-1]['items'].append(dict(index=int(index), definition=definition,
                                         hidden=int(hidden), origin=vectors[0], velocity=vectors[1]))

    for line in text.splitlines():
        if line.startswith(('PROJECTILE_CHECK ', 'PROJECTILE_ITEM ', 'PARITY_PHASE ')):
            if pending:
                finish(pending)
                pending = ''
            if line.startswith('PARITY_PHASE '):
                phase = line.split()[1]
            else:
                pending = line
        elif pending:
            pattern = HEADER if pending.startswith('PROJECTILE_CHECK ') else ITEM
            if pattern.fullmatch(pending) and not re.fullmatch(r'[-\d.,]+', line):
                finish(pending)
                pending = ''
            else:
                pending += line
    if pending:
        finish(pending)
    if not rows or any(row['count'] != len(row['items']) for row in rows):
        raise ValueError('absent or inconsistent projectile count evidence')
    return rows


def compare_projectiles(native, web, tolerance=0.001, scenario='explosive-weapons'):
    if not native or len(native) != len(web):
        raise ValueError('projectile checkpoint count differs or is empty')
    for left, right in zip(native, web):
        for field in ('phase', 'frame', 'time', 'count'):
            if left[field] != right[field]:
                raise ValueError(f'{left["phase"]}: projectile {field} differs')
        for a, b in zip(left['items'], right['items']):
            for field in ('index', 'definition', 'hidden'):
                if a[field] != b[field]:
                    raise ValueError(f'{left["phase"]}: projectile {field} differs')
            for field in ('origin', 'velocity'):
                delta = max(abs(x-y) for x, y in zip(a[field], b[field]))
                if delta > tolerance:
                    raise ValueError(f'{left["phase"]}: projectile {field} differs by {delta}')
    if scenario == 'player-death':
        expected = ('death_selected', 'death_shot1', 'death_impact1', 'death_shot2',
                    'death_impact2', 'death_shot3', 'death_impact3', 'death_fall', 'death_settled')
        if tuple(row['phase'] for row in native) != expected:
            raise ValueError('player death projectile coverage is incomplete')
        for row in native:
            if any(item['definition'] != 'projectile_rocket' for item in row['items']):
                raise ValueError('player death: wrong projectile')
            if row['phase'] in ('death_shot1', 'death_shot2', 'death_shot3'):
                moving = [item for item in row['items'] if not item['hidden'] and max(map(abs, item['velocity'])) > 800]
                if len(moving) != 1:
                    raise ValueError('player death: rocket launch missing')
            if row['phase'] in ('death_impact1', 'death_impact2', 'death_impact3'):
                if not row['count'] or any(item['velocity'] != (0, 0, 0) for item in row['items']):
                    raise ValueError('player death: rocket impact missing')
        if native[0]['count'] or native[-1]['count']:
            raise ValueError('player death: projectile cleanup missing')
        return len(native)
    if scenario == 'bfg-beam':
        phases = {row['phase']: row for row in native}
        for phase in ('beam_release', 'beam_before_damage', 'beam_damage1', 'beam_damage2'):
            row = phases.get(phase)
            if not row or row['count'] != 1 or row['items'][0]['definition'] != 'projectile_bfg' or row['items'][0]['hidden'] or max(map(abs, row['items'][0]['velocity'])) < 300:
                raise ValueError('periodic beam damage was not sampled during actual BFG flight')
        impact = phases.get('beam_impact')
        if not impact or impact['count'] != 1 or impact['items'][0]['velocity'] != (0, 0, 0):
            raise ValueError('BFG impact was not observed after periodic beam pulses')
        removed = phases.get('beam_removed')
        if not removed or removed['count']:
            raise ValueError('BFG projectile cleanup was not observed')
        return len(native)
    for name in ('grenade', 'rocket', 'bfg'):
        group = [row for row in native if row['phase'].startswith(name + '_')]
        moving = [item for row in group for item in row['items']
                  if not item['hidden'] and any(abs(value) > 1 for value in item['velocity'])]
        if not moving:
            raise ValueError(f'{name}: no actual projectile flight was observed')
        if not group or group[-1]['count']:
            raise ValueError(f'{name}: removal was not observed')
    return len(native)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_log')
    parser.add_argument('web_log')
    parser.add_argument('--scenario', choices=('explosive-weapons', 'player-death'), default='explosive-weapons')
    args = parser.parse_args()
    try:
        count = compare(checkpoints(args.native_log), checkpoints(args.web_log), scenario=args.scenario)
        compare_projectiles(snapshots(args.native_log), snapshots(args.web_log), scenario=args.scenario)
    except (ValueError, OSError) as error:
        parser.exit(1, f'Projectile comparison failed: {error}\n')
    print(f'PASS: {count} native/web weapon and projectile checkpoints (tolerance 0.001 units)')
