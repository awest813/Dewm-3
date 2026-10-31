"""Compare a soak fixture's native and web logs checkpoint by checkpoint.

python tests/soak_parity_check.py native.txt web.txt

Every RENDER_STATE (clocks, frame, random seed) and USERCMD_CHECK (player
origin, velocity, health, weapon, ...) and PROJECTILE_ITEM snapshot must match
exactly and in order (tests/soak_parity.cfg). Reports
the first divergence with the random-draw offset when seeds differ.
"""
import re
import sys
from pathlib import Path

from render_state_parity_check import states, draw_offset
from gameplay_parity_check import checkpoints


def projectiles(path):
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    # Native condumps wrap long lines; join continuation lines first.
    text = re.sub(r'\n(?![A-Z_]{4,}|\(|\]|[A-Za-z]+:|testUsercmd|godmode|Spawn|WARNING)', '', text)
    return re.findall(r'PROJECTILE_ITEM index=\d+ def=\S+ hidden=\d origin=[-\d.,]+ velocity=[-\d.,]+', text)


def main():
    native, web = sys.argv[1], sys.argv[2]
    ns, ws = states(native), states(web)
    nc, wc = checkpoints(native), checkpoints(web)
    print(f'render states: native {len(ns)} web {len(ws)}; player checkpoints: native {len(nc)} web {len(wc)}')
    ok = True
    for i, (a, b) in enumerate(zip(ns, ws), 1):
        if a != b:
            off = draw_offset(a['random_seed'], b['random_seed'])
            print(f'FIRST STATE DIVERGENCE at checkpoint {i}: native {a} web {b}' + (f' (web {off} draws {"ahead" if off and off > 0 else "behind"})' if off else ''))
            ok = False
            break
    for i, (a, b) in enumerate(zip(nc, wc), 1):
        if a != b:
            diffs = {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)}
            print(f'FIRST PLAYER DIVERGENCE at input {i}: {diffs}')
            ok = False
            break
    npj, wpj = projectiles(native), projectiles(web)
    print(f'projectile snapshots: native {len(npj)} web {len(wpj)}')
    for i, (a, b) in enumerate(zip(npj, wpj), 1):
        if a != b:
            print(f'FIRST PROJECTILE DIVERGENCE at snapshot {i}:\n  native {a}\n  web    {b}')
            ok = False
            break
    if not ns or not nc or not npj:
        print('missing evidence')
        ok = False
    if len(ns) != len(ws) or len(nc) != len(wc) or len(npj) != len(wpj):
        print('checkpoint counts differ')
        ok = False
    print('PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
