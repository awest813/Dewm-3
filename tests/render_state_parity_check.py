"""Compare recorded game/render clocks, frames and random seeds before pixel analysis.

Matching these fields is necessary evidence, not proof of equivalent entities,
camera, settings or full rendering fidelity. Reads native wrapped condumps and
unwrapped browser console exports without changing the engine's random state.
"""
import argparse
from pathlib import Path
import re


FIELDS = ('game_time', 'render_time', 'frame', 'random_seed')
PATTERN = re.compile(r'RENDER_STATE game_time=(-?\d+)\s*render_time=(-?\d+)\s*frame=(-?\d+)\s*random_seed=(-?\d+)$')


def _records(path, prefix, pattern):
    records = []
    pending = ''

    def finish(record):
        match = pattern.fullmatch(record)
        if not match:
            raise ValueError(f'{path}: incomplete render state')
        records.append(match.groups())

    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        if line.startswith(prefix):
            if pending:
                finish(pending)
            pending = line
        elif pending:
            # condump wraps within labels and numbers as well as at spaces.
            # Delay accepting a trailing seed until the next line, which may
            # contain the remaining digits of an otherwise valid integer.
            if pattern.fullmatch(pending) and not re.fullmatch(r'\d+', line):
                finish(pending)
                pending = ''
            else:
                pending += line
    if pending:
        finish(pending)
    if not records:
        raise ValueError(f'{path}: incomplete or absent render states')
    return records


def states(path):
    return [dict(zip(FIELDS, map(int, row))) for row in _records(path, 'RENDER_STATE ', PATTERN)]


def traces(path):
    pattern = re.compile(r'RANDOM_STATE phase=(\w+)\s*index=(\d+)\s*frame=(\d+)\s*seed=(-?\d+)$')
    return [dict(phase=row[0], index=int(row[1]), frame=int(row[2]), seed=int(row[3]))
            for row in _records(path, 'RANDOM_STATE ', pattern)]


def compare_traces(native, web):
    if not native or not web:
        raise ValueError('absent random trace evidence')
    for index, (left, right) in enumerate(zip(native, web), 1):
        for key in ('phase', 'index', 'frame', 'seed'):
            if key not in left or key not in right:
                raise ValueError(f'random trace {index}: incomplete evidence')
            if left[key] != right[key]:
                detail = ''
                if key == 'seed':
                    offset = draw_offset(left[key], right[key])
                    if offset is not None:
                        detail = f' (web {abs(offset)} random draws {"ahead" if offset > 0 else "behind"})'
                raise ValueError(f'random trace {index} phase={left["phase"]} index={left["index"]} frame={left["frame"]}: {key} {left[key]} / {right[key]}{detail}')
    if len(native) != len(web):
        raise ValueError(f'random trace count differs: {len(native)} / {len(web)}')
    return len(native)


def draw_offset(native_seed, web_seed, limit=4096):
    """Return a small signed draw distance in the stock 32-bit idRandom sequence."""
    native, web = native_seed & 0xffffffff, web_seed & 0xffffffff
    if native == web:
        return 0
    forward, backward = native, web
    for count in range(1, limit + 1):
        forward = (69069 * forward + 1) & 0xffffffff
        backward = (69069 * backward + 1) & 0xffffffff
        if forward == web:
            return count
        if backward == native:
            return -count
    return None


def compare(native, web):
    if not native or len(native) != len(web):
        raise ValueError(f'render checkpoint count differs or is empty: {len(native)} / {len(web)}')
    for index, (left, right) in enumerate(zip(native, web), 1):
        if set(left) != set(FIELDS) or set(right) != set(FIELDS):
            raise ValueError(f'render checkpoint {index}: incomplete state evidence')
        for field in FIELDS:
            if left[field] != right[field]:
                detail = ''
                if field == 'random_seed':
                    offset = draw_offset(left[field], right[field])
                    if offset is not None:
                        detail = f' (web {abs(offset)} random draws {"ahead" if offset > 0 else "behind"})'
                raise ValueError(f'render checkpoint {index} {field}: {left[field]} / {right[field]}{detail}')
    return len(native)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_log')
    parser.add_argument('web_log')
    parser.add_argument('--trace', action='store_true', help='compare g_debugRandomSeed traces and report the first divergence')
    args = parser.parse_args()
    try:
        count = (compare_traces(traces(args.native_log), traces(args.web_log)) if args.trace
                 else compare(states(args.native_log), states(args.web_log)))
    except (ValueError, OSError) as error:
        parser.exit(1, f'State comparison failed: {error}\n')
    label = 'random trace' if args.trace else 'game/render clock, frame and random-seed'
    print(f'PASS: {count} recorded {label} checkpoints; other scene state requires separate verification')
