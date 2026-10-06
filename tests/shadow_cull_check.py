"""Generate a Wasm culling parity harness from the actual web helper and generic SIMD.

python tests/shadow_cull_check.py build-web/shadow-cull-check.cpp
em++ build-web/shadow-cull-check.cpp -O3 -flto -fno-math-errno -fno-trapping-math -ffinite-math-only -fno-strict-aliasing -ffp-contract=off -sENVIRONMENT=node -o build-web/shadow-cull-check.js
node build-web/shadow-cull-check.js

The exact bit comparisons test geometry decisions; the alternating microbenchmark
measures only this kernel and is not an end-to-end frame-rate result.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
simd = (root / 'neo/idlib/math/Simd_Generic.cpp').read_text()
vec = (root / 'neo/idlib/math/Vector.h').read_text()
header = (root / 'neo/renderer/Interaction.h').read_text()
interaction = (root / 'neo/renderer/Interaction.cpp').read_text()

def body(signature, source=simd):
    start = source.index(signature)
    tail = source[start:]
    depth = 0
    for i, c in enumerate(tail):
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: return tail[:i+1]
    raise ValueError(signature)

dot = body('void VPCALL idSIMD_Generic::Dot( float *dst, const idPlane &constant, const idDrawVert *src, const int count )')
cmp = body('void VPCALL idSIMD_Generic::CmpLT( byte *dst, const byte bitNum, const float *src0, const float constant, const int count )')
vecdot = re.search(r'ID_INLINE float idVec3::operator\*\( const idVec3 &a \) const \{([^}]+)\}', vec).group(1)
epsilon = re.search(r'#define\s+LIGHT_CLIP_EPSILON\s+(\S+)', header).group(1)
unroll = '\n'.join(re.findall(r'^#define UNROLL[14]\(Y\).*$', simd, re.M))
helper = body('static void R_CalcInteractionCullBitsWeb(', interaction)
if not re.search(r'R_CalcInteractionCullBitsWeb\( cullInfo\.cullBits, cullInfo\.localClipPlanes,\s*tri->verts, tri->numVerts, frontBits \)', interaction):
    raise ValueError('Renderer does not call the tested web helper')
prefix = r'''
#include <cstdio>
#include <cstring>
#include <cmath>
#include <vector>
#include <algorithm>
#include <emscripten.h>
using byte = unsigned char;
#define VPCALL
struct idVec3 { float x,y,z; float operator*(const idVec3 &a) const { VECDOT } };
struct idPlane { idVec3 n; float d; const idVec3 &Normal() const {return n;} float operator[](int) const {return d;} };
struct idDrawVert { idVec3 xyz; float padding[12]; };
static_assert(sizeof(idDrawVert)==60,"real vertex stride");
class idSIMD_Generic { public:
__attribute__((noinline)) void Dot(float*,const idPlane&,const idDrawVert*,int);
__attribute__((noinline)) void CmpLT(byte*,byte,const float*,float,int);
};
'''.replace('VECDOT', vecdot)
code = r'''
const float epsilon = EPSILON;
__attribute__((noinline)) void reference(byte* bits, const idPlane* planes, const idDrawVert* verts, int count, int frontBits) {
  float* distances = (float*)__builtin_alloca(count * sizeof(float));
  std::memset(bits,0,count);
  idSIMD_Generic processor;
  for(int p=0;p<6;p++) {
    if(frontBits & (1<<p)) continue;
    processor.Dot(distances,planes[p],verts,count);
    processor.CmpLT(bits,p,distances,epsilon,count);
  }
}
WEB_HELPER
__attribute__((noinline)) void candidate(byte* bits, const idPlane* planes, const idDrawVert* verts, int count, int frontBits) {
  std::memset(bits,0,count);
  R_CalcInteractionCullBitsWeb(bits,planes,verts,count,frontBits);
}
unsigned seed=1;
float randomFloat() {seed=seed*1664525u+1013904223u;return (int(seed>>8)-8388608)*0.000123f;}
volatile unsigned checksum=0;
int main() {
  size_t checked=0;
  for(int count: {0,1,2,3,4,5,16,63,64,65,255,256,257,1000,4096}) {
    std::vector<idDrawVert> verts(count);
    for(auto &v:verts) v.xyz={randomFloat(),randomFloat(),randomFloat()};
    idPlane planes[6];
    for(auto &p:planes) p={{randomFloat(),randomFloat(),randomFloat()},randomFloat()};
    for(int scenario=0;scenario<3;scenario++) {
      if(scenario==1) {for(auto &p:planes)p={{1,0,0},0};for(int i=0;i<count;i++)verts[i].xyz={i%3==0?epsilon:(i%3==1?std::nextafter(epsilon,0.f):std::nextafter(epsilon,1.f)),0,0};}
      if(scenario==2) {for(auto &p:planes)p={{-1,0,0},0};for(int i=0;i<count;i++)verts[i].xyz={i%2?0.f:-0.f,0,0};}
      for(int mask=0;mask<64;mask++) {
        std::vector<byte> a(count+2,123), b(count+2,123);
        reference(a.data()+1,planes,verts.data(),count,mask);
        candidate(b.data()+1,planes,verts.data(),count,mask);
        if(a!=b) {std::printf("FAIL count=%d mask=%d scenario=%d\n",count,mask,scenario);return 1;}
        checked+=count;
      }
    }
  }
  std::printf("PASS %zu exact cull-bit comparisons, all 64 plane masks, edge counts, epsilon neighbors, signed zero, buffer guards\n",checked);
  for(int count: {32,256,2048}) {
    std::vector<idDrawVert> verts(count);
    for(auto &v:verts) v.xyz={randomFloat(),randomFloat(),randomFloat()};
    idPlane planes[6];for(auto &p:planes)p={{randomFloat(),randomFloat(),randomFloat()},randomFloat()};
    std::vector<byte> bits(count);
    auto sample=[&](auto fn) {double start=emscripten_get_now();for(int i=0;i<3000000/count;i++){fn(bits.data(),planes,verts.data(),count,i%63);checksum+=bits[i%count];}return emscripten_get_now()-start;};
    sample(reference);sample(candidate);
    std::vector<double> a,b;
    for(int run=0;run<9;run++) {if(run%2){b.push_back(sample(candidate));a.push_back(sample(reference));}else{a.push_back(sample(reference));b.push_back(sample(candidate));}}
    std::sort(a.begin(),a.end());std::sort(b.begin(),b.end());
    std::printf("BENCH count=%d reference=%.3fms fused=%.3fms ratio=%.3f\n",count,a[4],b[4],b[4]/a[4]);
  }
  std::printf("checksum=%u\n",checksum);
}
'''.replace('EPSILON',epsilon).replace('WEB_HELPER',helper)
Path(sys.argv[1]).write_text(prefix+'\n#define LIGHT_CLIP_EPSILON '+epsilon+'\n'+unroll+'\n'+dot+'\n'+cmp+'\n'+code)
print('Wrote ' + sys.argv[1])
