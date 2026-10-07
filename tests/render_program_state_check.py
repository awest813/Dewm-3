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
#include <cstdint>
#include <set>
#include <unordered_map>
#include <vector>
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
using GLsizeiptr = long; using GLsizeiptrARB = long; using GLintptr = long; using GLintptrARB = long;
constexpr GLenum GL_ELEMENT_ARRAY_BUFFER=0x8893, GL_ARRAY_BUFFER=0x8892;
constexpr GLenum GL_UNSIGNED_INT=0x1405, GL_UNSIGNED_SHORT=0x1403, GL_STREAM_DRAW=0x88e0, GL_NO_ERROR=0;
constexpr GLenum GL_VERTEX_PROGRAM_ARB=0x8620, GL_FRAGMENT_PROGRAM_ARB=0x8804;
constexpr GLenum GL_TEXTURE_2D=0x0de1, GL_TEXTURE_CUBE_MAP=0x8513;
constexpr GLenum GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT=0x84ff;
constexpr GLenum GL_TEXTURE0=0x84c0, GL_FRONT=0x404, GL_BACK=0x405, GL_FRONT_AND_BACK=0x408;
constexpr GLenum GL_KEEP=0x1e00, GL_ALWAYS=0x207, GL_INCR_WRAP=0x8507, GL_DECR_WRAP=0x8508, GL_EQUAL=0x202, GL_ACTIVE_TEXTURE=0x84e0;
int activeTextureCalls=0, stencilOpCalls=0, stencilFuncCalls=0, unitDependentCalls=0, subUploads=0;
GLenum lastActiveTexture=0, lastStencilFace=0;
void glActiveTexture(GLenum unit) { ++activeTextureCalls; lastActiveTexture=unit; }
void glTexParameteri(GLenum,GLenum,GLint) { ++unitDependentCalls; }
void glTexSubImage2D(GLenum,GLint,GLint,GLint,GLsizei,GLsizei,GLenum,GLenum,const GLvoid*) { ++unitDependentCalls; }
void glTexImage3D(GLenum,GLint,GLint,GLsizei,GLsizei,GLsizei,GLint,GLenum,GLenum,const GLvoid*) { ++unitDependentCalls; }
void glCompressedTexImage2D(GLenum,GLint,GLenum,GLsizei,GLsizei,GLint,GLsizei,const GLvoid*) { ++unitDependentCalls; }
void glCopyTexImage2D(GLenum,GLint,GLenum,GLint,GLint,GLsizei,GLsizei,GLint) { ++unitDependentCalls; }
void glGetIntegerv(GLenum name,GLint *value) { *value=name==GL_ACTIVE_TEXTURE ? (GLint)lastActiveTexture : 0; }
void glGetBooleanv(GLenum,GLboolean *value) { *value=0; }
void glStencilOp(GLenum,GLenum,GLenum) { ++stencilOpCalls; lastStencilFace=GL_FRONT_AND_BACK; }
void glStencilOpSeparate(GLenum face,GLenum,GLenum,GLenum) { ++stencilOpCalls; lastStencilFace=face; }
void glStencilFunc(GLenum,GLint,GLuint) { ++stencilFuncCalls; }
void glBufferSubData(GLenum,GLintptr,GLsizeiptr,const void*) { ++subUploads; }
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
    GLint lOrigin=4,vOrigin=5,interEnv=6,diffCol=18,specCol=19,
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
enum textureType_t { TT_DISABLED, TT_2D, TT_3D, TT_CUBIC, TT_RECT };
struct { struct { struct { textureType_t textureType; } tmu[8]; } glState; } backEnd{};
GLuint g_unitId[2]={1,1}, activeProgram=0;
bool texgen=false;
int checks=0, actualBinds=0, uploads=0, bufferUploads=0, drawCalls=0;
struct { int remaining=1, programBinds=0, draws=0, bufferCreates=0, uniformWrites=0, bufferBinds=0, attribWrites=0,
    bufferDataCalls=0, bufferSubDataCalls=0, cpuIndexDraws=0, activeTextureCalls=0, stencilCalls=0,
    vertexArrayBinds=0, vertexArrayCreates=0; double uploadBytes=0; } g_webPerf;
