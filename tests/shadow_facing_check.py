"""Extract the web triangle-facing kernel and compare the original generic passes.

Exact classifications protect shadow geometry. The alternating benchmark measures
this kernel alone; it does not establish a whole-game frame-rate improvement.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
simd = (root / 'neo/idlib/math/Simd_Generic.cpp').read_text()
interaction = (root / 'neo/renderer/Interaction.cpp').read_text()
vector = (root / 'neo/idlib/math/Vector.h').read_text()


def function(source, signature):
    start = source.index(signature)
    depth = 0
    for end in range(source.index('{', start), len(source)):
        depth += (source[end] == '{') - (source[end] == '}')
        if not depth:
            return source[start:end + 1]
    raise ValueError('incomplete function ' + signature)


dot = function(simd, 'void VPCALL idSIMD_Generic::Dot( float *dst, const idVec3 &constant, const idPlane *src, const int count )')
compare = function(simd, 'void VPCALL idSIMD_Generic::CmpGE( byte *dst, const float *src0, const float constant, const int count )')
helper = function(interaction, 'static void R_CalcInteractionFacingWeb(')
vecdot = re.search(r'ID_INLINE float idVec3::operator\*\( const idVec3 &a \) const \{([^}]+)\}', vector).group(1)
unroll = '\n'.join(re.findall(r'^#define UNROLL[14]\(Y\).*$', simd, re.M))
if not re.search(r'R_CalcInteractionFacingWeb\( cullInfo\.facing, localLightOrigin, tri->facePlanes, numFaces \)', interaction):
    raise ValueError('renderer does not call the tested helper')
if not re.search(r'cullInfo\.facing\[ numFaces \] = 1;', interaction):
    raise ValueError('dangling-edge facing sentinel missing')

prefix = r'''
#include <cstdio>
#include <cstring>
#include <cmath>
#include <vector>
#include <algorithm>
#include <limits>
#include <emscripten.h>
using byte = unsigned char;
#define VPCALL
struct idVec3 {float x,y,z;float operator*(const idVec3 &a)const{VECDOT}};
struct idPlane {idVec3 n;float d;const idVec3 &Normal()const{return n;}float operator[](int)const{return d;}};
static_assert(sizeof(idPlane)==16,"real plane stride");
class idSIMD_Generic {public:
 __attribute__((noinline)) void Dot(float*,const idVec3&,const idPlane*,int);
 __attribute__((noinline)) void CmpGE(byte*,const float*,float,int);
};
'''.replace('VECDOT', vecdot)
main = r'''
__attribute__((noinline)) void reference(byte *bits,const idVec3 &origin,const idPlane *planes,int count){
 float *distance=(float*)__builtin_alloca(count*sizeof(float));
 idSIMD_Generic processor;processor.Dot(distance,origin,planes,count);
 processor.CmpGE(bits,distance,0.f,count);bits[count]=1;
}
WEB_HELPER
__attribute__((noinline)) void candidate(byte *bits,const idVec3 &origin,const idPlane *planes,int count){
 R_CalcInteractionFacingWeb(bits,origin,planes,count);bits[count]=1;
}
unsigned seed=1305;
float randomFloat(){seed=1664525u*seed+1013904223u;return (int(seed>>8)-8388608)*0.000123f;}
volatile unsigned checksum=0;
int main(){
 size_t checked=0;
 for(int count:{0,1,2,3,4,5,16,63,64,65,255,256,257,1000,4096}){
  std::vector<idPlane> planes(count);
  for(int run=0;run<32;run++)for(int scenario=0;scenario<3;scenario++){
   idVec3 origin={randomFloat(),randomFloat(),randomFloat()};
   for(int i=0;i<count;i++){
    if(scenario==0)planes[i]={{randomFloat(),randomFloat(),randomFloat()},randomFloat()};
    if(scenario==1){float d=-origin.x;planes[i]={{1,0,0},i%3==0?d:std::nextafter(d,i%3==1?std::numeric_limits<float>::lowest():std::numeric_limits<float>::max())};}
    if(scenario==2){origin={0,0,0};float tiny=std::numeric_limits<float>::denorm_min();
     planes[i]={{i%2?0.f:-0.f,0,0},i%4==0?0.f:i%4==1?-0.f:i%4==2?tiny:-tiny};}
   }
   std::vector<byte> a(count+3,123),b(count+3,123);
   reference(a.data()+1,origin,planes.data(),count);candidate(b.data()+1,origin,planes.data(),count);
   if(a!=b||a.front()!=123||a.back()!=123||a[count+1]!=1){
    std::fprintf(stderr,"FAIL facing count=%d run=%d scenario=%d\n",count,run,scenario);return 1;}
   checked+=count;
  }
 }
 std::printf("PASS %zu exact facing classifications, random planes, zero and adjacent boundaries, signed zero, subnormals, edge counts, sentinel and guards\n",checked);
 for(int count:{32,256,2048}){
  std::vector<idPlane> planes(count);for(auto &p:planes)p={{randomFloat(),randomFloat(),randomFloat()},randomFloat()};
  idVec3 origin={randomFloat(),randomFloat(),randomFloat()};std::vector<byte> bits(count+1);
  auto sample=[&](auto fn){double start=emscripten_get_now();for(int i=0;i<12000000/count;i++){
   fn(bits.data(),origin,planes.data(),count);checksum+=bits[i%count];}return emscripten_get_now()-start;};
  sample(reference);sample(candidate);std::vector<double> a,b;
  for(int run=0;run<9;run++){if(run%2){b.push_back(sample(candidate));a.push_back(sample(reference));}
   else{a.push_back(sample(reference));b.push_back(sample(candidate));}}
  std::sort(a.begin(),a.end());std::sort(b.begin(),b.end());
  std::printf("BENCH count=%d reference=%.3fms fused=%.3fms ratio=%.3f\n",count,a[4],b[4],b[4]/a[4]);
 }
 std::printf("checksum=%u\n",checksum);
}
'''.replace('WEB_HELPER', helper)
Path(sys.argv[1]).write_text(prefix + unroll + '\n' + dot + '\n' + compare + '\n' + main)
