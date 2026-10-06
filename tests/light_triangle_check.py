"""Compare the real web light-triangle filter with the original loop/generic bounds pass.

The harness covers accepted index order, exact bound bits, input preservation and
output guards. Its alternating benchmark measures this kernel, not game FPS.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
interaction = (root / 'neo/renderer/Interaction.cpp').read_text()
simd = (root / 'neo/idlib/math/Simd_Generic.cpp').read_text()
bounds = (root / 'neo/idlib/bv/Bounds.h').read_text()
math = (root / 'neo/idlib/math/Math.cpp').read_text()


def block(source, signature):
    start = source.index(signature)
    depth = 0
    for end in range(source.index('{', start), len(source)):
        depth += (source[end] == '{') - (source[end] == '}')
        if not depth:
            return source[start:end + 1]
    raise ValueError('incomplete ' + signature)


helper = block(interaction, 'static int R_FilterLightTrianglesWeb(')
create = block(interaction, 'static srfTriangles_t *R_CreateLightTris(')
loop = block(create, 'for ( faceNum = i = 0;')
if create.count('R_FilterLightTrianglesWeb(') != 1:
    raise ValueError('missing or duplicate production filter integration')
minmax = block(simd, 'void VPCALL idSIMD_Generic::MinMax( idVec3 &min, idVec3 &max, const idDrawVert *src, const int *indexes, const int count )')
clear = block(bounds, 'ID_INLINE void idBounds::Clear(').replace('ID_INLINE', 'inline')
add = block(bounds, 'ID_INLINE bool idBounds::AddPoint(').replace('ID_INLINE', 'inline')
infinity = re.search(r'const float\s+idMath::INFINITY\s*=\s*([^;]+);', math).group(1)
unroll = '\n'.join(re.findall(r'^#define UNROLL[14]\(Y\).*$', simd, re.M))
prefix = r'''
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <vector>
#include <algorithm>
#include <limits>
#include <emscripten.h>
#undef INFINITY
using byte=unsigned char;using glIndex_t=int;
#define VPCALL
namespace idMath {constexpr float INFINITY=INFINITY_VALUE;}
struct idVec3 {float v[3];float &operator[](int i){return v[i];}float operator[](int i)const{return v[i];}};
struct idBounds {idVec3 b[2];idVec3 &operator[](int i){return b[i];}void Clear();bool AddPoint(const idVec3 &v);};
struct idDrawVert {idVec3 xyz;byte rest[48];};
static_assert(sizeof(idDrawVert)==60,"real vertex stride");
static_assert(sizeof(idBounds)==24,"real bounds layout");
struct srfTriangles_t {int numIndexes;const glIndex_t *indexes;};
class idSIMD_Generic {public:__attribute__((noinline)) void MinMax(idVec3&,idVec3&,const idDrawVert*,const int*,int);};
'''.replace('INFINITY_VALUE', infinity)
reference = r'''
__attribute__((noinline)) int reference(glIndex_t *indexes,idBounds &bounds,const idDrawVert *verts,
 const glIndex_t *src,const byte *facing,int count){
 srfTriangles_t data{count,src};const srfTriangles_t *tri=&data;
 int i,faceNum,numIndexes=0,c_backfaced=0;
 ORIGINAL_LOOP
 idSIMD_Generic().MinMax(bounds[0],bounds[1],verts,indexes,numIndexes);return numIndexes;
}
'''.replace('ORIGINAL_LOOP', loop)
main = r'''
__attribute__((noinline)) int candidate(glIndex_t *dst,idBounds &bounds,const idDrawVert *verts,
 const glIndex_t *src,const byte *facing,int count){return R_FilterLightTrianglesWeb(dst,bounds,verts,src,facing,count);}
unsigned seed=1305;unsigned rng(){seed=1664525u*seed+1013904223u;return seed;}
float randomFloat(){return (int(rng()>>8)-8388608)*.000123f;}
volatile unsigned checksum=0;
int main(){
 size_t checkedFaces=0,cases=0;
 for(int faces:{0,1,2,3,4,5,16,32,63,64,65,127,128,255,256,257,1000,2048,4096}){
  int nv=std::max(1,2*faces+5),count=faces*3;
  for(int run=0;run<32;run++)for(int scenario=0;scenario<7;scenario++){
   std::vector<idDrawVert> verts(nv);
   for(int i=0;i<nv;i++){std::memset(&verts[i],0x5a,sizeof(idDrawVert));for(int k=0;k<3;k++){
    float v=randomFloat();
    if(scenario==2 || scenario==5)v=(i+k)%2?0.f:-0.f;
    if(scenario==4)v=(i+k)%2?std::numeric_limits<float>::max():std::numeric_limits<float>::lowest();
    if(scenario==6)v=(i+k)%2?std::numeric_limits<float>::denorm_min():-std::numeric_limits<float>::denorm_min();
    verts[i].xyz[k]=v;
   }}
   std::vector<glIndex_t> src(count),a(count+2,-123),b(count+2,-123);
   for(auto &i:src)i=scenario==4?0:int(rng()%nv);
   std::vector<byte> facing(faces+1,1);
   for(int i=0;i<faces;i++){
    facing[i]=rng()%4?byte((rng()%2)?1:255):0;
    if(scenario==1)facing[i]=0;
    if(scenario==2 || scenario==4)facing[i]=1;
    if(scenario==3)facing[i]=i==faces-1?2:0;
    if(scenario==5 || scenario==6)facing[i]=i%2;
   }
   auto originalVerts=verts;auto originalSrc=src;auto originalFacing=facing;
   idBounds ba,bb;
   int na=reference(a.data()+1,ba,verts.data(),src.data(),facing.data(),count);
   int nb=candidate(b.data()+1,bb,verts.data(),src.data(),facing.data(),count);
   if(na!=nb || std::memcmp(&ba,&bb,sizeof ba) || a!=b || a.front()!=-123 || a.back()!=-123 ||
      src!=originalSrc || facing!=originalFacing || std::memcmp(verts.data(),originalVerts.data(),nv*sizeof(idDrawVert))){
    std::fprintf(stderr,"FAIL faces=%d run=%d scenario=%d\n",faces,run,scenario);return 1;
   }
   checkedFaces+=faces;cases++;
  }
 }
 std::printf("PASS: %zu light-triangle cases, %zu input faces; exact index order and bound bits, empty/prefix/dense/sparse selections, signed zero, subnormals, finite extremes, repeated indices, input preservation and output guards\n",cases,checkedFaces);
 for(int faces:{32,256,2048})for(int percent:{0,25,50,100}){
  int nv=faces*2,count=faces*3;std::vector<idDrawVert> verts(nv);std::vector<glIndex_t> src(count),dst(count);
  std::vector<byte> facing(faces);for(auto &v:verts)for(int k=0;k<3;k++)v.xyz[k]=randomFloat();
  for(auto &i:src)i=rng()%nv;for(auto &f:facing)f=rng()%100<unsigned(percent);
  idBounds bounds;
  auto sample=[&](auto fn){double t=emscripten_get_now();for(int i=0;i<3000000/faces;i++){
   checksum+=fn(dst.data(),bounds,verts.data(),src.data(),facing.data(),count);}return emscripten_get_now()-t;};
  sample(reference);sample(candidate);std::vector<double> a,b;
  for(int run=0;run<9;run++){if(run%2){b.push_back(sample(candidate));a.push_back(sample(reference));}
   else{a.push_back(sample(reference));b.push_back(sample(candidate));}}
  std::sort(a.begin(),a.end());std::sort(b.begin(),b.end());
  std::printf("BENCH faces=%d kept=%d%% reference=%.3fms fused=%.3fms ratio=%.3f\n",faces,percent,a[4],b[4],b[4]/a[4]);
 }
 std::printf("checksum=%u\n",checksum);
}
'''
Path(sys.argv[1]).write_text(prefix + clear + '\n' + add + '\n' + unroll + '\n' + minmax + '\n' + reference + helper + main)
