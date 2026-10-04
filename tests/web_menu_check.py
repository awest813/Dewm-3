"""Compile the actual menu policy, preset and command code without licensed assets."""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]


def block(source, start):
    depth = 0
    opened = False
    for i in range(start, len(source)):
        if source[i] == '{':
            depth += 1
            opened = True
        elif source[i] == '}':
            depth -= 1
            if opened and depth == 0:
                return source[start:i + 1]
    raise ValueError('Unterminated block')


def function(path, name):
    source = (root / path).read_text()
    source = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
    match = re.search(r'[^\n]*\b' + re.escape(name) + r'\([^;]*?\)\s*\{', source)
    if not match:
        raise ValueError(name)
    return block(source, match.start())


menu = (root / 'neo/framework/Session_menu.cpp').read_text()
menu = menu[menu.index('void idSessionLocal::HandleMainMenuCommands('):]
branches = '\n'.join(block(menu, re.search(r'if\s*\(\s*!idStr::Icmp\s*\(\s*cmd,\s*"' + command + r'"\s*\)\s*\)', menu).start())
                     for command in ['sound', 'video', 'exec'])
harness = r'''
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <map>
#include <cctype>
#define __EMSCRIPTEN__ 1
#define CVAR_ARCHIVE 1
#define CVAR_USERINFO 2
#define CMD_EXEC_NOW 0
#define WIN_CANFOCUS 1
#define WIN_MODAL 2
#define ON_ACTION 0
#define ON_ACTIONRELEASE 1
#define LEXFL_NOSTRINGCONCAT 1
int checks=0;
void check(bool ok,const char *label){if(!ok){std::fprintf(stderr,"FAIL %s\n",label);std::exit(1);}++checks;}
struct idStr : std::string {
 using std::string::string; using std::string::operator=;
 operator const char*()const{return c_str();}
 int Length()const{return size();}
 static int Icmp(const char*a,const char*b){while(*a&&*b){int d=std::tolower(*a++)-std::tolower(*b++);if(d)return d;}return *a-*b;}
 int Icmp(const char*b)const{return Icmp(c_str(),b);}
};
struct idCmdArgs {std::vector<const char*> words; int Argc()const{return words.size();}const char*Argv(int i)const{return words.at(i);}};
struct Cvars {
 std::map<std::string,std::string> values;
 void SetCVarInteger(const char*n,int v,int=0){values[n]=std::to_string(v);}
 void SetCVarBool(const char*n,bool v,int=0){SetCVarInteger(n,v);}
 void SetCVarString(const char*n,const char*v,int=0){values[n]=v;}
 int GetCVarInteger(const char*n){return std::atoi(values[n].c_str());}
 const char*GetCVarString(const char*n){return values[n].c_str();}
 float GetCVarFloat(const char*n){return std::atof(values[n].c_str());}
 void SetCVarFloat(const char*n,float v){values[n]=std::to_string(v);}
 void SetModifiedFlags(int){}
} cvars;
Cvars *cvarSystem=&cvars;
struct Spec {int value=1;int GetInteger(){return value;}void SetInteger(int v){value=v;}} com_machineSpec;
std::vector<std::string> trace;
int com_frameTime=0;
struct Gui {void StateChanged(int){}void HandleNamedEvent(const char*v){trace.push_back(v);}void SetStateInt(const char*n,int v){trace.push_back(std::string(n)+"="+std::to_string(v));}} gui;
Gui *guiActive=&gui;
void(*executeCommand)(const char*)=nullptr;
struct Commands {void BufferCommandText(int,const char*v){trace.push_back(v);if(executeCommand)executeCommand(v);}} commands;
Commands *cmdSystem=&commands;
struct WinVar {std::string value;bool update=true; bool NeedsUpdate(){return update;}void Set(const char*v){value=v;}const char*c_str(){return value.c_str();}};
const char*va(const char*,int v){static std::string s;s=std::to_string(v);return s.c_str();}
struct Cvar {std::string value;const char*GetString(){return value.c_str();}void SetString(const char*v){value=v;}};
struct idChoiceWindow {bool webReadOnly=false,liveUpdate=true;Cvar*cvar=nullptr;WinVar cvarStr,guiStr;int currentChoice=0;void UpdateVars(bool read,bool force=false);};
template<class T>struct idList:std::vector<T>{using std::vector<T>::vector;int Num(){return this->size();}void Append(T v){this->push_back(v);}int FindIndex(T v){for(int i=0;i<Num();++i)if((*this)[i]==v)return i;return -1;}};
struct idParser {std::string text;idParser(int flags=0){check(flags&LEXFL_NOSTRINGCONCAT,"Apply parser keeps adjacent quoted arguments separate");}void LoadMemory(const char*s,int n,const char*){text.assign(s,n);}};
struct idGuiScriptList {std::string text;bool fixed=false;void FixupParms(void*){fixed=true;}};
struct idWindow {idList<idWindow*> children;bool visible=true,noEvents=false;float actualX=0,actualY=0;struct {float w=10,h=10;}drawRect;int flags=0;idGuiScriptList*scripts[2]={};void ParseScript(idParser*p,idGuiScriptList&s){s.text=p->text;}void AddWebApplyRelease();void CollectWebFocus(idList<idWindow*>&);idWindow*FindWebFocus(idWindow*,bool);};
enum {SE_KEY, K_MOUSE1=10, K_MOUSE2, K_RIGHTARROW, K_KP_RIGHTARROW, K_LEFTARROW, K_KP_LEFTARROW};
struct sysEvent_t{int evType,evValue,evValue2;};
struct idMath{static float ClampFloat(float lo,float hi,float v){return v<lo?lo:v>hi?hi:v;}};
struct SliderGui{const char*source="guis/mainmenu.gui";float published=0;const char*GetSourceFile(){return source;}float CursorY(){return 0;}void SetStateFloat(const char*,float v){published=v;}}sliderGui;
struct Buddy{void HandleBuddyUpdate(void*){}};
struct idSliderWindow{float value=1,stepSize=.1f,low=.5f,high=2;struct{float y=0;}thumbRect;Buddy*buddyWin=nullptr;SliderGui*gui=&sliderGui;const char*cvarStr="r_brightness";float written=0;void SetCapture(void*){}void RouteMouseCoords(float,float){}void UpdateCvar(bool){written=gui->published;}const char*HandleEvent(const sysEvent_t*,bool*);};
'''
harness += (root / 'neo/ui/WebMenuPolicy.h').read_text()
harness += function('neo/ui/ChoiceWindow.cpp', 'idChoiceWindow::UpdateVars')
harness += function('neo/ui/Window.cpp', 'idWindow::AddWebApplyRelease')
harness += function('neo/ui/Window.cpp', 'idWindow::CollectWebFocus')
harness += function('neo/ui/Window.cpp', 'idWindow::FindWebFocus')
harness += function('neo/ui/SliderWindow.cpp', 'idSliderWindow::HandleEvent')
harness += function('neo/framework/Common.cpp', 'Com_ExecMachineSpec_f')
harness += '\nvoid menuCommand(const idCmdArgs &args){int icmd=0;while(icmd<args.Argc()){idStr cmd=args.Argv(icmd++);' + branches + '}}\n'
harness += r'''
int main(){
 for(const auto&o:webMenuChoices){check(Web_MenuChoice("guis/mainmenu.gui",o.window,o.originalCvar)==&o,"stock policy match");check(!Web_MenuChoice("guis/modmenu.gui",o.window,o.originalCvar),"mod left alone");check(!Web_MenuChoice("guis/mainmenu.gui",o.window,"custom_binding"),"custom binding left alone");}
 check(!Web_MenuChoice(nullptr,"OS2Primary","r_mode"),"missing source guarded");
 check(!Web_MenuChoice("guis/mainmenu.gui",nullptr,"r_mode"),"missing control guarded");
 check(Web_MenuChoice("GUIS/MAINMENU.GUI","os2primary","R_MODE")!=nullptr,"case independent match");
 auto particles=Web_MenuChoice("guis/mainmenu.gui","ADV7Primary","r_multisamples");
 check(particles&&!particles->readOnly&&!std::strcmp(particles->replacementCvar,"r_useSoftParticles"),"MSAA replaced with supported live option");
 auto fps=Web_MenuChoice("guis/mainmenu.gui","ADV5Primary","r_swapInterval");
 check(fps&&!fps->readOnly&&!std::strcmp(fps->replacementCvar,"r_webFrameLimit"),"frame-rate row binds live browser cap");
 check(!std::strcmp(fps->choices,"30 FPS;60 FPS;Unlocked")&&!std::strcmp(fps->values,"30;60;0"),"frame-rate choices have correct values");
 Cvar real{"5"};idChoiceWindow choice;choice.cvar=&real;choice.cvarStr.value="3";choice.webReadOnly=true;
 choice.UpdateVars(false,true);check(real.value=="5","Apply cannot overwrite disabled setting");
 choice.UpdateVars(true,true);check(choice.cvarStr.value=="5","disabled setting can still read engine");
 choice.webReadOnly=false;choice.cvarStr.value="0";choice.UpdateVars(false,true);check(real.value=="0","supported setting writes");
 choice.liveUpdate=false;choice.cvarStr.value="1";choice.UpdateVars(false);check(real.value=="0","latched setting waits for Apply");
 choice.UpdateVars(false,true);check(real.value=="1","Apply writes latched setting");
 idWindow root,hidden,collapsed,disabled,panel,button;hidden.visible=false;hidden.flags=WIN_CANFOCUS;collapsed.drawRect.h=0;collapsed.flags=WIN_CANFOCUS;disabled.noEvents=true;disabled.flags=WIN_CANFOCUS;button.flags=WIN_CANFOCUS;panel.children={&button};root.children={&hidden,&collapsed,&disabled,&panel};
 check(root.FindWebFocus(nullptr,false)==&button,"Tab seeds first visible nested button");
 check(root.FindWebFocus(&collapsed,false)==&button,"stale collapsed focus recovers");
 panel.visible=false;check(!root.FindWebFocus(nullptr,false),"hidden parents suppress focus");panel.visible=true;
 idWindow second,modal,confirm;second.flags=WIN_CANFOCUS;root.children.push_back(&second);
 check(root.FindWebFocus(&button,false)==&second,"forward navigation");check(root.FindWebFocus(&second,false)==&button,"forward wrap");check(root.FindWebFocus(&button,true)==&second,"reverse wrap");check(root.FindWebFocus(nullptr,true)==&second,"reverse initial focus");
 modal.flags=WIN_MODAL;confirm.flags=WIN_CANFOCUS;modal.children={&confirm};root.children.push_back(&modal);
 check(root.FindWebFocus(&button,false)==&confirm,"open modal owns focus");modal.drawRect.h=0;check(root.FindWebFocus(&button,false)==&second,"closed modal skipped");
 second.actualX=640;check(root.FindWebFocus(&button,false)==&button,"offscreen animated button skipped");second.actualX=0;
 check(Web_MenuOnScreen(-5,0,10,10)&&!Web_MenuOnScreen(-10,0,10,10)&&!Web_MenuOnScreen(0,480,10,10),"viewport intersection boundaries");
 idGuiScriptList closeAnimation;idWindow apply;apply.scripts[ON_ACTION]=&closeAnimation;apply.AddWebApplyRelease();auto release=apply.scripts[ON_ACTIONRELEASE];
 check(apply.scripts[ON_ACTION]==&closeAnimation&&release&&release->fixed&&release->text=="{ set \"cmd\" \"video restart\" ; }","single-button confirmation retains animation and gains resolved Apply action");
 apply.AddWebApplyRelease();check(apply.scripts[ON_ACTIONRELEASE]==release,"Apply patch does not duplicate existing release handler");delete release;
 idWindow older;older.scripts[ON_ACTIONRELEASE]=&closeAnimation;older.AddWebApplyRelease();check(older.scripts[ON_ACTIONRELEASE]==&closeAnimation,"older scripted Apply handler retained");
 for(int spec=0;spec<4;++spec){com_machineSpec.value=spec;cvars.SetCVarInteger("r_mode",7);cvars.SetCVarInteger("s_maxSoundsPerShader",4);for(auto n:{"g_decals","g_projectileLights","g_doubleVision","g_muzzleFlash"})cvars.SetCVarBool(n,false);Com_ExecMachineSpec_f({{"execMachineSpec","nores"}});check(cvars.GetCVarInteger("r_mode")==7,"web preset retains render size");check(cvars.GetCVarInteger("image_downSizeBump")==(spec==0),"preset bump quality changes");check(cvars.GetCVarInteger("image_anisotropy")==(spec>=2?8:spec==1?1:0),"preset texture filtering");check(cvars.GetCVarInteger("s_maxSoundsPerShader")==4,"texture preset retains sound limits");for(auto n:{"g_decals","g_projectileLights","g_doubleVision","g_muzzleFlash"})check(cvars.GetCVarInteger(n)==0,"texture preset retains gameplay effects");}
 com_machineSpec.value=2;Com_ExecMachineSpec_f({{"execMachineSpec"}});check(cvars.GetCVarInteger("r_mode")==4,"desktop high quality resolves to mode four");check(!cvars.values.count(""),"presets never create blank cvar");
 com_machineSpec.value=1;trace.clear();menuCommand({{"video","high"}});check(com_machineSpec.value==2,"quality choice applied");check(trace.size()==2&&trace.back()=="execMachineSpec nores\n","browser quality uses nores");
 trace.clear();menuCommand({{"video","recommended"}});check(com_machineSpec.value==1&&trace.size()==2&&trace.back()=="execMachineSpec nores\n","balanced choice does not probe desktop hardware");
 trace.clear();menuCommand({{"video","restart"}});check(trace==std::vector<std::string>{"cvar write render","reloadImages reload\n","cvar read render"},"Apply reloads images with valid argument and refreshes values");
 trace.clear();cvars.SetCVarInteger("s_numberOfSpeakers",6);menuCommand({{"sound","speakers"}});check(cvars.GetCVarInteger("s_numberOfSpeakers")==2&&trace==std::vector<std::string>{"cvar read sound"},"speaker choice stays stereo without audio restart");
 trace.clear();cvars.SetCVarBool("s_useEAXReverb",true);menuCommand({{"sound","eax"}});check(!cvars.GetCVarInteger("s_useEAXReverb")&&trace==std::vector<std::string>{"cvar read sound"},"unavailable EAX stays off without blocking dialog");
 trace.clear();menuCommand({{"sound","drivar"}});check(trace.empty(),"legacy backend does not restart WebAudio");
 idSliderWindow slider;sysEvent_t right{SE_KEY,K_RIGHTARROW,1},left{SE_KEY,K_LEFTARROW,1};
 slider.value=slider.high;slider.HandleEvent(&right,nullptr);check(slider.written==slider.high,"brightness upper endpoint clamps before cvar write");
 slider.value=slider.low;slider.HandleEvent(&left,nullptr);check(slider.written==slider.low,"brightness lower endpoint clamps before cvar write");
 slider.low=1;slider.high=30;slider.stepSize=.5f;slider.value=29.75f;slider.HandleEvent(&right,nullptr);check(slider.written==30,"sensitivity fractional step clamps");
 slider.value=5;slider.HandleEvent(&left,nullptr);check(slider.written==4.5f,"ordinary sensitivity step retained");
 slider.gui->source="guis/modmenu.gui";slider.value=30;slider.HandleEvent(&right,nullptr);check(slider.written==30.5f,"custom slider behavior unchanged");
 cvars.SetCVarInteger("r_mode",-1);cvars.SetCVarInteger("r_fullscreen",0);cvars.SetCVarInteger("r_customWidth",900);cvars.SetCVarInteger("r_customHeight",600);cvars.SetCVarString("sys_lang","french");cvars.SetCVarFloat("r_brightness",1.8f);
 executeCommand=[](const char*cmd){if(!std::strcmp(cmd,"cvar_restart")){cvars.values.clear();com_machineSpec.value=-1;}else if(!std::strcmp(cmd,"exec default.cfg")){cvars.SetCVarInteger("r_mode",3);cvars.SetCVarInteger("r_fullscreen",1);cvars.SetCVarFloat("r_brightness",1);}else if(!std::strcmp(cmd,"execMachineSpec nores\n"))Com_ExecMachineSpec_f({{"execMachineSpec","nores"}});};
 trace.clear();menuCommand({{"exec","cvar_restart"}});executeCommand=nullptr;
 check(cvars.GetCVarInteger("r_mode")==-1&&cvars.GetCVarInteger("r_fullscreen")==0&&cvars.GetCVarInteger("r_customWidth")==900&&cvars.GetCVarInteger("r_customHeight")==600,"Restore Defaults retains custom browser display");
 check(com_machineSpec.value==1&&cvars.GetCVarInteger("image_anisotropy")==1,"Restore Defaults uses balanced preset");
 check(cvars.GetCVarInteger("s_numberOfSpeakers")==2&&!cvars.GetCVarInteger("s_useEAXReverb"),"Restore Defaults normalizes supported audio");
 check(!std::strcmp(cvars.GetCVarString("sys_lang"),"french")&&cvars.GetCVarFloat("r_brightness")==1,"Restore Defaults preserves language and resets brightness");
 check(trace==std::vector<std::string>{"cvar_restart","exec default.cfg","execMachineSpec nores\n","cvar read render","cvar read sound","com_machineSpec=1"},"Restore Defaults refreshes options without renderer/audio restart");
 std::printf("PASS: %d in-game menu checks\n",checks);
}
'''
Path(sys.argv[1]).write_text(harness)
