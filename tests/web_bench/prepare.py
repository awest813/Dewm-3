"""Prepare an (ignored) web build directory for licensed-data browser benches.

python tests/web_bench/prepare.py --build build-web --data "C:/.../Doom 3"
    [--native rails.png stairs.png saved_rail.png]

Creates <build>/bench/ (page helpers, fixtures, captures/) and links
<build>/doom3base to the user's own <data>/base. Nothing here is committed or
distributed: game data stays in the local install and is served only by the
local web/serve.py instance. --native copies hangar references captured
from tests/render_hangar_parity.cfg on the native build; native_capture.py
records references for any render fixture.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

here = Path(__file__).resolve().parent
root = here.parents[1]


FIXTURES = {'hangar': 'tests/render_hangar_parity.cfg', 'scenes': 'tests/render_scenes_parity.cfg'}


def fixture(source):
    # Browser form of a native fixture: same settings and checkpoints,
    # minus window mode and quit, plus a completion marker.
    lines = []
    for line in (root / source).read_text(encoding='utf-8').splitlines():
        if line.startswith('//') or line.startswith(('set r_fullscreen', 'set r_mode')) or line == 'quit':
            continue
        lines.append(line)
    return '\n'.join(lines + ['echo FIXTURE_DONE', ''])


def link(target, source):
    if target.exists() or target.is_symlink():
        return
    if os.name == 'nt':
        # Directory junctions need no administrator rights.
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(target), str(source)], check=True, stdout=subprocess.DEVNULL)
    else:
        target.symlink_to(source, target_is_directory=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--build', default='build-web')
    ap.add_argument('--data', required=True, help='Doom 3 install directory containing base/pak000.pk4')
    ap.add_argument('--native', nargs=3, metavar=('RAILS', 'STAIRS', 'SAVED_RAIL'))
    args = ap.parse_args()
    build, base = Path(args.build), Path(args.data) / 'base'
    if not (base / 'pak000.pk4').is_file():
        sys.exit(f'{base} does not contain pak000.pk4')
    bench = build / 'bench'
    (bench / 'captures').mkdir(parents=True, exist_ok=True)
    shutil.copy(here / 'bench.js', bench / 'bench.js')
    for name, source in FIXTURES.items():
        (bench / f'{name}-fixture.cfg').write_text(fixture(source), encoding='utf-8')
    # Gameplay fixtures run unchanged through run_console_fixture.js.
    for cfg in (root / 'tests').glob('*_parity.cfg'):
        shutil.copy(cfg, bench / cfg.name)
    link(build / 'doom3base', base.resolve())
    if args.native:
        for view, png in zip(('rails', 'stairs', 'saved_rail'), args.native):
            shutil.copy(png, bench / 'captures' / f'native-{view}.png')
    print(f'Prepared {bench}; archives served from {build / "doom3base"}')


if __name__ == '__main__':
    main()
