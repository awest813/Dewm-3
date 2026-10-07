"""Capture native reference views for a render fixture.

python tests/web_bench/native_capture.py --exe build-windows/RelWithDebInfo/dhewm3.exe \
    --data "C:/.../Doom 3" --fixture scenes [--out build-web/bench/captures] [--label native]

Runs the native engine on tests/render_<fixture>_parity.cfg with private save
and config directories, then copies its screenshots in order to
<out>/<label>-<view>.png. Views come from the fixture's echo markers. The
native engine also writes its console log under the user's documents folder
(My Games/dhewm3); a copy is saved as <out>/<label>-<fixture>-console.txt.
"""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
FIXTURES = {'hangar': 'tests/render_hangar_parity.cfg', 'scenes': 'tests/render_scenes_parity.cfg'}


def views(source):
    text = (root / source).read_text(encoding='utf-8')
    return re.findall(r'^echo (?:HANGAR_VIEW|SCENE_VIEW) (\S+)', text, re.M)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--exe', required=True)
    ap.add_argument('--data', required=True, help='Doom 3 install directory containing base/')
    ap.add_argument('--fixture', default='scenes', choices=sorted(FIXTURES))
    ap.add_argument('--out', default='build-web/bench/captures')
    ap.add_argument('--label', default='native')
    ap.add_argument('--timeout', type=int, default=900)
    args = ap.parse_args()
    names = [v.replace('-', '_') for v in views(FIXTURES[args.fixture])]
    # The engine runs from its own directory (next to its DLLs).
    exe = Path(args.exe).resolve()
    if not exe.is_file():
        sys.exit(f'{exe} does not exist')
    with tempfile.TemporaryDirectory(prefix='dhewm3-native-') as work:
        base = Path(work) / 'base'
        base.mkdir()
        shutil.copy(root / FIXTURES[args.fixture], base / 'fixture.cfg')
        subprocess.run([str(exe), '+set', 'fs_basepath', args.data, '+set', 'fs_savepath', work,
                        '+set', 'fs_configpath', work, '+set', 'r_fullscreen', '0', '+set', 'r_mode', '3',
                        '+exec', 'fixture.cfg'], cwd=exe.parent, timeout=args.timeout, check=False)
        shots = sorted((base / 'screenshots').glob('shot*.png'))
        if len(shots) != len(names):
            sys.exit(f'expected {len(names)} screenshots, found {len(shots)}')
        os.makedirs(args.out, exist_ok=True)
        for name, shot in zip(names, shots):
            shutil.copy(shot, Path(args.out) / f'{args.label}-{name}.png')
    logs = [p for p in (Path.home() / 'Documents/My Games/dhewm3/dhewm3log.txt',
                        Path.home() / 'OneDrive/Documents/My Games/dhewm3/dhewm3log.txt') if p.is_file()]
    if logs:
        newest = max(logs, key=lambda p: p.stat().st_mtime)
        shutil.copy(newest, Path(args.out) / f'{args.label}-{args.fixture}-console.txt')
    print(f'Wrote {len(names)} native views: {", ".join(names)}')


if __name__ == '__main__':
    main()
