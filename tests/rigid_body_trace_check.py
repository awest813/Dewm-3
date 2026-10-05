"""Find the first exact difference in read-only rigid-body arithmetic traces."""
import argparse
from pathlib import Path
import re

NUMBER = r'-?\d+(?:\.\d+)?(?:e[+-]?\d+)?'
PATTERN = re.compile(r'RB_TRACE phase=(\w+)\s*entity=(\d+)\s*frame=(\d+)\s*field=(\w+)\s*v=(' + NUMBER + r'),(' + NUMBER + r'),(' + NUMBER + r')$')


def records(path):
    rows = []
    pending = ''

    def finish(text):
        match = PATTERN.fullmatch(text)
        if not match:
            raise ValueError('incomplete rigid-body trace evidence')
        phase, entity, frame, field, *values = match.groups()
        rows.append(dict(phase=phase, entity=int(entity), frame=int(frame), field=field,
                         value=tuple(map(float, values))))

    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        if line.startswith('RB_TRACE '):
            if pending:
                finish(pending)
            pending = line
        elif pending:
            if PATTERN.fullmatch(pending) and not re.fullmatch(r'[-+\d.eE,]+', line):
                finish(pending)
                pending = ''
            else:
                pending += line
    if pending:
        finish(pending)
    if not rows:
        raise ValueError('absent rigid-body trace evidence')
    return rows


def compare(native, web):
    if not native or not web:
        raise ValueError('absent rigid-body trace evidence')
    for index, (left, right) in enumerate(zip(native, web), 1):
        for field in ('phase', 'entity', 'frame', 'field', 'value'):
            if left[field] != right[field]:
                raise ValueError(f'trace {index} frame={left["frame"]} phase={left["phase"]} '
                                 f'field={left["field"]}: {field} {left[field]} / {right[field]}')
    if len(native) != len(web):
        raise ValueError(f'rigid-body trace count differs: {len(native)} / {len(web)}')
    return len(native)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_log')
    parser.add_argument('web_log')
    args = parser.parse_args()
    try:
        count = compare(records(args.native_log), records(args.web_log))
    except (OSError, ValueError) as error:
        parser.exit(1, f'Rigid-body comparison failed: {error}\n')
    print(f'PASS: {count} exact rigid-body arithmetic records')
