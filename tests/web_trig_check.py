"""Check the web float libm ports against native MSVC/UCRT results.

python tests/web_trig_check.py build-web/web-trig-check.cpp
em++ build-web/web-trig-check.cpp -O3 -flto -fno-math-errno -fno-trapping-math \
    -ffinite-math-only -fno-strict-aliasing -ffp-contract=off -msimd128 \
    -sENVIRONMENT=node -sNODERAWFS=1 -o build-web/web-trig-check.js
node build-web/web-trig-check.js [dense-native-dump.bin]

The checked-in fixtures (tests/trig_native.txt for sinf/cosf,
tests/libm_native.txt for tanf, asinf, acosf, atanf, atan2f, expf and logf,
tests/libm_double_native.txt for double sin, cos, tan, atan, asin, acos, atan2)
were measured with the native Windows build's UCRT on an FMA-capable CPU.
Each is checked through the port and through the linked symbol, so musl's
definitions must not win. NaN results compare as NaN; payloads are not
checked. An optional dense dump from build-web/libm_dump.c compiled with MSVC
adds about a million more sinf/cosf inputs.
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

names = ['tanf', 'asinf', 'acosf', 'atanf', 'expf', 'logf', 'atan2f']
others = []
for line in (root / 'tests/libm_native.txt').read_text(encoding='utf-8').splitlines():
    if line and not line.startswith('#'):
        parts = line.split()
        x, y, r = (parts[1], '0', parts[2]) if len(parts) == 3 else parts[1:]
        others.append(f'{{{names.index(parts[0])},0x{x}u,0x{y}u,0x{r}u}}')

dnames = ['sin', 'cos', 'tan', 'atan', 'asin', 'acos', 'atan2']
doubles = []
for line in (root / 'tests/libm_double_native.txt').read_text(encoding='utf-8').splitlines():
    if line and not line.startswith('#'):
        parts = line.split()
        x, y, r = (parts[1], '0', parts[2]) if len(parts) == 3 else parts[1:]
        doubles.append(f'{{{dnames.index(parts[0])},0x{x}ull,0x{y}ull,0x{r}ull}}')

program = r'''
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#define ID_INLINE inline
using std::fma; using std::fmaf; using std::sqrtf; using std::nearbyint;
// Calls through pointers reach the linked symbols, not compiler builtins.
extern "C" float sinf( float ); extern "C" float cosf( float );
extern "C" float tanf( float ); extern "C" float asinf( float ); extern "C" float acosf( float );
extern "C" float atanf( float ); extern "C" float expf( float ); extern "C" float logf( float );
extern "C" float atan2f( float, float );
static float ( *volatile linkedSin )( float ) = sinf;
static float ( *volatile linkedCos )( float ) = cosf;
static float ( *volatile linked1[] )( float ) = { tanf, asinf, acosf, atanf, expf, logf };
static float ( *volatile linkedAtan2 )( float, float ) = atan2f;
extern "C" double sin( double ); extern "C" double cos( double ); extern "C" double tan( double );
extern "C" double atan( double ); extern "C" double asin( double ); extern "C" double acos( double );
extern "C" double atan2( double, double );
static double ( *volatile linkedD[] )( double ) = { sin, cos, tan, atan, asin, acos };
static double ( *volatile linkedDAtan2 )( double, double ) = atan2;
''' + ported + r'''
struct Fixture { uint32_t x, s, c; };
static const Fixture fixtures[] = { FIXTURES };
struct Other { int fn; uint32_t x, y, r; };
static const Other others[] = { OTHERS };
struct DFixture { int fn; uint64_t x, y, r; };
static const DFixture doubles[] = { DOUBLES };
static const char *dnames[] = { "sin", "cos", "tan", "atan", "asin", "acos", "atan2" };
static uint64_t dbits(double d) { uint64_t u; memcpy(&u, &d, 8); return u; }
static double dbl(uint64_t u) { double d; memcpy(&d, &u, 8); return d; }
static bool dsame(double d, uint64_t r) { return dbits(d) == r || (std::isnan(d) && (r & 0x7fffffffffffffffull) > 0x7ff0000000000000ull); }
static const char *names[] = { "tanf", "asinf", "acosf", "atanf", "expf", "logf", "atan2f" };
static uint32_t bits(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }
static bool isNan(uint32_t u) { return (u & 0x7fffffffu) > 0x7f800000u; }
static bool same(float f, uint32_t r) { return bits(f) == r || (isNan(bits(f)) && isNan(r)); }
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
    float (*ports[])(float) = { WebTanf, WebAsinf, WebAcosf, WebAtanf, WebExpf, WebLogf };
    for (const Other &o : others) {
        const float x = flt(o.x), y = flt(o.y);
        const float p = o.fn == 6 ? WebAtan2f(x, y) : ports[o.fn](x);
        const float l = o.fn == 6 ? linkedAtan2(x, y) : linked1[o.fn](x);
        if (!same(p, o.r) || !same(l, o.r)) {
            if (failures++ < 10) std::fprintf(stderr, "FAIL %s(%a, %a) %08x/%08x/%08x (port/linked/native)\n",
                names[o.fn], x, y, bits(p), bits(l), o.r);
        }
        ++checked;
    }
    double (*dports[])(double) = { WebSin, WebCos, WebTan, WebAtan, WebAsin, WebAcos };
    for (const DFixture &o : doubles) {
        const double x = dbl(o.x), y = dbl(o.y);
        const double p = o.fn == 6 ? WebAtan2(x, y) : dports[o.fn](x);
        const double l = o.fn == 6 ? linkedDAtan2(x, y) : linkedD[o.fn](x);
        if (!dsame(p, o.r) || !dsame(l, o.r)) {
            if (failures++ < 10) std::fprintf(stderr, "FAIL %s(%a, %a) %016llx/%016llx/%016llx (port/linked/native)\n",
                dnames[o.fn], x, y, (unsigned long long)dbits(p), (unsigned long long)dbits(l), (unsigned long long)o.r);
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
    if (failures) { std::fprintf(stderr, "%d of %d float libm results differ from native\n", failures, checked); return 1; }
    std::printf("PASS: %d exact native float libm results\n", checked);
    return 0;
}
'''.replace('FIXTURES', ','.join(fixtures)).replace('OTHERS', ','.join(others)).replace('DOUBLES', ','.join(doubles))
Path(sys.argv[1]).write_text(program, encoding='utf-8')
print(f'Wrote {sys.argv[1]} ({len(fixtures) + len(others) + len(doubles)} fixtures)')
