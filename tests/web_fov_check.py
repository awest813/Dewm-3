"""Check the real aspect-ratio FOV calculation against measured native values.

The fixtures were captured from the original MSVC engine calculation, before
explicit double casts. Float math.h overloads in Emscripten change its output.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
source = (root / 'neo/game/Game_local.cpp').read_text()
start = source.index('void idGameLocal::CalcFov(')
depth = 0
for end in range(source.index('{', start), len(source)):
    if source[end] == '{':
        depth += 1
    elif source[end] == '}':
        depth -= 1
        if not depth:
            break
body = source[start:end + 1]
pi = re.search(r'const float\s+idMath::PI\s*=\s*([^;]+);',
               (root / 'neo/idlib/math/Math.cpp').read_text())[1]
header = r'''
#include <math.h>
#include <cstdio>
#include <cstdlib>
#include <cassert>
struct idMath { static const float PI; };
const float idMath::PI = PI_VALUE;
struct Aspect { int value; int GetInteger() const { return value; } } r_aspectRatio;
struct Screen {
    int width, height;
    int GetScreenWidth() const { return width; }
    int GetScreenHeight() const { return height; }
} screen;
Screen *renderSystem = &screen;
struct idGameLocal {
    void CalcFov(float, float&, float&) const;
    void Error(const char*, ...) const { std::abort(); }
};
'''.replace('PI_VALUE', pi)
fixtures = []
for line in (root / 'tests/fov_native.txt').read_text(encoding='utf-8-sig').splitlines():
    if line and not line.startswith('#'):
        base, aspect, width, height, x, y = line.split()
        fixtures.append(f'{{{base}.0f,{aspect},{width},{height},{x}f,{y}f}}')
# C++ requires a decimal point on float literals that happen to be integers.
fixtures = [re.sub(r'(?<![.\d])(-?\d+)f\b', r'\1.0f', row) for row in fixtures]
checks = r'''
int main() {
    idGameLocal game;
    struct Case { float base; int aspect,width,height; float x,y; };
    const Case cases[] = {FIXTURES};
    unsigned count=0;
    for (const auto &test : cases) {
        r_aspectRatio.value=test.aspect;
        screen.width=test.width; screen.height=test.height;
        float x,y;
        game.CalcFov(test.base,x,y);
        if (x != test.x || y != test.y) {
            std::fprintf(stderr,"FAIL FOV %.0f aspect=%d %dx%d: %.9g,%.9g / %.9g,%.9g\n",
                test.base,test.aspect,test.width,test.height,x,y,test.x,test.y);
            return 1;
        }
        ++count;
    }
    std::printf("PASS: %u native FOV fixtures\n",count);
}
'''.replace('FIXTURES', ',\n'.join(fixtures))
out = Path(sys.argv[1])
out.write_text(header + body + checks)
print(f'Wrote {out}')
