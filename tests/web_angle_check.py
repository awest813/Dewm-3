"""Extract real vector/matrix angle conversion and compare with native fixtures.

The equal-coordinate campaign vector exposed early atan2f rounding that changed
AI head-alignment branches and random draws. Golden values were measured using
the original conversion with the project's MSVC toolchain, not a float atan2
oracle. No game data is included.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
def function(path, signature):
    source = (root / path).read_text()
    start = source.index(signature)
    depth = 0
    for index in range(source.index('{', start), len(source)):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if not depth:
                return source[start:index + 1]
    raise ValueError(f'Incomplete function {signature}')


yaw = function('neo/idlib/math/Vector.cpp', 'float idVec3::ToYaw( void ) const {')
matrix_angles = function('neo/idlib/math/Matrix.cpp', 'idAngles idMat3::ToAngles( void ) const {')
math_source = (root / 'neo/idlib/math/Math.cpp').read_text()
pi = re.search(r'const float\s+idMath::PI\s*=\s*([^;]+);', math_source)[1]
header = r'''
#include <math.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
struct idMath { static const float PI, M_RAD2DEG, FLT_EPSILON; };
const float idMath::PI = PI_VALUE;
const float idMath::M_RAD2DEG = 180.0f / idMath::PI;
const float idMath::FLT_EPSILON = 1.192092896e-07f;
#define RAD2DEG(a) ((a) * idMath::M_RAD2DEG)
struct idVec3 { float x,y,z; float ToYaw() const; };
struct idAngles { float pitch,yaw,roll; };
struct idMat3 { float mat[3][3]; idAngles ToAngles() const; };
'''.replace('PI_VALUE', pi)
checks = r'''
int main() {
    struct Case { float x,y,expected; } cases[] = {
        {1,0,0}, {0,1,89.9999924f}, {-1,0,179.999985f}, {0,-1,270},
        {1,1,44.9999962f}, {-1,1,135}, {-1,-1,225}, {1,-1,315},
        {362.038574f,362.038574f,44.9999962f}, {0,0,0}
    };
    int count=0;
    for (const auto &test : cases) {
        idVec3 v{test.x,test.y,0};
        float actual=v.ToYaw();
        if (actual != test.expected) {
            std::fprintf(stderr,"FAIL yaw %.9g,%.9g: %.9g / %.9g\n",v.x,v.y,actual,test.expected);
            return 1;
        }
        ++count;
    }
    idMat3 matrices[] = {
        {{{1,0,0},{0,1,0},{0,0,1}}},
        {{{.707106769f,.707106769f,0},{-.707106769f,.707106769f,0},{0,0,1}}},
        {{{-.707106769f,.707106769f,0},{-.707106769f,-.707106769f,0},{0,0,1}}},
        {{{.866025388f,0,.5f},{0,1,0},{-.5f,0,.866025388f}}},
        {{{.866025388f,0,-.5f},{0,1,0},{.5f,0,.866025388f}}},
        // Near gimbal lock and non-unit input exercise both branches and the
        // existing sin clamp; these last inputs intentionally include drift.
        {{{1,0,.999999f},{-.707106769f,.707106769f,.3f},{0,0,.7f}}},
        {{{1,0,.9999999f},{-.707106769f,.707106769f,.3f},{0,0,.7f}}},
        {{{1,0,1.01f},{-.707106769f,.707106769f,.3f},{0,0,.7f}}},
        {{{1,0,-1.01f},{-.707106769f,.707106769f,.3f},{0,0,.7f}}},
        {{{1,0,0},{0,.866025388f,.5f},{0,-.5f,.866025388f}}}
    };
    const idAngles expected[] = {
        {0,0,0}, {0,44.9999962f,0}, {0,135,0},
        {-29.9999981f,0,0}, {29.9999981f,0,0},
        {-89.9184341f,0,23.1985912f}, {-89.9720154f,44.9999962f,0},
        {-89.9999924f,44.9999962f,0}, {89.9999924f,44.9999962f,0},
        {0,0,29.9999981f}
    };
    for (unsigned i=0; i<sizeof(matrices)/sizeof(matrices[0]); ++i) {
        const idAngles a=matrices[i].ToAngles(), e=expected[i];
        if (a.pitch!=e.pitch || a.yaw!=e.yaw || a.roll!=e.roll) {
            std::fprintf(stderr,"FAIL matrix %u: %.9g,%.9g,%.9g / %.9g,%.9g,%.9g\n",
                i,a.pitch,a.yaw,a.roll,e.pitch,e.yaw,e.roll);
            return 1;
        }
        ++count;
    }
    std::printf("PASS: %d native vector/matrix-angle fixtures\n",count);
}
'''
out = Path(sys.argv[1])
out.write_text(header + yaw + matrix_angles + checks)
print(f'Wrote {out}')
