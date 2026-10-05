"""Extract cylinder/cone vertex generation to check native/web shape precision.

Only the real vertex-generation prefix is executed here. Polygon normals,
mass properties and collision behavior require separate engine comparisons.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
source = (root / 'neo/idlib/geometry/TraceModel.cpp').read_text()
parts = []
for shape in ('Cylinder', 'Cone'):
    start = source.index(f'void idTraceModel::Setup{shape}( const idBounds &')
    end = source.index('// edges', start)
    parts.append(source[start:end] + '}\n}\n')
constants = (root / 'neo/idlib/geometry/TraceModel.h').read_text()
limits = '\n'.join(re.findall(r'^#define MAX_TRACEMODEL_\w+\s+\d+', constants, re.M))
pi = re.search(r'const float\s+idMath::PI\s*=\s*([^;]+);',
               (root / 'neo/idlib/math/Math.cpp').read_text())[1]
header = r'''
#include <math.h>
#include <cstdio>
LIMITS
struct idMath { static const float TWO_PI; };
const float idMath::TWO_PI=2.0f*PI_VALUE;
struct Common { void Printf(const char*,...) {} } traceCommon;
struct idLib { static Common *common; };
Common *idLib::common=&traceCommon;
struct idVec3 {
    float x,y,z;
    void Set(float a,float b,float c){x=a;y=b;z=c;}
    idVec3 operator+(const idVec3 &b)const{return{x+b.x,y+b.y,z+b.z};}
    idVec3 operator-(const idVec3 &b)const{return{x-b.x,y-b.y,z-b.z};}
    idVec3 operator*(float b)const{return{x*b,y*b,z*b};}
};
struct idBounds {
    idVec3 b[2];
    const idVec3 &operator[](int i)const{return b[i];}
};
enum {TRM_CYLINDER,TRM_CONE};
struct idTraceModel {
    int type,numVerts,numEdges,numPolys;
    idVec3 offset,verts[MAX_TRACEMODEL_VERTS];
    void SetupCylinder(const idBounds&,int);
    void SetupCone(const idBounds&,int);
};
'''.replace('LIMITS', limits).replace('PI_VALUE', pi)
fixtures = []
for line in (root / 'tests/trace_shape_native.txt').read_text(encoding='utf-8-sig').splitlines():
    if line and not line.startswith('#'):
        shape, test, vertex, *values = line.split()
        literals = [value + ('f' if '.' in value or 'e' in value else '.0f') for value in values]
        fixtures.append('{' + ','.join((shape, test, vertex, '{' + ','.join(literals) + '}')) + '}')
checks = r'''
int main(){
    struct Expected { int shape,test,vertex; idVec3 value; };
    const Expected expected[]={FIXTURES};
    unsigned count=0;
    const idBounds bounds[]={{{{-3,-3,0},{3,3,11}}},{{{1.25f,-4.75f,.5f},{5.75f,2.25f,12.5f}}}};
    const int sides[]={6,5,10};
    for(int shape=0;shape<2;++shape){
        for(int test=0;test<3;++test){
            idTraceModel model;
            if(shape==0)model.SetupCylinder(bounds[test==0?0:1],sides[test]);
            else model.SetupCone(bounds[test==0?0:1],sides[test]);
            for(int i=0;i<model.numVerts;++i){
                const idVec3 &v=model.verts[i];
                if(count>=sizeof(expected)/sizeof(expected[0]))return 1;
                const Expected &e=expected[count];
                if(e.shape!=shape || e.test!=test || e.vertex!=i ||
                    e.value.x!=v.x || e.value.y!=v.y || e.value.z!=v.z){
                    std::fprintf(stderr,"FAIL shape=%d test=%d vertex=%d: %.9g,%.9g,%.9g / %.9g,%.9g,%.9g\n",
                        shape,test,i,v.x,v.y,v.z,e.value.x,e.value.y,e.value.z);
                    return 1;
                }
                ++count;
            }
        }
    }
    if(count!=sizeof(expected)/sizeof(expected[0]))return 1;
    std::printf("PASS: %u native cylinder/cone vertices\n",count);
}
'''.replace('FIXTURES', ',\n'.join(fixtures))
out = Path(sys.argv[1])
out.write_text(header + '\n'.join(parts) + checks)
print(f'Wrote {out}')
