"""Exercise the engine's real tick/input functions and web graphics bridge without assets."""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
common = (root / 'neo/framework/Common.cpp').read_text()
input_source = (root / 'neo/framework/UsercmdGen.cpp').read_text()
header = (root / 'neo/framework/UsercmdGen.h').read_text()
main = (root / 'neo/sys/linux/main.cpp').read_text()
events = (root / 'neo/sys/events.cpp').read_text()


def function(source, name):
    match = re.search(r'[^\n]*\b' + re.escape(name) + r'\([^;]*?\)\s*\{', source)
    if not match:
        raise ValueError(name)
    body = re.sub(r'/\*.*?\*/|//[^\n]*', '', source[match.start():], flags=re.S)
    depth = 0
    for i, char in enumerate(body):
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if not depth:
                return body[:i + 1]
    raise ValueError('Unterminated ' + name)


# Guard the browser integration, not just the scheduler in isolation.
frame = function(common, 'idCommonLocal::Frame')
assert frame.index('eventLoop->RunEventLoop()') < frame.index('Async()') < frame.index('session->Frame()')
assert 'common->Async()' not in function(main, 'WebMainLoop')
web_loop = function(main, 'WebMainLoop')
assert web_loop.index('pacing.ShouldRender') < web_loop.index('common->Frame()')
assert '#if defined(__EMSCRIPTEN__) && !defined(__EMSCRIPTEN_PTHREADS__)' in frame
enum = re.search(r'typedef enum \{.*?\} usercmdButton_t;', input_source, re.S)[0]
constants = '\n'.join(re.findall(r'const int (?:USERCMD_HZ|USERCMD_MSEC|BUTTON_\w+|UCF_IMPULSE_SEQUENCE)\s*=.*?;', header))
move_speed = re.search(r'const int KEY_MOVESPEED\s*=.*?;', input_source)[0]
graphics_table = main[main.index('struct webGraphicsOption_t'):main.index('extern "C" EMSCRIPTEN_KEEPALIVE double Web_GetGraphicsOption')]

harness = r'''
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <limits>
#include <string>
#include <map>
#define EMSCRIPTEN_KEEPALIVE
#define BIT(x) (1 << (x))
int checks=0;
void check(bool ok,const char *label){if(!ok){std::fprintf(stderr,"FAIL %s\n",label);std::exit(1);}++checks;}
struct CVar { double value; bool GetBool(){return value!=0;} float GetFloat(){return value;} int GetInteger(){return value;} };
CVar com_preciseTic{1},com_timescale{1},in_alwaysRun{0},in_freeLook{1};
int clockMsec=1000,lastTicMsec=0,ticks=0;
int Sys_Milliseconds(){return clockMsec;}
class idCommonLocal { public: bool initialized=true; bool IsInitialized(){return initialized;} void Async(); void SingleAsyncTic(){++ticks;} } commonLocal;
idCommonLocal *common=&commonLocal;
struct Cvars {
 std::map<std::string,double> values;
 double GetCVarFloat(const char *name){return values[name];}
 void SetCVarFloat(const char *name,double value){values[name]=value;}
} cvars;
Cvars *cvarSystem=&cvars;
struct { bool isInitialized=true, anisotropicAvailable=true; float maxTextureAnisotropy=16; } glConfig;
namespace idMath { signed char ClampChar(int value){return value<-128?-128:value>127?127:value;} }
'''
harness += enum + '\n' + constants + '\n' + move_speed + '\n'
harness += r'''
struct Cmd { int buttons=0,flags=0,impulse=0; signed char forwardmove=0,rightmove=0,upmove=0; };
struct Toggle { bool on=false; };
struct idKeyInput { static int bindings[256]; static int GetUsercmdAction(int key){return bindings[key];} static void ClearStates(); };
int idKeyInput::bindings[256]={};
class idUsercmdGenLocal { public:
 Cmd cmd; int buttonState[UB_MAX_BUTTONS]={}; bool keyState[256]={}; float joystickAxis[8]={};
 bool inhibitCommands=false; int mouseDx=0,mouseDy=0,mouseButton=0; bool mouseDown=false;
 Toggle toggled_crouch,toggled_run,toggled_zoom;
 int ButtonState(int action){return buttonState[action]>0;} bool AlwaysRunAllowed(){return true;}
 bool Inhibited(){return inhibitCommands;}
 void Key(int keyNum,bool down); void KeyMove(); void CmdButtons(); void Clear();
} input;
int queueClears=0;
void Sys_ClearEvents(){++queueClears;}
void idKeyInput::ClearStates(){input.Clear();}
'''
for name in ['Key', 'KeyMove', 'CmdButtons', 'Clear']:
    harness += function(input_source, 'idUsercmdGenLocal::' + name) + '\n'
