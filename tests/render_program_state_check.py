"""Generate a C++ regression harness from the renderer's actual state functions.

python tests/render_program_state_check.py build-web/render-state-check.cpp
em++ build-web/render-state-check.cpp -sENVIRONMENT=node -o build-web/render-state-check.js
node build-web/render-state-check.js

GL bindings/uniform uploads are stubbed; program selection and scope handling
are extracted from the renderer. Retail game data and a GPU are unnecessary.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
source = (root / 'neo/renderer/tr_gles.cpp').read_text(encoding='utf-8')
header = (root / 'neo/renderer/tr_local.h').read_text(encoding='utf-8')


def function(name, src=source, return_type='void'):
    match = re.search(r'^(?:static )?' + return_type + r' (?:APIENTRY )?' + name + r'\([^\n]*\)\s*\{', src, re.M)
    if not match:
        raise ValueError('Missing renderer function: ' + name)
    # These functions contain no braced literals. Strip comments before
    # counting so an explanatory comment cannot change extraction boundaries.
    tail = src[match.start():]
    tail = re.sub(r'/\*.*?\*/|//[^\n]*', '', tail, flags=re.S)
    depth = 0
    for index, char in enumerate(tail):
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return tail[:index + 1]
    raise ValueError('Unterminated renderer function: ' + name)


program_enum = re.search(r'typedef enum \{\s*PROG_INVALID,.*?\} program_t;', header, re.S).group()
harness = r'''
#include <cstdio>
#include <cstdlib>
#include <cstring>
#define APIENTRY
using GLenum = unsigned int;
using GLuint = unsigned int;
using GLint = int;
using GLsizei = int;
using GLvoid = void;
using GLfloat = float;
using GLboolean = unsigned char;
using EMSCRIPTEN_WEBGL_CONTEXT_HANDLE = int;
using byte = unsigned char;
constexpr GLenum GL_ELEMENT_ARRAY_BUFFER=0x8893, GL_ARRAY_BUFFER=0x8892;
constexpr GLenum GL_UNSIGNED_INT=0x1405, GL_UNSIGNED_SHORT=0x1403, GL_STREAM_DRAW=0x88e0, GL_NO_ERROR=0;
constexpr GLenum GL_VERTEX_PROGRAM_ARB=0x8620, GL_FRAGMENT_PROGRAM_ARB=0x8804;
constexpr GLenum GL_TEXTURE_2D=0x0de1, GL_TEXTURE_CUBE_MAP=0x8513;
constexpr GLenum GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT=0x84ff;
struct { bool anisotropicAvailable=false; float maxTextureAnisotropy=1; } glConfig;
bool anisotropyExtension=false;
float anisotropyMaximum=16;
int anisotropyQueries=0;
bool emscripten_webgl_enable_extension(int,const char *name) {
    return anisotropyExtension && !std::strcmp(name,"EXT_texture_filter_anisotropic");
}
void glGetFloatv(GLenum name,GLfloat *value) {
    if(name!=GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT)std::exit(2);
    ++anisotropyQueries; *value=anisotropyMaximum;
}
struct glesProg_t {
    GLuint prog;
    GLint shadowExtrude=29;
    GLint lOrigin=4,vOrigin=5,projS=6,projT=7,projQ=8,fallS=9,bumpS=10,bumpT=11,
        diffS=12,diffT=13,specS=14,specT=15,colMod=16,colAdd=17,diffCol=18,specCol=19,
        gamma=21,eyeLocal=22,modelR0=23,modelR1=24,modelR2=25,depthRecip=26,partRadius=27,chanMask=28,
        colorFraction=30,colorTarget=31,screenScale=32,screenRecip=33;
    GLint heat[7]={34,35,36,37,38,39,40};
};
glesProg_t g_progFlat{1}, g_progInteraction{2}, g_progShadow{3}, g_progEnv{4},
    g_progBumpyEnv{5}, g_progGlass{6}, g_progSoft{7}, g_progSky{8}, g_progHeat{9}, g_progColorProcess{10};
glesProg_t *g_curProg = nullptr;
int g_lastVid=-1, g_lastFid=-1, g_inInteraction=0, g_heatModes[1024]{};
bool g_colorProcessIds[1024]{};
float g_vertexLocal[32][4]{};
bool g_vertexProgramEnabled=false, g_fragmentProgramEnabled=false, g_cpuShadowVertices=false;
bool g_shadowExtrude=false;
GLenum g_unitTarget[2]={GL_TEXTURE_2D,GL_TEXTURE_2D};
GLuint g_unitId[2]={1,1}, activeProgram=0;
bool texgen=false;
int checks=0, actualBinds=0, uploads=0, bufferUploads=0, drawCalls=0;
struct { int remaining=1, programBinds=0, draws=0, bufferCreates=0, uniformWrites=0, bufferBinds=0, attribWrites=0; } g_webPerf;
GLuint g_boundProgram=0, g_boundIndexBuffer=0, g_boundArrayBuffer=0, g_scratchIndexBuffer=0, actualIndexBuffer=0;
struct { bool enabled=true; bool GetBool(){return enabled;} } r_webStateCache;
int actualBufferBinds=0, actualPointers=0, actualEnables=0, scalarUploads=0, matrixUploads=0;
const void *lastIndices=nullptr;
int lastBytes=0;
int envUploads=0, lastUniform=-1;
float lastValue[4], g_glesEnvVertex[32][4]{}, g_glesEnvFragment[32][4]{};
void glUniform4fv(GLint loc,int,const GLfloat *value){++envUploads;lastUniform=loc;std::memcpy(lastValue,value,sizeof(lastValue));}
void glUniform3fv(GLint,int,const GLfloat*) { ++scalarUploads; }
void glUniform1f(GLint,GLfloat) { ++scalarUploads; }
void glUniform1i(GLint,GLint) { ++scalarUploads; }
void glUniformMatrix4fv(GLint,int,GLboolean,const GLfloat*) { ++matrixUploads; }
void glEnableVertexAttribArray(GLuint) { ++actualEnables; }
void glDisableVertexAttribArray(GLuint) { ++actualEnables; }
void glVertexAttribPointer(GLuint,GLint,GLenum,GLboolean,GLsizei,const GLvoid*) { ++actualPointers; }
void glUseProgram(GLuint program) { activeProgram=program; ++actualBinds; }
void glBindBuffer(GLenum target, GLuint buffer) { ++actualBufferBinds; if(target==GL_ELEMENT_ARRAY_BUFFER)actualIndexBuffer=buffer; }
void glDeleteBuffers(GLsizei count, const GLuint *buffers) {
    for(int i=0;i<count;++i)if(buffers[i]==actualIndexBuffer)actualIndexBuffer=0;
}
void glGenBuffers(GLsizei,GLuint *buffer) { *buffer=17; }
void glBufferData(GLenum,int bytes,const void*,GLenum) { ++bufferUploads; lastBytes=bytes; }
GLenum glGetError() { return GL_NO_ERROR; }
void fakeDraw(GLenum,GLsizei,GLenum,const void *indices) { ++drawCalls;lastIndices=indices; }
auto RealDrawElements=fakeDraw;
struct { bool enabled=true; bool GetBool(){return enabled;} } r_ignoreGLErrors;
int errorQueries=0, pendingErrors=0, errorReports=0;
constexpr GLenum GL_INVALID_ENUM=0x500, GL_INVALID_VALUE=0x501, GL_INVALID_OPERATION=0x502,
    GL_STACK_OVERFLOW=0x503, GL_STACK_UNDERFLOW=0x504, GL_OUT_OF_MEMORY=0x505;
GLenum qglGetError() { ++errorQueries; if(pendingErrors>0){--pendingErrors; return GL_INVALID_OPERATION;} return GL_NO_ERROR; }
struct idStr { static void snPrintf(char *dst,int size,const char *fmt,int value){std::snprintf(dst,size,fmt,value);} };
struct Common { void Printf(const char*,...){++errorReports;} } commonObject, *common=&commonObject;
void GLES_UploadProgramUniforms(glesProg_t*) { ++uploads; }
void GLES_SyncTexgenUniforms() {}
bool GLES_TexgenActive() { return texgen; }
void check(bool ok, const char *label) {
    if (!ok) { std::fprintf(stderr,"FAIL %s\n",label); std::exit(1); }
    ++checks;
}
'''
harness += program_enum + '\n'
harness += source[source.index('// Uniforms belong to a linked program'):source.index('static void GLES_UseProgram(')]
harness += '\n'.join(function(name) for name in (
    'GLES_InitAnisotropy', 'GLES_UseProgram', 'GLES_BindBuffer', 'GLES_DeleteBuffers', 'GLES_GenBuffers',
    'R_GLES_MarkInteraction', 'GLES_UseSelectedProgram',
    'GLES_BindProgramARB', 'GLES_SyncProgramForDraw', 'GLES_DrawElements',
    'GLES_ProgramEnvParameter4fvARB', 'GLES_ProgramLocalParameter4fvARB', 'R_GLES_SetShadowMode'))
harness += '\nstruct vertCache_t { vertCache_t *next, *prev; bool indexBuffer; };\n'
cache_source = (root / 'neo/renderer/VertexCache.cpp').read_text(encoding='utf-8')
harness += function('Web_FindCompatibleHeader', cache_source, r'vertCache_t \*')
init_source = (root / 'neo/renderer/RenderSystem_init.cpp').read_text(encoding='utf-8')
harness += function('GL_CheckErrors', init_source)
harness += r'''
void transition(int vertex, int fragment, bool fragmentFirst) {
    R_GLES_MarkInteraction(0);
    GLES_BindProgramARB(GL_VERTEX_PROGRAM_ARB,vertex);
    GLES_BindProgramARB(GL_FRAGMENT_PROGRAM_ARB,fragment);
    R_GLES_MarkInteraction(1);
    // The intermediate pair must not cancel the caller's lighting scope.
    GLES_BindProgramARB(fragmentFirst ? GL_FRAGMENT_PROGRAM_ARB : GL_VERTEX_PROGRAM_ARB,
                       fragmentFirst ? FPROG_INTERACTION : VPROG_INTERACTION);
    check(g_inInteraction==1,"scope survives first ARB program bind");
    GLES_BindProgramARB(fragmentFirst ? GL_VERTEX_PROGRAM_ARB : GL_FRAGMENT_PROGRAM_ARB,
                       fragmentFirst ? VPROG_INTERACTION : FPROG_INTERACTION);
    g_vertexProgramEnabled=g_fragmentProgramEnabled=true;
    GLES_SyncProgramForDraw();
    check(g_curProg==&g_progInteraction && activeProgram==g_progInteraction.prog,
          "completed pair draws with lighting shader");
    R_GLES_MarkInteraction(0);
    GLES_SyncProgramForDraw();
    check(g_curProg==&g_progFlat,"stale lighting binding outside scope uses flat shader");
}
int main() {
    pendingErrors=2; GL_CheckErrors();
    check(errorQueries==0 && pendingErrors==2,"normal web frames avoid synchronizing GL error queries");
    r_ignoreGLErrors.enabled=false; GL_CheckErrors();
    check(errorQueries==3 && pendingErrors==0 && errorReports==2,"enabled diagnostics drain and report GL errors");
    GL_CheckErrors();
    check(errorQueries==4 && errorReports==2,"clean diagnostic check stops after first query");
    pendingErrors=11; GL_CheckErrors();
    check(errorQueries==14 && pendingErrors==1 && errorReports==12,"diagnostic error loop stays bounded");
    r_ignoreGLErrors.enabled=true; pendingErrors=0;
    GLES_InitAnisotropy(1);
    check(!glConfig.anisotropicAvailable && glConfig.maxTextureAnisotropy==1 && !anisotropyQueries,"unsupported GPU avoids anisotropy enum queries");
    anisotropyExtension=true; GLES_InitAnisotropy(1);
    check(glConfig.anisotropicAvailable && glConfig.maxTextureAnisotropy==16 && anisotropyQueries==1,"supported GPU exposes actual anisotropy limit");
    GLES_InitAnisotropy(0);
    check(!glConfig.anisotropicAvailable && glConfig.maxTextureAnisotropy==1 && anisotropyQueries==1,"context loss clears anisotropy capability without querying invalid context");
    anisotropyMaximum=0; GLES_InitAnisotropy(1);
    check(!glConfig.anisotropicAvailable && glConfig.maxTextureAnisotropy==1,"invalid extension limit retains safe filtering fallback");
    anisotropyMaximum=8; GLES_InitAnisotropy(1);
    check(glConfig.anisotropicAvailable && glConfig.maxTextureAnisotropy==8,"restored GPU uses its new anisotropy limit");
    g_colorProcessIds[40]=g_colorProcessIds[41]=true;
    GLES_BindProgramARB(GL_VERTEX_PROGRAM_ARB,40);
    GLES_BindProgramARB(GL_FRAGMENT_PROGRAM_ARB,41);
    g_vertexProgramEnabled=g_fragmentProgramEnabled=true;
    GLES_SyncProgramForDraw();
    check(g_curProg==&g_progColorProcess,"color process selects dedicated shader for the registered pair");
    GLfloat fraction[]={.5f,.25f,1,0};
    GLES_ProgramLocalParameter4fvARB(GL_VERTEX_PROGRAM_ARB,0,fraction);
    check(lastUniform==30 && lastValue[1]==.25f && g_vertexLocal[0][2]==1,"color fraction writes after bind update shader and cached vertex locals");
    GLES_ProgramLocalParameter4fvARB(GL_VERTEX_PROGRAM_ARB,1,fraction);
    check(lastUniform==31,"color target writes after bind update dedicated uniform");
    GLES_ProgramEnvParameter4fvARB(GL_FRAGMENT_PROGRAM_ARB,0,fraction);
    check(lastUniform==32,"color process render texture scale updates after bind");
    GLES_ProgramEnvParameter4fvARB(GL_FRAGMENT_PROGRAM_ARB,1,fraction);
    check(lastUniform==33,"color process screen reciprocal updates after bind");
    GLES_BindProgramARB(GL_VERTEX_PROGRAM_ARB,999);
    check(g_curProg==&g_progFlat,"mismatched color process pair does not reuse effect");
    g_heatModes[50]=3;g_heatModes[51]=2;
    GLES_BindProgramARB(GL_VERTEX_PROGRAM_ARB,50);
    GLES_BindProgramARB(GL_FRAGMENT_PROGRAM_ARB,51);
    check(g_curProg==&g_progHeat,"stock mixed heat vertex/mask fragment pair selects heat shader");
    GLfloat heatValues[]={.75f,.625f,0,1};
    GLES_ProgramEnvParameter4fvARB(GL_FRAGMENT_PROGRAM_ARB,0,heatValues);
    check(lastUniform==38 && lastValue[0]==.75f,"heat screen scale updates immediately after bind");
    heatValues[0]=.001f;
    GLES_ProgramEnvParameter4fvARB(GL_FRAGMENT_PROGRAM_ARB,1,heatValues);
    check(lastUniform==39 && lastValue[0]==.001f,"heat viewport reciprocal updates immediately after bind");
    GLES_BindProgramARB(GL_VERTEX_PROGRAM_ARB,999);
    check(g_curProg==&g_progFlat,"unknown vertex program cannot inherit a heat fragment binding");
    GLES_BindProgramARB(GL_VERTEX_PROGRAM_ARB,50);
    GLuint heatProgram=g_progHeat.prog;g_progHeat.prog=0;
    GLES_UseSelectedProgram();
    check(g_curProg==&g_progFlat,"failed heat compilation does not bind shader zero");
    g_progHeat.prog=heatProgram;
    envUploads=0;
    std::memset(g_glesEnvVertex,0,sizeof(g_glesEnvVertex));
    std::memset(g_glesEnvFragment,0,sizeof(g_glesEnvFragment));
    g_heatModes[31]=g_heatModes[32]=1;
    const int previous[][2]={{VPROG_SOFT_PARTICLE,FPROG_SOFT_PARTICLE},
        {31,32},{VPROG_ENVIRONMENT,FPROG_ENVIRONMENT},
        {VPROG_BUMPY_ENVIRONMENT,FPROG_BUMPY_ENVIRONMENT},{0,0}};
    for (const auto &pair : previous) {
        transition(pair[0],pair[1],false);
        transition(pair[0],pair[1],true);
    }
    GLES_BindProgramARB(GL_VERTEX_PROGRAM_ARB,VPROG_SOFT_PARTICLE);
    GLES_BindProgramARB(GL_FRAGMENT_PROGRAM_ARB,FPROG_SOFT_PARTICLE);
    GLES_SyncProgramForDraw();
    check(g_curProg==&g_progSoft,"soft-particle pair remains usable");
    g_vertexProgramEnabled=g_fragmentProgramEnabled=false;
    GLES_SyncProgramForDraw();
    check(g_curProg==&g_progFlat,"disabled ARB programs use fixed pipeline");
    g_cpuShadowVertices=true;
    GLES_SyncProgramForDraw();
    check(g_curProg==&g_progShadow,"homogeneous CPU shadow vertices use shadow shader");
    int previousUploads=uploads;
    GLES_SyncProgramForDraw();
    check(uploads==previousUploads,"consecutive shadow draws retain uniforms");
    g_cpuShadowVertices=false; texgen=true;
    GLES_SyncProgramForDraw();
    check(g_curProg==&g_progFlat,"fixed texgen draw uses flat shader");
    int previousBinds=actualBinds;
    GLES_UseProgram(activeProgram);
    check(actualBinds==previousBinds,"same shader skips redundant GL bind");
    GLES_UseProgram(25);
    check(actualBinds==previousBinds+1 && activeProgram==25,"different shader binds once");
    texgen=false;
    GLES_BindBuffer(GL_ELEMENT_ARRAY_BUFFER,12);
    GLES_BindBuffer(GL_ARRAY_BUFFER,99);
    check(g_boundIndexBuffer==12,"vertex-buffer bind preserves index binding");
    GLES_DrawElements(4,3,GL_UNSIGNED_SHORT,(const void*)6);
    check(drawCalls==1 && lastIndices==(const void*)6 && bufferUploads==0,"VBO offsets pass through without CPU upload");
    GLuint deleted=99;
    GLES_DeleteBuffers(1,&deleted);
    check(g_boundIndexBuffer==12,"unrelated deletion preserves index binding");
    deleted=12;
    GLES_DeleteBuffers(1,&deleted);
    check(g_boundIndexBuffer==0 && actualIndexBuffer==0,"deleting bound EBO resets tracked binding");
    unsigned short indices[]={0,1,2};
    GLES_DrawElements(4,3,GL_UNSIGNED_SHORT,indices);
    check(drawCalls==2 && lastIndices==nullptr && bufferUploads==1 && lastBytes==6,"CPU indices upload and draw as offset zero");
    check(g_boundIndexBuffer==0 && actualIndexBuffer==0,"scratch EBO restores unbound state");
    GLES_DrawElements(4,3,GL_UNSIGNED_INT,indices);
    check(bufferUploads==2 && lastBytes==12,"32-bit CPU index upload uses correct byte count");
    g_curProg=&g_progInteraction;
    GLfloat values[]={1,2,3,4};
    GLES_ProgramEnvParameter4fvARB(GL_VERTEX_PROGRAM_ARB,4,values);
    check(envUploads==1 && lastUniform==4 && lastValue[2]==3,"changed interaction environment uploads immediately");
    GLES_ProgramEnvParameter4fvARB(GL_VERTEX_PROGRAM_ARB,4,values);
    check(envUploads==1,"unchanged environment skips redundant upload");
    GLES_ProgramEnvParameter4fvARB(GL_VERTEX_PROGRAM_ARB,5,values);
    check(envUploads==2 && lastUniform==5,"different environment slot uploads independently");
    g_curProg=&g_progFlat;
    values[0]=7;
    GLES_ProgramEnvParameter4fvARB(GL_VERTEX_PROGRAM_ARB,4,values);
    check(envUploads==2 && g_glesEnvVertex[4][0]==7,"unmapped environment stays cached for the next shader activation");
    GLES_ProgramEnvParameter4fvARB(GL_FRAGMENT_PROGRAM_ARB,21,values);
    check(envUploads==3 && lastUniform==21,"fragment environment cache is independent");
    g_lastVid=VPROG_INTERACTION;g_lastFid=FPROG_INTERACTION;
    previousUploads=uploads;
    GLES_UseSelectedProgram();
    check(g_curProg==&g_progInteraction && uploads==previousUploads+1,"shader activation refreshes its complete cached environment");
    vertCache_t head{},vertex{},index{};
    head.next=&vertex;head.prev=&index;
    vertex.next=&index;vertex.prev=&head;vertex.indexBuffer=false;
    index.next=&head;index.prev=&vertex;index.indexBuffer=true;
    check(Web_FindCompatibleHeader(&head,false)==&vertex,"vertex allocation finds compatible free buffer");
    check(Web_FindCompatibleHeader(&head,true)==&index,"index allocation skips incompatible free-list head");
    check(head.next==&vertex && index.prev==&vertex,"selection preserves the intrusive list");
    index.indexBuffer=false;
    check(Web_FindCompatibleHeader(&head,true)==&vertex,"missing classification falls back to normal allocation");
    head.next=&head;
    check(Web_FindCompatibleHeader(&head,true)==&head,"empty list returns sentinel");
    GLES_UseProgram(40);
    int oldEnv=envUploads;
    GLES_Uniform4fv(101,1,values);
    GLES_Uniform4fv(101,1,values);
    check(envUploads==oldEnv+1,"uniform writes deduplicate within a program");
    GLES_UseProgram(41);
    GLES_Uniform4fv(101,1,values);
    check(envUploads==oldEnv+2,"same numeric uniform location in another program uploads");
    values[3]=9;
    GLES_Uniform4fv(101,1,values);
    check(envUploads==oldEnv+3,"changed uniform component uploads");
    GLES_Uniform4fv(-1,1,values);
    check(envUploads==oldEnv+3,"inactive uniform is ignored");
    // Hash collisions must evict safely, not suppress a required write.
    GLES_Uniform4fv(101+512,1,values);
    GLES_Uniform4fv(101,1,values);
    check(envUploads==oldEnv+5,"uniform hash collision causes safe re-upload");
    GLfloat planes[16]={};
    GLES_Uniform4fv(103,4,planes);
    planes[15]=2;
    GLES_Uniform4fv(103,4,planes);
    check(envUploads==oldEnv+7,"last component of four-vector texgen array is tracked");
    GLES_UniformMatrix4fv(104,1,0,planes);
    GLES_UniformMatrix4fv(104,1,0,planes);
    check(matrixUploads==1,"identical MVP matrix uploads once");
    planes[15]=3;
    GLES_UniformMatrix4fv(104,1,0,planes);
    check(matrixUploads==2,"changed MVP matrix uploads");
    GLES_Uniform1i(105,0);
    GLES_Uniform1f(105,0);
    check(scalarUploads==2,"uniform type is included in cache key");
    r_webStateCache.enabled=false;
    values[0]=12;
    GLES_Uniform4fv(101,1,values);
    GLES_Uniform4fv(101,1,values);
    check(envUploads==oldEnv+9,"disabled cache uploads every write");
    r_webStateCache.enabled=true;
    GLES_Uniform4fv(101,1,values);
    check(envUploads==oldEnv+9,"re-enabled cache reflects uncached writes");
    std::memset(g_uniformState,0,sizeof(g_uniformState));
    GLES_Uniform4fv(101,1,values);
    check(envUploads==oldEnv+10,"shader/context reset forces uniform refresh");
    int oldBuffers=actualBufferBinds;
    GLES_BindBuffer(GL_ARRAY_BUFFER,100);
    GLES_BindBuffer(GL_ARRAY_BUFFER,100);
    check(actualBufferBinds==oldBuffers+1,"same vertex buffer binds once");
    GLES_AttribPointer(0,3,1,0,60,(void*)4);
    GLES_AttribPointer(0,3,1,0,60,(void*)4);
    check(actualPointers==1,"unchanged attribute pointer skips redundant write");
    GLES_BindBuffer(GL_ARRAY_BUFFER,101);
    GLES_AttribPointer(0,3,1,0,60,(void*)4);
    check(actualPointers==2,"attribute pointer captures new buffer despite identical offset");
    deleted=101;
    GLES_DeleteBuffers(1,&deleted);
    GLES_BindBuffer(GL_ARRAY_BUFFER,101);
    GLES_AttribPointer(0,3,1,0,60,(void*)4);
    check(actualPointers==3,"deleted buffer invalidates captured attribute state");
    GLES_AttribPointer(0,4,1,0,60,(void*)4);
    GLES_AttribPointer(0,4,1,0,60,(void*)8);
    check(actualPointers==5,"changed shadow layout and offset both upload");
    GLES_AttribEnabled(0,true);
    GLES_AttribEnabled(0,true);
    GLES_AttribEnabled(0,false);
    check(actualEnables==2,"attribute enables and disables preserve transitions");
    std::memset(g_attribState,0,sizeof(g_attribState));
    GLES_AttribEnabled(0,true);
    GLES_AttribPointer(0,4,1,0,60,(void*)8);
    check(actualEnables==3 && actualPointers==6,"fresh context restores vertex state");
    g_lastVid=VPROG_STENCIL_SHADOW;g_lastFid=32;
    GLES_UseSelectedProgram();
    check(g_curProg==&g_progShadow,"shadow vertex program wins over a stale heat-haze fragment binding");
    R_GLES_SetShadowMode(true);
    check(g_shadowExtrude,"shared shadow vertices select GPU extrusion");
    R_GLES_SetShadowMode(false);
    check(!g_shadowExtrude,"private shadow vertices retain their precomputed projection");
    values[0]=13;
    oldEnv=envUploads;
    GLES_ProgramEnvParameter4fvARB(GL_VERTEX_PROGRAM_ARB,4,values);
    check(envUploads==oldEnv+1 && lastUniform==4,"local shadow light origin uploads between bind and draw");
    std::printf("%d renderer-state checks passed\n",checks);
}
'''
output = Path(sys.argv[1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(harness, encoding='utf-8')
print('Wrote ' + str(output))
