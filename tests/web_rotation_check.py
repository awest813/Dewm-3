"""Extract actual quaternion reconstruction and check original MSVC fixtures.

The near-identity case reproduces combat frame 867's collision rotation drift.
Inputs are numeric matrices; no proprietary models, maps or scripts are included.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]


def function(path, signature):
    source = (root/path).read_text()
    start = source.index(signature)
    depth = 0
    for end in range(source.index('{', start), len(source)):
        depth += (source[end] == '{') - (source[end] == '}')
        if not depth:
            return source[start:end+1].replace('ID_INLINE ', '')
    raise ValueError('incomplete function ' + signature)


pi = re.search(r"const float\s+idMath::PI\s*=\s*([^;]+);", (root/"neo/idlib/math/Math.cpp").read_text())[1]
header = r'''
#include <math.h>
#include <cstdio>
#include <cassert>
#include <cstring>
using dword=unsigned int;
struct idMath {
 static constexpr float PI=PI_VALUE, M_RAD2DEG=180.f/PI;
 enum {LOOKUP_BITS=8,EXP_POS=23,EXP_BIAS=127,LOOKUP_POS=EXP_POS-LOOKUP_BITS,SEED_POS=EXP_POS-8,SQRT_TABLE_SIZE=2<<LOOKUP_BITS,LOOKUP_MASK=SQRT_TABLE_SIZE-1};
 union _flint {dword i;float f;};static dword iSqrt[SQRT_TABLE_SIZE];static bool initialized;
 static void Init();static float InvSqrt(float);static float ACos(float);static float Fabs(float x){return fabsf(x);}
};
dword idMath::iSqrt[idMath::SQRT_TABLE_SIZE];bool idMath::initialized=false;
struct idVec3 {
 float x,y,z;float &operator[](int i){return (&x)[i];}float operator[](int i)const{return (&x)[i];}
 void Zero(){x=y=z=0;}void Set(float a,float b,float c){x=a;y=b;z=c;}
 float Normalize();bool FixDegenerateNormal();
};
struct idRotation;
struct idMat3 {idVec3 mat[3];idVec3 &operator[](int i){return mat[i];}const idVec3 &operator[](int i)const{return mat[i];}idRotation ToRotation()const;};
struct idRotation {float angle;idVec3 vec,origin;idMat3 axis;bool axisValid;};
'''
header = header.replace("PI_VALUE", pi)
functions = [function(path, signature) for path, signature in (
    ('neo/idlib/math/Math.cpp', 'void idMath::Init( void ) {'),
    ('neo/idlib/math/Math.h', 'ID_INLINE float idMath::InvSqrt( float x ) {'),
    ('neo/idlib/math/Math.h', 'ID_INLINE float idMath::ACos( float a ) {'),
    ('neo/idlib/math/Vector.h', 'ID_INLINE float idVec3::Normalize( void ) {'),
    ('neo/idlib/math/Vector.h', 'ID_INLINE bool idVec3::FixDegenerateNormal( void ) {'),
    ('neo/idlib/math/Matrix.cpp', 'idRotation idMat3::ToRotation( void ) const {'))]
if '--measure' in sys.argv:
    main = r'''
int main(){ idMath::Init(); volatile float input[][9]={
 {0.999018669f,-0.0115571022f,-0.0427546352f,0.00776860118f,0.99611336f,-0.0877376348f,0.0436024517f,0.087319389f,0.995225728f},
 {1,0,0,0,1,0,0,0,1}, {1.000001f,0,0,0,1.000001f,0,0,0,1.000001f},
 {1,0,0,0,-1,0,0,0,-1}, {-1,0,0,0,1,0,0,0,-1}, {-1,0,0,0,-1,0,0,0,1},
 {0,1,0,-1,0,0,0,0,1}, {0,-1,0,1,0,0,0,0,1},
 {1,0,0,0,0.99619472f,0.0871557444f,0,-0.0871557444f,0.99619472f},
 {0.98480773f,-0.173648179f,0,0.173648179f,0.98480773f,0,0,0,1}
};
for(auto &values:input){ idMat3 m;for(int i=0;i<9;i++)m[i/3][i%3]=values[i];
 idRotation r=m.ToRotation();for(int i=0;i<9;i++)std::printf("%.9g ",values[i]);
 std::printf("%.9g %.9g %.9g %.9g\n",r.angle,r.vec.x,r.vec.y,r.vec.z);
}}
'''
else:
    rows = []
    for line in (root/'tests/rotation_native.txt').read_text().splitlines():
        if line.startswith('#') or not line.strip():
            continue
        if len(line.split()) != 13 or not all(re.fullmatch(r'-?\d+(?:\.\d+)?(?:e[+-]?\d+)?', value) for value in line.split()):
            raise ValueError('malformed native rotation fixture')
        rows.append('{'+','.join(value+'f' if '.' in value or 'e' in value else value+'.0f' for value in line.split())+'}')
    if len(rows) != 10:
        raise ValueError('incomplete native rotation fixtures')
    main = r'''
int main(){idMath::Init();float cases[][13]={CASES};int index=0;
for(auto &values:cases){idMat3 m;for(int i=0;i<9;i++)m[i/3][i%3]=values[i];idRotation r=m.ToRotation();
 float actual[]={r.angle,r.vec.x,r.vec.y,r.vec.z};for(int i=0;i<4;i++)if(actual[i]!=values[i+9]){
  std::fprintf(stderr,"FAIL rotation case=%d field=%d actual=%.9g expected=%.9g\n",index,i,actual[i],values[i+9]);return 1;}
 ++index;
}std::printf("PASS %d exact native quaternion-to-rotation cases, near identity, endpoint clamp, three diagonal branches and signed rotations\n",index);}
'''.replace('CASES', ',\n'.join(rows))
Path(sys.argv[1]).write_text(header+'\n'.join(functions)+'\n'+main)
