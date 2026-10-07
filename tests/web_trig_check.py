"""Check the web sinf/cosf ports against native MSVC/UCRT results.

python tests/web_trig_check.py build-web/web-trig-check.cpp
em++ build-web/web-trig-check.cpp -O3 -flto -fno-math-errno -fno-trapping-math \
    -ffinite-math-only -fno-strict-aliasing -ffp-contract=off -msimd128 \
    -sENVIRONMENT=node -sNODERAWFS=1 -o build-web/web-trig-check.js
node build-web/web-trig-check.js [dense-native-dump.bin]

The checked-in fixtures (tests/trig_native.txt) were measured with the native
Windows build's UCRT on an FMA-capable CPU. An optional dense dump from
build-web/libm_dump.c compiled with MSVC adds about a million more inputs.
"""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
source = (root / 'neo/idlib/math/WebMath.h').read_text(encoding='utf-8')
start = source.index('static ID_INLINE double WebLibmDouble(')
end = source.rindex('#endif')
ported = source[start:end]

fixtures = []
for line in (root / 'tests/trig_native.txt').read_text(encoding='utf-8').splitlines():
    if line and not line.startswith('#'):
        x, s, c = line.split()
        fixtures.append(f'{{0x{x}u,0x{s}u,0x{c}u}}')

program = r'''
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#define ID_INLINE inline
using std::fma; using std::sin; using std::cos;
// Calls through pointers reach the linked symbols, not compiler builtins.
extern "C" float sinf( float ); extern "C" float cosf( float );
static float ( *volatile linkedSin )( float ) = sinf;
static float ( *volatile linkedCos )( float ) = cosf;
''' + ported + r'''
struct Fixture { uint32_t x, s, c; };
static const Fixture fixtures[] = { FIXTURES };
static uint32_t bits(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }
static float flt(uint32_t u) { float f; memcpy(&f, &u, 4); return f; }
int main(int argc, char **argv) {
    int checked = 0, failures = 0;
    for (const Fixture &f : fixtures) {
        const float x = flt(f.x);
        if (bits(WebSinf(x)) != f.s || bits(WebCosf(x)) != f.c ||
            bits(linkedSin(x)) != f.s || bits(linkedCos(x)) != f.c) {
            if (failures++ < 10) std::fprintf(stderr, "FAIL fixture x=%a sin %08x/%08x/%08x cos %08x/%08x/%08x (port/linked/native)\n",
                x, bits(WebSinf(x)), bits(linkedSin(x)), f.s, bits(WebCosf(x)), bits(linkedCos(x)), f.c);
        }
        ++checked;
    }
    if (argc > 1) {
        // libm_dump.c record: x, y, then sinf, cosf, ... as 32-bit words.
        FILE *in = std::fopen(argv[1], "rb");
        if (!in) { std::fprintf(stderr, "cannot open %s\n", argv[1]); return 2; }
        uint32_t record[12];
        while (std::fread(record, 4, 12, in) == 12) {
            const float x = flt(record[0]);
            if (bits(WebSinf(x)) != record[2] || bits(WebCosf(x)) != record[3]) {
                if (failures++ < 10) std::fprintf(stderr, "FAIL dense x=%a sin %08x/%08x cos %08x/%08x\n",
                    x, bits(WebSinf(x)), record[2], bits(WebCosf(x)), record[3]);
            }
            ++checked;
        }
        std::fclose(in);
    }
    if (failures) { std::fprintf(stderr, "%d of %d sinf/cosf results differ from native\n", failures, checked); return 1; }
    std::printf("PASS: %d exact native sinf/cosf results\n", checked);
    return 0;
}
'''.replace('FIXTURES', ','.join(fixtures))
Path(sys.argv[1]).write_text(program, encoding='utf-8')
print(f'Wrote {sys.argv[1]} ({len(fixtures)} fixtures)')
