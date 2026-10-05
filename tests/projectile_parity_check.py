"""Compare actual player-owned projectile snapshots from the two engine runs.

Checks launch, motion and removal evidence, alongside weapon/tick/ammo parity.
This does not prove enemy damage, BFG target selection or chainsaw hit accuracy.
"""
import argparse
from pathlib import Path
import re

from gameplay_parity_check import checkpoints, compare

HEADER = re.compile(r'PROJECTILE_CHECK frame=(\d+)\s*time=(\d+)\s*count=(\d+)$')
ITEM = re.compile(r'PROJECTILE_ITEM index=(\d+)\s*def=(\S+?)\s*hidden=([01])\s*origin=([-\d.,]+)\s*velocity=([-\d.,]+)$')


def snapshots(path):
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
            if any(len(vector) != 3 for vector in vectors):
                raise ValueError('incomplete projectile vector')
            rows[-1]['items'].append(dict(index=int(index), definition=definition,
                                         hidden=int(hidden), origin=vectors[0], velocity=vectors[1]))

    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
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


def compare_projectiles(native, web, tolerance=0.001):
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
    args = parser.parse_args()
    try:
        count = compare(checkpoints(args.native_log), checkpoints(args.web_log), scenario='explosive-weapons')
        compare_projectiles(snapshots(args.native_log), snapshots(args.web_log))
    except (ValueError, OSError) as error:
        parser.exit(1, f'Projectile comparison failed: {error}\n')
    print(f'PASS: {count} native/web weapon and projectile checkpoints (tolerance 0.001 units)')