harness += function(common, 'idCommonLocal::Async') + '\n'
harness += graphics_table
harness += (root / 'neo/sys/WebFramePacing.h').read_text()
for name in ['Web_GetGraphicsOption', 'Web_SetGraphicsOption']:
    harness += function(main, name) + '\n'
harness += function(events, 'Web_ReleaseInput') + '\n'
harness += r'''
int main(){
 for(int refresh: {30,60,90,120,144,240})for(int limit: {0,30,60}){
  webFramePacing_t pacing;int rendered=0;lastTicMsec=0;ticks=0;
  for(int f=0;f<=refresh*10;++f){
   double now=1000.0+f*1000.0/refresh;
   if(pacing.ShouldRender(now,limit)){++rendered;clockMsec=(int)now;common->Async();}
  }
  int expected=(limit&&limit<refresh?limit:refresh)*10+1;
  check(std::abs(rendered-expected)<=1,"frame limits across display refresh rates");
  check(ticks>=625&&ticks<=626,"fixed game ticks retained under render caps");
 }
 webFramePacing_t pacing;
 check(pacing.ShouldRender(0,30)&&!pacing.ShouldRender(10,30),"30 FPS skips early callback");
 check(pacing.ShouldRender(10,60),"switching cap takes effect immediately");
 check(pacing.ShouldRender(11,0)&&pacing.ShouldRender(12,0),"unlocked renders every callback");
 check(pacing.ShouldRender(1000,30)&&!pacing.ShouldRender(1001,30),"long gaps do not cause render bursts");
 webFramePacing_t jitter;
 for(double now: {0.0,16.3,33.1,49.8,66.4,83.0})check(jitter.ShouldRender(now,60),"60 Hz jitter does not halve rate");
 check(!Web_ValidFrameLimit(45)&&Web_ValidFrameLimit(0)&&Web_ValidFrameLimit(30)&&Web_ValidFrameLimit(60),"only supported caps accepted");
 check(USERCMD_MSEC==16,"native integer tick interval retained");
 for(int fps: {30,60,90,144}){
  lastTicMsec=0;ticks=0;
  for(int f=0;f<=fps*2;++f){clockMsec=1000+f*1000/fps;common->Async();}
  check(ticks==126,"same fixed tick count at different render rates");
 }
 lastTicMsec=1000;ticks=0;clockMsec=1015;common->Async();check(ticks==0,"no early tick");
 clockMsec=1016;common->Async();check(ticks==1,"tick boundary");
 clockMsec=1032;common->Async();check(ticks==2,"next tick");
 clockMsec=50000;ticks=0;common->Async();check(ticks==10,"long hitch bounded to native ten ticks");
 com_timescale.value=2;lastTicMsec=1000;ticks=0;clockMsec=1032;common->Async();check(ticks==4,"native timescale behavior");
 com_timescale.value=1;
 idKeyInput::bindings['w']=UB_FORWARD;idKeyInput::bindings['s']=UB_BACK;
 idKeyInput::bindings['d']=UB_MOVERIGHT;idKeyInput::bindings[' ']=UB_UP;
 idKeyInput::bindings['f']=UB_ATTACK;idKeyInput::bindings['g']=UB_ATTACK;
 idKeyInput::bindings['2']=UB_IMPULSE2;idKeyInput::bindings['r']=UB_IMPULSE13;
 input.Key('w',true);input.Key('d',true);input.KeyMove();
 check(input.cmd.forwardmove==127&&input.cmd.rightmove==127,"native forward/strafe usercmd");
 input.cmd={};input.Key('s',true);input.KeyMove();check(input.cmd.forwardmove==0,"opposed movement cancels");
 input.cmd={};input.Key(' ',true);input.KeyMove();check(input.cmd.upmove==127,"native jump input");
 input.Key('f',true);input.CmdButtons();check(input.cmd.buttons&BUTTON_ATTACK,"attack input");
 input.Key('f',true);input.Key('f',false);input.CmdButtons();check(!(input.cmd.buttons&BUTTON_ATTACK),"repeat keydown does not latch attack");
 input.Key('f',true);input.Key('g',true);input.Key('f',false);input.CmdButtons();check(input.cmd.buttons&BUTTON_ATTACK,"second attack binding remains held");
 input.Key('g',false);input.CmdButtons();check(!(input.cmd.buttons&BUTTON_ATTACK),"all attack bindings released");
 input.Key('2',true);check(input.cmd.impulse==2&&input.cmd.flags==UCF_IMPULSE_SEQUENCE,"weapon selection impulse");
 input.Key('2',true);check(input.cmd.flags==UCF_IMPULSE_SEQUENCE,"repeat does not repeat weapon impulse");
 input.Key('r',true);check(input.cmd.impulse==13&&input.cmd.flags==0,"native reload impulse sequence");
 input.inhibitCommands=true;input.Key('2',false);input.Key('2',true);check(input.cmd.impulse==13,"menu inhibits weapon switch");
 Web_ReleaseInput();input.cmd={};input.KeyMove();input.CmdButtons();
 check(queueClears==1&&input.cmd.forwardmove==0&&input.cmd.rightmove==0&&!(input.cmd.buttons&BUTTON_ATTACK),"focus loss clears movement and attack");
 check(!input.mouseDown&&input.mouseDx==0&&input.mouseDy==0,"focus loss clears mouse state");
 common->initialized=false;Web_ReleaseInput();check(queueClears==1,"prestart focus loss is safe");
 check(Web_GetGraphicsOption(0)==-1&&!Web_SetGraphicsOption(0,1),"prestart graphics guarded");
 common->initialized=true;
 for(int i=0;i<6;++i){check(Web_SetGraphicsOption(i,1)==1,"supported option applied");check(Web_GetGraphicsOption(i)==1,"engine readback");}
 check(!Web_SetGraphicsOption(-1,1)&&!Web_SetGraphicsOption(8,1),"unknown graphics index rejected");
 check(Web_GetGraphicsOption(-1)==-1&&Web_GetGraphicsOption(8)==-1,"unknown read rejected");
 check(Web_GetTextureFilteringLimit()==16,"filtering reports supported GPU limit");
 for(double level:{1.,2.,3.5,4.,8.,16.})check(Web_SetGraphicsOption(7,level)&&Web_GetGraphicsOption(7)==level,"filtering writes preserve valid native intermediate values");
 glConfig.maxTextureAnisotropy=4;
 check(Web_GetTextureFilteringLimit()==4&&!Web_SetGraphicsOption(7,8),"filtering rejects levels above GPU limit");
 glConfig.anisotropicAvailable=false;
 check(Web_GetTextureFilteringLimit()==1&&Web_SetGraphicsOption(7,1)&&!Web_SetGraphicsOption(7,2),"unsupported extension retains standard filtering");
 glConfig.anisotropicAvailable=true;glConfig.isInitialized=false;
 check(Web_GetTextureFilteringLimit()==1,"unavailable context retains standard filtering");
 glConfig.isInitialized=true;glConfig.maxTextureAnisotropy=16;
 check(!Web_SetGraphicsOption(7,0)&&!Web_SetGraphicsOption(7,17),"filtering range rejects invalid levels");
 for(int limit:{0,30,60})check(Web_SetGraphicsOption(6,limit)&&Web_GetGraphicsOption(6)==limit,"FPS choice writes and reads");
 check(!Web_SetGraphicsOption(6,45)&&!Web_SetGraphicsOption(6,30.5),"invalid FPS and fractions rejected");
 check(!Web_SetGraphicsOption(0,0.5),"boolean must be zero or one");
 check(!Web_SetGraphicsOption(4,0.49)&&!Web_SetGraphicsOption(4,3.01),"gamma bounds");
 check(!Web_SetGraphicsOption(5,0.49)&&!Web_SetGraphicsOption(5,2.01),"brightness bounds");
 // Supply runtime IEEE bits like a JavaScript caller; finite-math compilers
 // may treat compile-time NaN/infinity arithmetic as undefined behavior.
 volatile uint64_t invalidBits=0x7ff8000000000000ULL;
 uint64_t raw=invalidBits;double invalid;std::memcpy(&invalid,&raw,sizeof(raw));
 check(!Web_SetGraphicsOption(4,invalid),"runtime NaN rejected with finite-math build");
 invalidBits=0x7ff0000000000000ULL;raw=invalidBits;std::memcpy(&invalid,&raw,sizeof(raw));
 check(!Web_SetGraphicsOption(4,invalid),"runtime infinity rejected");
 check(Web_SetGraphicsOption(4,0.5)&&Web_SetGraphicsOption(4,3)&&Web_SetGraphicsOption(5,2),"valid boundaries accepted");
 check(cvars.values.size()==8,"graphics bridge cannot change gameplay cvars");
 std::printf("PASS: %d gameplay timing/input/graphics checks\n",checks);
}
'''
Path(sys.argv[1]).write_text(harness)
