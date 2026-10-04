"""Extract the actual drag-input bridge into an asset-free C++ regression harness."""
from pathlib import Path
import re
import sys

source = (Path(__file__).resolve().parents[1] / 'neo/sys/events.cpp').read_text()

def function(name, prefix='extern "C" EMSCRIPTEN_KEEPALIVE void '):
    start = re.search(prefix + name + r'\([^\n]*\)\s*\{', source).start()
    body = source[start:]
    body = re.sub(r'/\*.*?\*/|//[^\n]*', '', body, flags=re.S)
    depth = 0
    for i, char in enumerate(body):
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if not depth:
                return body[:i+1]
    raise ValueError('Unterminated function: ' + name)

harness = r'''
#include <cstdio>
#include <cstdlib>
#define EMSCRIPTEN_KEEPALIVE
constexpr int SDL_MOUSEMOTION=1;
struct SDL_Window {} window;
struct SDL_Event { int type; struct { int windowID,which,xrel,yrel; } motion; } lastEvent;
bool focused=true, in_relativeMouseMode=true;
bool captured=false;
bool GLimp_WebMouseCaptured(){return captured;}
double webDragRemainderX=0, webDragRemainderY=0;
int calls=0, checks=0;
SDL_Window *SDL_GetMouseFocus(){return focused?&window:nullptr;}
void SDL_GetWindowSize(SDL_Window*,int *w,int *h){*w=800;*h=600;}
int SDL_GetWindowID(SDL_Window*){return 42;}
int SDL_PushEvent(SDL_Event *event){lastEvent=*event;++calls;return 1;}
void check(bool ok,const char *label){if(!ok){std::fprintf(stderr,"FAIL %s\n",label);std::exit(1);}++checks;}
'''
harness += function('Web_SetDragLook') + '\n' + function('Web_DragMouse')
harness += '\n' + function('Web_UseMouseMotion', 'static bool ')
harness += r'''
int main(){
    check(!Web_UseMouseMotion(0),"unlocked synthetic SDL motion cannot turn the camera");
    check(Web_UseMouseMotion(0xD003),"drag bridge motion reaches gameplay without capture");
    captured=true;
    check(Web_UseMouseMotion(0),"confirmed capture allows normal SDL motion");
    captured=false;in_relativeMouseMode=false;
    check(Web_UseMouseMotion(0),"menus retain ordinary absolute motion");
    check(!Web_UseMouseMotion(0xD003),"menus reject queued fallback motion");
    in_relativeMouseMode=true;
    Web_SetDragLook(1);
    Web_DragMouse(7,-3,800,600);
    check(calls==1 && lastEvent.motion.xrel==7 && lastEvent.motion.yrel==-3,"first drag delta stays small");
    check(lastEvent.motion.which==0xD003 && lastEvent.motion.windowID==42,"motion is marked and routed to the game window");
    Web_DragMouse(1,-1,400,300);
    check(lastEvent.motion.xrel==2 && lastEvent.motion.yrel==-2,"CSS scaling matches virtual window size");
    Web_SetDragLook(1);
    int prior=calls;
    Web_DragMouse(0.5,-0.5,800,600);
    check(calls==prior,"fractional motion is retained instead of emitting zero events");
    Web_DragMouse(0.5,-0.5,800,600);
    check(calls==prior+1 && lastEvent.motion.xrel==1 && lastEvent.motion.yrel==-1,"fractional deltas accumulate in both directions");
    Web_DragMouse(0.5,0.5,800,600);
    Web_SetDragLook(0);
    Web_SetDragLook(1);
    prior=calls;
    Web_DragMouse(0.5,0.5,800,600);
    check(calls==prior,"new drag resets residual movement from the previous drag");
    Web_DragMouse(50,50,0,600);
    Web_DragMouse(50,50,800,-1);
    check(calls==prior,"invalid canvas dimensions do not queue motion");
    in_relativeMouseMode=false;
    Web_DragMouse(50,50,800,600);
    check(calls==prior,"menus reject queued drag motion");
    in_relativeMouseMode=true;focused=false;
    Web_DragMouse(50,50,800,600);
    check(calls==prior,"missing mouse focus rejects drag motion");
    std::printf("%d web drag-input checks passed\n",checks);
}
'''
output = Path(sys.argv[1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(harness)
print('Wrote ' + str(output))
