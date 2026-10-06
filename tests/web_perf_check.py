"""Extract the real browser profiler and verify timing, nesting and sample accounting."""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
source = (root / 'neo/renderer/tr_gles.cpp').read_text()


def function(name):
    start = re.search(r'^(?:extern "C" )?(?:void|double) ' + name + r'\(', source, re.M).start()
    depth = 0
    for end in range(source.index('{', start), len(source)):
        depth += (source[end] == '{') - (source[end] == '}')
        if not depth:
            return source[start:end + 1]
    raise ValueError(name)


state = source[source.index('struct webPerf_t {'):source.index('extern "C" void R_GLES_PerfCallback')]
prefix = r'''
#include <algorithm>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <cstdarg>
#include <string>
#include "HEADER"
double clockMs=1000;
int clockReads=0,checks=0;
double emscripten_get_now(){++clockReads;return clockMs;}
void check(bool ok,const char *label){if(!ok){std::fprintf(stderr,"FAIL %s\n",label);std::exit(1);}++checks;}
struct Common {std::string text;void Printf(const char *format,...){
 char buffer[4096];va_list args;va_start(args,format);vsnprintf(buffer,sizeof(buffer),format,args);va_end(args);text+=buffer;
}} logger,*common=&logger;
'''.replace('HEADER', (root / 'neo/renderer/WebRenderTiming.h').as_posix())
main = r'''
void earlyReturn(){webRenderPhase_t timer(19);clockMs+=3;}
void begin(int frames){g_webPerf=webPerf_t();g_webPerf.remaining=frames;g_webPerf.warmup=true;logger.text.clear();}
int main(){
 {webRenderPhase_t idle(16);idle.Next(17);earlyReturn();}
 R_GLES_PerfCallback(true);R_GLES_PerfAsync(1);R_GLES_PerfPhase(19,1);
 R_GLES_PerfLightTriangles(8,3,true);
 check(clockReads==0,"idle scopes never read browser clock");
 check(g_webPerf.phaseCalls[19]==0 && g_webPerf.callbacks==0,"idle counters stay empty");
 check(g_webPerf.lightTriangleBuilds==0 && g_webPerf.lightInputFaces==0,"idle geometry counters stay empty");
 begin(2);
 {webRenderPhase_t warmup(16);clockMs+=8;}
 R_GLES_PerfCallback(true);R_GLES_PerfAsync(4);g_webPerf.draws=99;
 R_GLES_PerfLightTriangles(8,3,true);
 R_GLES_PerfFrame(20);
 check(g_webPerf.remaining==2 && !g_webPerf.warmup && g_webPerf.samples==0,"warmup is not a sample");
 check(g_webPerf.phases[16]==0 && g_webPerf.phaseCalls[16]==0,"warmup phase time and counts discarded");
 check(g_webPerf.callbacks==0 && g_webPerf.asyncMs==0 && g_webPerf.draws==0,"warmup work discarded");
 check(g_webPerf.lightInputFaces==0 && g_webPerf.lightKeptFaces==0 && g_webPerf.lightTriangleBuilds==0 && g_webPerf.fusedBoundBuilds==0,"warmup geometry discarded");
 int callsBefore=clockReads;
 {webRenderPhase_t parent(18);clockMs+=2;earlyReturn();clockMs+=5;}
 check(g_webPerf.phases[18]==10 && g_webPerf.phaseCalls[18]==1,"parent includes child time once");
 check(g_webPerf.phases[19]==3 && g_webPerf.phaseCalls[19]==1,"early return records nested scope");
 check(clockReads-callsBefore==4,"nested scopes each read start and end");
 {webRenderPhase_t chained(16);clockMs+=2;chained.Next(17);clockMs+=4;}
 check(g_webPerf.phases[16]==2 && g_webPerf.phases[17]==4,"phase transition records distinct intervals");
 check(g_webPerf.phaseCalls[16]==1 && g_webPerf.phaseCalls[17]==1,"phase transition counts match intervals");
 R_GLES_PerfPhase(-1,100);R_GLES_PerfPhase(WEB_RENDER_PHASE_COUNT,100);
 check(g_webPerf.phases[19]==3,"invalid phase bounds ignored");
 R_GLES_PerfCallback(false);R_GLES_PerfCallback(true);R_GLES_PerfAsync(1);
 R_GLES_PerfLightTriangles(8,3,true);
 R_GLES_PerfFrame(12);
 check(g_webPerf.remaining==1 && logger.text.empty(),"report waits for complete sample");
 R_GLES_PerfCallback(true);R_GLES_PerfAsync(2);clockMs=g_webPerf.started+100;
 R_GLES_PerfLightTriangles(12,7,false);
 R_GLES_PerfFrame(20);
 check(g_webPerf.remaining==0 && g_webPerf.samples==2,"exact sampled-frame count");
 check(logger.text.find("20.0 fps, CPU mean 16.00 ms, p95 20.00 ms")!=std::string::npos,"wall time and CPU summary");
 check(logger.text.find("30.0 animation callbacks/s, 1 cap skips (33.3%)")!=std::string::npos,"callbacks and skip denominator");
 check(logger.text.find("model detail 1.00 ms resolve/animate (0.5 calls), 2.00 ms ambient surfaces (0.5 calls), 5.00 ms active interactions (0.5 calls)")!=std::string::npos,"detail report averages by frames");
 check(logger.text.find("interaction builds 1.50 ms (0.5 calls)")!=std::string::npos,"nested build average");
 check(logger.text.find("CPU breakdown 1.50 ms async input/audio, 14.50 ms game/render")!=std::string::npos,"async CPU accounting");
 check(logger.text.find("light triangles 10.0 input / 5.0 kept per frame; 1.0 builds (0.5 fused bounds)")!=std::string::npos,"geometry frame denominators and fused subset");
 auto report=logger.text;callsBefore=clockReads;
 {webRenderPhase_t stopped(19);clockMs+=1;}
 R_GLES_PerfCallback(false);R_GLES_PerfFrame(30);
 R_GLES_PerfLightTriangles(12,7,true);
 check(clockReads==callsBefore && logger.text==report,"completed sample stays idle");
 check(g_webPerf.lightInputFaces==20 && g_webPerf.lightTriangleBuilds==2,"completed sample ignores geometry");
 begin(1);R_GLES_PerfFrame(1);clockMs+=20;R_GLES_PerfFrame(7);
 check(g_webPerf.phaseCalls[19]==0 && g_webPerf.samples==1,"replacement sample resets state");
 check(logger.text.find("0.0 animation callbacks/s, 0 cap skips (0.0%)")!=std::string::npos,"zero callback denominator safe");
 std::printf("PASS: %d browser profiler accounting checks\n",checks);
}
'''
names = ('R_GLES_PerfCallback', 'R_GLES_PerfAsync', 'R_GLES_PerfPhase',
         'R_GLES_PerfTimestamp', 'R_GLES_PerfLightTriangles', 'R_GLES_PerfFrame')
Path(sys.argv[1]).write_text(prefix + state + '\n'.join(function(name) for name in names) + main)