GLuint g_boundProgram=0, g_boundIndexBuffer=0, g_boundArrayBuffer=0, g_scratchIndexBuffer=0, actualIndexBuffer=0;
struct { bool enabled=true; bool GetBool(){return enabled;} } r_webStateCache;
constexpr int CVAR_RENDERER=1, CVAR_BOOL=2;
struct idCVar {
    bool value;
    idCVar(const char*,const char *initial,int,const char*) : value(initial[0]=='1') {}
    bool GetBool() { return value; }
    void SetBool(bool v) { value=v; }
};
unsigned int g_glesFrame=1;
GLuint boundVao=0, nextVao=1000;
int vaoCreates=0, vaoDeletes=0;
void glGenVertexArrays(GLsizei,GLuint *vao) { *vao=++nextVao; ++vaoCreates; }
void glBindVertexArray(GLuint vao) { boundVao=vao; }
void glDeleteVertexArrays(GLsizei,const GLuint*) { ++vaoDeletes; }
constexpr GLenum GL_STATIC_DRAW=0x88e4;
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
void glBufferData(GLenum,GLsizeiptr bytes,const void*,GLenum) { ++bufferUploads; lastBytes=bytes; }
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
void GLES_ProbePixel() {}  // diagnostic webpixel tracer is not under test
bool GLES_TexgenActive() { return texgen; }
void check(bool ok, const char *label) {
    if (!ok) { std::fprintf(stderr,"FAIL %s\n",label); std::exit(1); }
    ++checks;
}
'''
harness += program_enum + '\n'
# Uniform cache, vertex state and vertex arrays, buffers and uploads,
# deferred texture-unit selection and the stencil state cache.
harness += source[source.index('// Uniforms belong to a linked program'):source.index('// WebAssembly checks indirect-call signatures')]
harness += function('GLES_InitAnisotropy') + '\n'
harness += 'idCVar r_webDeferInteractionEnv("r_webDeferInteractionEnv","1",CVAR_RENDERER|CVAR_BOOL,"");\n'
harness += 'bool g_interactionEnvDirty=true;\n'
harness += function('GLES_FlushInteractionEnv') + '\n'
harness += '\n'.join(function(name) for name in (
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
    check(g_boundIndexBuffer==0 && actualIndexBuffer==17 && boundVao==0,"scratch EBO draws in the default vertex array and restores the requested state");
    GLES_DrawElements(4,3,GL_UNSIGNED_INT,indices);
    check(bufferUploads==2 && lastBytes==12,"32-bit CPU index upload uses correct byte count");
    g_curProg=&g_progInteraction;
    g_interactionEnvDirty=false;
    GLfloat values[]={1,2,3,4};
    GLES_ProgramEnvParameter4fvARB(GL_VERTEX_PROGRAM_ARB,4,values);
    check(envUploads==0 && g_interactionEnvDirty,"interaction vertex environment waits for the draw");
    GLES_ProgramEnvParameter4fvARB(GL_VERTEX_PROGRAM_ARB,5,values);
    g_progInteraction.prog=activeProgram=g_boundProgram=2;
    g_vertexProgramEnabled=g_fragmentProgramEnabled=true;g_inInteraction=1;
    GLES_DrawElements(4,3,GL_UNSIGNED_SHORT,nullptr);
    check(envUploads==1 && lastUniform==6 && lastValue[2]==3 && !g_interactionEnvDirty,
        "one array upload before the draw carries every changed interaction slot");
    GLES_ProgramEnvParameter4fvARB(GL_VERTEX_PROGRAM_ARB,4,values);
    GLES_DrawElements(4,3,GL_UNSIGNED_SHORT,nullptr);
    check(envUploads==1,"unchanged environment draws without an upload");
    values[1]=9;
    GLES_ProgramEnvParameter4fvARB(GL_VERTEX_PROGRAM_ARB,17,values);
    GLES_DrawElements(4,3,GL_UNSIGNED_SHORT,nullptr);
    check(envUploads==2 && lastUniform==6,"last packed slot (color add) reaches the array");
    r_webDeferInteractionEnv.SetBool(false);
    values[1]=10;
    GLES_ProgramEnvParameter4fvARB(GL_VERTEX_PROGRAM_ARB,12,values);
    check(envUploads==3 && !g_interactionEnvDirty,"immediate mode uploads the array on each change");
    r_webDeferInteractionEnv.SetBool(true);
    GLES_ProgramEnvParameter4fvARB(GL_VERTEX_PROGRAM_ARB,18,values);
    check(envUploads==3 && !g_interactionEnvDirty,"slots outside env[4..17] do not touch the interaction array");
    g_inInteraction=0;g_vertexProgramEnabled=g_fragmentProgramEnabled=false;
    envUploads=2;
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
    // Default vertex array: bindings and attributes apply at upload/draw time.
    r_webVertexArrays.SetBool(false);
    std::memset(g_attribState,0,sizeof(g_attribState));
    std::memset(g_defaultAttribs,0,sizeof(g_defaultAttribs));
    g_actualArrayBuffer=0; g_defaultElement=0; GLES_BindVertexArrayNow(0);
    int oldBuffers=actualBufferBinds, oldPointers=actualPointers, oldEnables=actualEnables;
    GLES_BindBuffer(GL_ARRAY_BUFFER,100);
    GLES_BindBuffer(GL_ARRAY_BUFFER,100);
    check(actualBufferBinds==oldBuffers,"array buffer binds wait for an upload or draw");
    GLES_BufferData(GL_ARRAY_BUFFER,16,nullptr,GL_STATIC_DRAW);
    GLES_BufferData(GL_ARRAY_BUFFER,16,nullptr,GL_STATIC_DRAW);
    check(actualBufferBinds==oldBuffers+1,"same vertex buffer binds once for repeated uploads");
    GLES_BindBuffer(GL_ELEMENT_ARRAY_BUFFER,12);
    GLES_AttribPointer(0,3,1,0,60,(void*)4);
    GLES_AttribEnabled(0,true);
    GLES_DrawElements(4,3,GL_UNSIGNED_SHORT,nullptr);
    check(actualPointers==oldPointers+1 && actualEnables==oldEnables+1 && actualIndexBuffer==12,"default vertex array applies pointer, enable and element buffer at draw");
    GLES_AttribPointer(0,3,1,0,60,(void*)4);
    GLES_AttribEnabled(0,true);
    GLES_DrawElements(4,3,GL_UNSIGNED_SHORT,nullptr);
    check(actualPointers==oldPointers+1 && actualEnables==oldEnables+1,"unchanged attribute pointer and enable are not resent");
    GLES_BindBuffer(GL_ARRAY_BUFFER,101);
    GLES_AttribPointer(0,3,1,0,60,(void*)4);
    GLES_DrawElements(4,3,GL_UNSIGNED_SHORT,nullptr);
    check(actualPointers==oldPointers+2,"attribute pointer captures new buffer despite identical offset");
    deleted=101;
    GLES_DeleteBuffers(1,&deleted);
    GLES_BindBuffer(GL_ARRAY_BUFFER,101);
    GLES_AttribPointer(0,3,1,0,60,(void*)4);
    GLES_DrawElements(4,3,GL_UNSIGNED_SHORT,nullptr);
    check(actualPointers==oldPointers+3,"deleted buffer invalidates captured attribute state");
    GLES_AttribPointer(0,4,1,0,60,(void*)4);
    GLES_DrawElements(4,3,GL_UNSIGNED_SHORT,nullptr);
    GLES_AttribPointer(0,4,1,0,60,(void*)8);
    GLES_DrawElements(4,3,GL_UNSIGNED_SHORT,nullptr);
    check(actualPointers==oldPointers+5,"changed shadow layout and offset both upload");
    GLES_AttribEnabled(0,false);
    GLES_DrawElements(4,3,GL_UNSIGNED_SHORT,nullptr);
    GLES_AttribEnabled(0,true);
    GLES_AttribEnabled(0,true);
    GLES_DrawElements(4,3,GL_UNSIGNED_SHORT,nullptr);
    check(actualEnables==oldEnables+3,"attribute enables and disables preserve transitions");
    // Cached vertex arrays for static geometry.
    r_webVertexArrays.SetBool(true);
    int created=vaoCreates;
    auto surface=[](GLuint vbo,GLuint ibo,const void *offset){
        GLES_BindBuffer(GL_ARRAY_BUFFER,vbo);
        GLES_AttribPointer(0,3,1,0,60,offset);
        GLES_AttribEnabled(0,true);
        GLES_BindBuffer(GL_ELEMENT_ARRAY_BUFFER,ibo);
        GLES_DrawElements(4,3,GL_UNSIGNED_SHORT,nullptr);
    };
    surface(200,201,nullptr);
    GLuint vaoA=boundVao;
    check(vaoCreates==created+1 && vaoA!=0 && actualIndexBuffer==201,"static geometry draws through a new vertex array holding its element buffer");
    surface(210,211,nullptr);
    check(vaoCreates==created+2 && boundVao!=vaoA,"different static geometry gets its own vertex array");
    int pointers=actualPointers, buffers=actualBufferBinds;
    surface(200,201,nullptr);
    check(vaoCreates==created+2 && boundVao==vaoA && actualPointers==pointers && actualBufferBinds==buffers,"returning to a cached layout only binds its vertex array");
    surface(200,211,nullptr);
    check(vaoCreates==created+3,"the element buffer is part of the vertex array key");
    surface(200,201,(const void*)12);
    check(vaoCreates==created+4,"attribute offsets are part of the vertex array key");
    GLES_BindBuffer(GL_ARRAY_BUFFER,220);
    GLES_BufferData(GL_ARRAY_BUFFER,16,nullptr,GL_STREAM_DRAW);
    surface(220,201,nullptr);
    check(boundVao==0 && vaoCreates==created+4,"streamed vertices use the default vertex array");
    surface(200,201,nullptr);
    GLES_BindBuffer(GL_ELEMENT_ARRAY_BUFFER,230);
    GLES_BufferData(GL_ELEMENT_ARRAY_BUFFER,6,nullptr,GL_STATIC_DRAW);
    check(boundVao==0 && actualIndexBuffer==230,"element uploads never modify a cached vertex array");
    surface(200,201,nullptr);
    check(boundVao==vaoA,"cached vertex array still holds its element buffer after an upload");
    int deletes=vaoDeletes;
    deleted=200;
    GLES_DeleteBuffers(1,&deleted);
    check(vaoDeletes==deletes+3 && boundVao==0,"deleting a buffer deletes every vertex array that references it");
    surface(210,211,nullptr);
    check(vaoCreates==created+4,"vertex arrays for other buffers survive");
    deleted=211;
    GLES_DeleteBuffers(1,&deleted);
    check(vaoDeletes==deletes+4,"deleting an element buffer deletes vertex arrays keyed by it");
    // Live scenes re-upload dynamic buffers every frame at new offsets; a
    // vertex array for them would never be reused.
    created=vaoCreates;
    GLES_BindBuffer(GL_ARRAY_BUFFER,240);
    GLES_BufferData(GL_ARRAY_BUFFER,64,nullptr,GL_STATIC_DRAW);
    surface(240,201,nullptr);
    check(boundVao==0 && vaoCreates==created,"a buffer uploaded this frame draws without a new vertex array");
    g_glesFrame+=2;
    surface(240,201,nullptr);
    check(boundVao==0 && vaoCreates==created,"still volatile two frames after its upload");
    g_glesFrame+=1;
    surface(240,201,nullptr);
    check(boundVao!=0 && vaoCreates==created+1,"a buffer unchanged for three frames gets a cached vertex array");
    GLES_BindBuffer(GL_ELEMENT_ARRAY_BUFFER,201);
    GLES_BufferData(GL_ELEMENT_ARRAY_BUFFER,6,nullptr,GL_STATIC_DRAW);
    surface(240,201,nullptr);
    check(boundVao==0 && vaoCreates==created+1,"re-uploading the element buffer makes the draw volatile again");
    g_glesFrame+=3;
    surface(240,201,nullptr);
    check(vaoCreates==created+1 && boundVao!=0,"once stable again it reuses its cached vertex array");
    unsigned short cpu[]={0,1,2};
    surface(210,0,nullptr);
    int before=vaoCreates;
    GLES_DrawElements(4,3,GL_UNSIGNED_SHORT,cpu);
    check(boundVao==0 && vaoCreates==before,"CPU-index draws use the default vertex array");
    r_webStateCache.enabled=false;
    surface(210,0,nullptr);
    check(boundVao==0,"disabled state cache draws through the default vertex array");
    r_webStateCache.enabled=true;
    GLES_ClearVertexArrays();
    check(g_vaoCache.empty() && boundVao==0,"clearing the cache unbinds and deletes cached vertex arrays");
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
    // Texture-unit selection is deferred until a unit-dependent call.
    g_activeTexture=g_wantedActiveTexture=GL_TEXTURE0; activeTextureCalls=0;
    GLES_ActiveTexture(GL_TEXTURE0+1);GLES_ActiveTexture(GL_TEXTURE0+2);GLES_ActiveTexture(GL_TEXTURE0+3);
    check(activeTextureCalls==0,"unit selections without texture work send nothing");
    GLES_TexParameteri(GL_TEXTURE_2D,0,0);
    check(activeTextureCalls==1 && lastActiveTexture==GL_TEXTURE0+3 && unitDependentCalls==1,"texture call first selects the latest requested unit");
    GLES_ActiveTexture(GL_TEXTURE0+3);GLES_TexSubImage2D(GL_TEXTURE_2D,0,0,0,1,1,0,0,nullptr);
    check(activeTextureCalls==1,"already selected unit is not selected again");
    GLES_ActiveTexture(GL_TEXTURE0+5);GLES_ActiveTexture(GL_TEXTURE0+3);GLES_CopyTexImage2D(GL_TEXTURE_2D,0,0,0,0,1,1,0);
    check(activeTextureCalls==1,"returning to the selected unit before texture work sends nothing");
    GLES_ActiveTexture(GL_TEXTURE0+6);GLint queried=0;GLES_GetIntegerv(GL_ACTIVE_TEXTURE,&queried);
    check(activeTextureCalls==2 && queried==(GLint)(GL_TEXTURE0+6),"state queries observe the requested unit");
    GLES_ActiveTexture(GL_TEXTURE0+1);GLES_TexImage3D(GL_TEXTURE_2D,0,0,1,1,1,0,0,0,nullptr);
    GLES_ActiveTexture(GL_TEXTURE0+2);GLES_CompressedTexImage2D(GL_TEXTURE_2D,0,0,1,1,0,0,nullptr);
    check(activeTextureCalls==4 && lastActiveTexture==GL_TEXTURE0+2,"each unit-dependent upload selects its unit");
    r_webStateCache.enabled=false;
    GLES_ActiveTexture(GL_TEXTURE0+2);
    check(activeTextureCalls==5,"disabled state cache selects immediately for comparison");
    r_webStateCache.enabled=true;
    // Stencil state starts from a new context's defaults.
    GLES_ResetStencilState(); stencilOpCalls=stencilFuncCalls=0;
    GLES_StencilOp(GL_KEEP,GL_KEEP,GL_KEEP);GLES_StencilFunc(GL_ALWAYS,0,~0u);
    check(stencilOpCalls==0 && stencilFuncCalls==0,"default stencil state is not resent");
    GLES_StencilOpSeparate(GL_BACK,GL_KEEP,GL_DECR_WRAP,GL_KEEP);GLES_StencilOpSeparate(GL_FRONT,GL_KEEP,GL_INCR_WRAP,GL_KEEP);
    GLES_StencilOpSeparate(GL_BACK,GL_KEEP,GL_DECR_WRAP,GL_KEEP);GLES_StencilOpSeparate(GL_FRONT,GL_KEEP,GL_INCR_WRAP,GL_KEEP);
    check(stencilOpCalls==2,"repeated per-volume stencil faces are sent once");
    GLES_StencilOpSeparate(GL_FRONT,GL_KEEP,GL_KEEP,GL_DECR_WRAP);
    check(stencilOpCalls==3 && lastStencilFace==GL_FRONT,"changed face is sent alone");
    GLES_StencilOp(GL_KEEP,GL_KEEP,GL_KEEP);GLES_StencilOpSeparate(GL_BACK,GL_KEEP,GL_KEEP,GL_KEEP);
    check(stencilOpCalls==4,"two-face stencil op updates both cached faces");
    GLES_StencilOpSeparate(GL_FRONT_AND_BACK,GL_KEEP,GL_KEEP,GL_INCR_WRAP);GLES_StencilOpSeparate(GL_FRONT,GL_KEEP,GL_KEEP,GL_INCR_WRAP);
    check(stencilOpCalls==5,"front-and-back separate op updates both cached faces");
    GLES_StencilFunc(GL_ALWAYS,128,255);GLES_StencilFunc(GL_ALWAYS,128,255);GLES_StencilFunc(GL_EQUAL,128,255);
    check(stencilFuncCalls==2,"stencil function sends only changes");
    r_webStateCache.enabled=false;
    GLES_StencilFunc(GL_EQUAL,128,255);GLES_StencilOp(GL_KEEP,GL_KEEP,GL_INCR_WRAP);
    check(stencilFuncCalls==3 && stencilOpCalls==6,"disabled state cache sends every stencil call");
    r_webStateCache.enabled=true;
    GLES_StencilOp(GL_KEEP,GL_KEEP,GL_INCR_WRAP);
    check(stencilOpCalls==6,"re-enabled cache reflects uncached stencil writes");
    // Sky cubes: fixed-function samples only enabled units.
    g_cpuShadowVertices=false; texgen=false; g_vertexProgramEnabled=g_fragmentProgramEnabled=false;
    g_curProg=&g_progFlat; g_unitTarget[0]=GL_TEXTURE_CUBE_MAP; g_unitId[0]=5; g_unitTarget[1]=GL_TEXTURE_2D; g_unitId[1]=9;
    backEnd.glState.tmu[0].textureType=TT_CUBIC; backEnd.glState.tmu[1].textureType=TT_DISABLED;
    GLES_SyncProgramForDraw();
    check(g_curProg==&g_progSky,"sky cube ignores a stale 2D binding on a disabled unit");
    backEnd.glState.tmu[1].textureType=TT_2D;
    GLES_SyncProgramForDraw();
    check(g_curProg==&g_progFlat,"an enabled second 2D unit keeps the flat program");
    backEnd.glState.tmu[1].textureType=TT_CUBIC;
    GLES_SyncProgramForDraw();
    check(g_curProg==&g_progSky,"two cube units still use the sky program");
    // A unit keeps 2D and cube bindings; the engine's enabled type decides.
    g_unitTarget[0]=GL_TEXTURE_CUBE_MAP; backEnd.glState.tmu[0].textureType=TT_2D; backEnd.glState.tmu[1].textureType=TT_DISABLED;
    GLES_SyncProgramForDraw();
    check(g_curProg==&g_progFlat,"unit zero enabled as 2D ignores its stale cube binding");
    g_unitTarget[0]=GL_TEXTURE_2D;
    std::printf("%d renderer-state checks passed\n",checks);
}
'''
output = Path(sys.argv[1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(harness, encoding='utf-8')
print('Wrote ' + str(output))
