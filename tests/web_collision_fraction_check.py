"""Check real rotational collision formulas against original MSVC measurements.

The articulated-body replay diverged when collision fraction arithmetic rounded
atan early on web. These synthetic inputs contain no game assets. Both collision
fraction branches are extracted from engine source, rather than reimplemented.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
source = (root / 'neo/cm/CollisionModel_rotate.cpp').read_text()
initial = re.findall(r'tw\.maxTan = initialTan = [^;]+;', source)
fractions = re.findall(r'results->fraction = idMath::Fabs\( atan\([^;]+;', source)
if len(initial) != 1 or len(fractions) != 2:
    raise ValueError('rotational collision formulas missing or ambiguous')

header = r'''
#include <math.h>
#include <cstdio>
#include <cstdlib>
struct idMath {
    static constexpr float PI = 3.14159265358979323846f;
    static float Fabs(float value) { return fabsf(value); }
};
struct TraceWork { float angle, maxTan; };
struct Result { float fraction; };
float initialTangent(float angle) {
    TraceWork tw{angle, 0}; float initialTan;
    INITIAL_FORMULA
    return initialTan;
}
float collisionFraction1(float angle, float maxTan) {
    TraceWork tw{angle, maxTan}; Result result; Result *results = &result;
    FRACTION_FORMULA_1
    return result.fraction;
}
float collisionFraction2(float angle, float maxTan) {
    TraceWork tw{angle, maxTan}; Result result; Result *results = &result;
    FRACTION_FORMULA_2
    return result.fraction;
}
'''.replace('INITIAL_FORMULA', initial[0]).replace('FRACTION_FORMULA_1', fractions[0]).replace('FRACTION_FORMULA_2', fractions[1])

if '--measure' in sys.argv:
    main = r'''
int main() {
    const float angles[] = {0.001f, 0.1f, 1, 5.16506958f, 6.11276245f, 45, 90, 170, -5.16506958f, -45, -170};
    const float ratios[] = {0.01f, 0.1f, 0.25f, 0.5f, 0.75f, 0.99f};
    for (float angle : angles) {
        float initial = initialTangent(angle);
        for (float ratio : ratios) {
            float maxTan = initial * ratio;
            std::printf("%.9g %.9g %.9g %.9g %.9g\n", angle, maxTan, initial,
                collisionFraction1(angle, maxTan), collisionFraction2(angle, maxTan));
        }
    }
}
'''
else:
    rows = [line.split() for line in (root / 'tests/collision_fraction_native.txt').read_text().splitlines()
            if line.strip() and not line.startswith('#')]
    if len(rows) != 66 or any(len(row) != 5 for row in rows):
        raise ValueError('incomplete native collision fraction fixtures')
    cases = ',\n'.join('{' + ','.join(value + 'f' if '.' in value or 'e' in value else value + '.0f' for value in row) + '}' for row in rows)
    main = r'''
int main() {
    struct Case { float angle, maxTan, initial, fraction1, fraction2; };
    Case cases[] = { CASES };
    int count = 0;
    for (const auto &test : cases) {
        float initial = initialTangent(test.angle);
        float first = collisionFraction1(test.angle, test.maxTan);
        float second = collisionFraction2(test.angle, test.maxTan);
        if (initial != test.initial || first != test.fraction1 || second != test.fraction2) {
            std::fprintf(stderr, "FAIL angle %.9g tangent %.9g: %.9g/%.9g %.9g/%.9g %.9g/%.9g\n",
                test.angle, test.maxTan, initial, test.initial, first, test.fraction1, second, test.fraction2);
            return 1;
        }
        ++count;
    }
    std::printf("PASS: %d exact native rotational collision cases\n", count);
}
'''.replace('CASES', cases)

Path(sys.argv[1]).write_text(header + main)
