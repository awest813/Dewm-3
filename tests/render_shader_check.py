"""Generate a local WebGL2 pixel regression page from the actual renderer GLSL.

Run: python tests/render_shader_check.py build-web/render-check.html
Serve with web/serve.py, then open /render-check.html. No retail assets required.
"""
import ast
import json
from pathlib import Path
import re
import sys

source = (Path(__file__).resolve().parents[1] / 'neo/renderer/tr_gles.cpp').read_text(encoding='utf-8')
shaders = {}
for name, body in re.findall(r'static const char \*(GLES_[VF]S_\w+)\s*=\s*((?:"(?:\\.|[^"\\])*"|//[^\n]*|\s)+);', source):
    shaders[name] = ''.join(ast.literal_eval(s) for s in re.findall(r'"(?:\\.|[^"\\])*"', body))

# Exercise the operations selected by the actual WebGL initialization path.
# Missing initialization must fail generation rather than silently use defaults.
config = source[source.index('void R_GLES_InitConfig( void ) {'):]
stencil_ops = []
for field in ('stencilIncr', 'stencilDecr'):
    match = re.search(r'tr\.' + field + r'\s*=\s*GL_(\w+)\s*;', config)
    if not match:
        raise ValueError('WebGL initialization does not set tr.' + field)
    stencil_ops.append(match.group(1))

page = r'''<!doctype html><meta charset="utf-8"><title>Doom 3 rendering checks</title>
<style>body{background:#111827;color:#e5e7eb;font:16px system-ui;padding:24px}pre{white-space:pre-wrap}</style>
<h1>Doom 3 rendering checks</h1><canvas id="gpu" width="1" height="1"></canvas><pre id="report">Running…</pre>
<script>
const s=SHADERS, report=document.querySelector('#report');
const gl=document.querySelector('#gpu').getContext('webgl2',{antialias:false,depth:true,stencil:true});
let count=0, lines=[];
function assert(ok,msg){if(!ok)throw Error(msg);count++;lines.push('PASS '+msg);}
function shader(type,code){const x=gl.createShader(type);gl.shaderSource(x,code);gl.compileShader(x);
 if(!gl.getShaderParameter(x,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(x));return x;}
function program(v,f,varyings){const p=gl.createProgram();gl.attachShader(p,shader(gl.VERTEX_SHADER,v));gl.attachShader(p,shader(gl.FRAGMENT_SHADER,f));
 if(varyings)gl.transformFeedbackVaryings(p,varyings,gl.INTERLEAVED_ATTRIBS);
 gl.linkProgram(p);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(p));gl.useProgram(p);return p;}
function uniform(p,n,v){const l=gl.getUniformLocation(p,n);if(v.length===1)gl.uniform1f(l,v[0]);else gl['uniform'+v.length+'fv'](l,v);}
function texture(p,name,unit,data){gl.activeTexture(gl.TEXTURE0+unit);const t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,t);
 gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);
 gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA8,1,1,0,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array(data));gl.uniform1i(gl.getUniformLocation(p,name),unit);}
function draw(){gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);gl.drawArrays(gl.TRIANGLES,0,3);const b=new Uint8Array(4);gl.readPixels(0,0,1,1,gl.RGBA,gl.UNSIGNED_BYTE,b);return [...b];}
function pixel(expected,label){const got=draw();assert(got.every((x,i)=>Math.abs(x-expected[i])<=2),label+' ['+got+']');}
const triangle='vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);gl_Position=vec4(p*2.0-1.0,0,1);';
try{
 assert(!!gl,'WebGL2 available');
 const aniso=gl.getExtension('EXT_texture_filter_anisotropic');
 if(aniso){
  const maximum=gl.getParameter(aniso.MAX_TEXTURE_MAX_ANISOTROPY_EXT);
  const t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,t);
  gl.texParameterf(gl.TEXTURE_2D,aniso.TEXTURE_MAX_ANISOTROPY_EXT,Math.min(8,maximum));
  assert(gl.getTexParameter(gl.TEXTURE_2D,aniso.TEXTURE_MAX_ANISOTROPY_EXT)===Math.min(8,maximum),'GPU accepts anisotropic filtering; maximum '+maximum);
  gl.deleteTexture(t);
 }else lines.push('INFO anisotropic filtering unavailable; engine must retain 1x fallback');
 for(const name of ['INTERACTION','SHADOW','FLAT','ENV','BUMPYENV','SOFT','GLASS','SKY','COLORPROCESS','HEAT']){
  program(s.GLES_VS_HEAD+s['GLES_VS_'+name],s.GLES_FS_HEAD+s['GLES_FS_'+name]);assert(true,name+' shaders compile and link');
 }
 const stencilOps=STENCIL_OPS.map(name=>gl[name]);
 assert(gl.getParameter(gl.STENCIL_BITS)>=8,'shadow counting has an eight-bit stencil attachment');
 program('#version 300 es\nvoid main(){'+triangle+'}', '#version 300 es\nprecision highp float;out vec4 o_col;void main(){o_col=vec4(1);}');
 gl.enable(gl.STENCIL_TEST);gl.stencilMask(255);gl.clearDepth(0);
 function volumeCrossing(initial,operation,expected,label){
  gl.clearStencil(initial);gl.clear(gl.STENCIL_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
  gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LESS);gl.colorMask(false,false,false,false);
  gl.stencilFunc(gl.ALWAYS,0,255);gl.stencilOp(gl.KEEP,operation,gl.KEEP);
  gl.drawArrays(gl.TRIANGLES,0,3);
  gl.disable(gl.DEPTH_TEST);gl.colorMask(true,true,true,true);
  gl.stencilFunc(gl.EQUAL,expected,255);gl.stencilOp(gl.KEEP,gl.KEEP,gl.KEEP);
  pixel([255,255,255,255],label);
 }
 volumeCrossing(128,stencilOps[0],129,'z-fail back crossing increments the shadow count');
 volumeCrossing(129,stencilOps[1],128,'z-fail front crossing restores the shadow count');
 volumeCrossing(255,stencilOps[0],0,'overlapping shadow count wraps instead of saturating');
 volumeCrossing(0,stencilOps[1],255,'reverse shadow crossing wraps below zero');
 gl.disable(gl.STENCIL_TEST);gl.clearDepth(1);gl.clearStencil(0);
 const shadowVS=s.GLES_VS_SHADOW.replace('gl_Position = u_mvp * pos;', 'testPosition = gl_Position = u_mvp * pos;');
 let shadow=program(s.GLES_VS_HEAD+'out vec4 testPosition;\n'+shadowVS,s.GLES_FS_HEAD+s.GLES_FS_SHADOW,['testPosition']);
 const feedback=gl.createBuffer();gl.bindBuffer(gl.TRANSFORM_FEEDBACK_BUFFER,feedback);
 gl.bufferData(gl.TRANSFORM_FEEDBACK_BUFFER,16,gl.STREAM_READ);gl.bindBufferBase(gl.TRANSFORM_FEEDBACK_BUFFER,0,feedback);
 gl.uniformMatrix4fv(gl.getUniformLocation(shadow,'u_mvp'),false,new Float32Array([2,0,0,0,0,3,0,0,0,0,4,0,5,6,7,1]));
 uniform(shadow,'u_lOrigin',[4,-2,1,0]);
 function shadowPosition(pos,extrude,expected,label){
  gl.vertexAttrib4fv(0,pos);uniform(shadow,'u_shadowExtrude',[extrude]);gl.enable(gl.RASTERIZER_DISCARD);
  gl.beginTransformFeedback(gl.POINTS);gl.drawArrays(gl.POINTS,0,1);gl.endTransformFeedback();gl.disable(gl.RASTERIZER_DISCARD);
  const got=new Float32Array(4);gl.getBufferSubData(gl.TRANSFORM_FEEDBACK_BUFFER,0,got);
  assert(got.every((v,i)=>Math.abs(v-expected[i])<.0001),label+' ['+[...got]+']');
 }
 shadowPosition([7,8,9,1],1,[19,30,43,1],'GPU shadow near vertex matches ordinary MVP');
 shadowPosition([7,8,9,0],1,[6,30,32,0],'GPU shadow infinite vertex matches CPU extrusion and MVP');
 shadowPosition([3,10,8,0],0,[6,30,32,0],'private CPU shadow avoids a second extrusion');
 // The interaction shader receives vertex program.env[4..17] as one array;
 // each texgen row, light projection and color term must keep its engine slot.
 const env=[];for(let k=0;k<18;k++)env.push([k+1,(k%5)-2,k*.5,3-k*.25]);
 const dot=(a,b)=>a.reduce((t,x,i)=>t+x*b[i],0);
 const inter=program(s.GLES_VS_HEAD+s.GLES_VS_INTERACTION,s.GLES_FS_HEAD+s.GLES_FS_INTERACTION,['v_bump','v_diff','v_spec','v_lproj','v_col','v_L']);
 // A cube and a 2D sampler may not share a unit, even with rasterization off.
 ['u_cube','u_bump','u_fall','u_proj','u_diff','u_spec','u_spectab'].forEach((n,i)=>gl.uniform1i(gl.getUniformLocation(inter,n),i));
 gl.uniform4fv(gl.getUniformLocation(inter,'u_ienv'),new Float32Array(env.slice(4,18).flat()));
 gl.uniformMatrix4fv(gl.getUniformLocation(inter,'u_mvp'),false,new Float32Array([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]));
 const tc=[5,7,0,1],pos=[1,2,3,1],col=[.5,.25,1,2];
 gl.vertexAttrib4fv(0,pos);gl.vertexAttrib4fv(1,tc);gl.vertexAttrib4fv(2,col);
 gl.vertexAttrib4fv(3,[0,0,1,0]);gl.vertexAttrib4fv(4,[1,0,0,0]);gl.vertexAttrib4fv(5,[0,1,0,0]);
 const interFeedback=gl.createBuffer();gl.bindBuffer(gl.TRANSFORM_FEEDBACK_BUFFER,interFeedback);
 gl.bufferData(gl.TRANSFORM_FEEDBACK_BUFFER,68,gl.STREAM_READ);gl.bindBufferBase(gl.TRANSFORM_FEEDBACK_BUFFER,0,interFeedback);
 gl.enable(gl.RASTERIZER_DISCARD);gl.beginTransformFeedback(gl.POINTS);gl.drawArrays(gl.POINTS,0,1);gl.endTransformFeedback();gl.disable(gl.RASTERIZER_DISCARD);
 const interGot=new Float32Array(17);gl.getBufferSubData(gl.TRANSFORM_FEEDBACK_BUFFER,0,interGot);
 const interWant=[dot(tc,env[10]),dot(tc,env[11]),dot(tc,env[12]),dot(tc,env[13]),dot(tc,env[14]),dot(tc,env[15]),
  dot(pos,env[6]),dot(pos,env[7]),dot(pos,env[8]),dot(pos,env[9]),...col.map((c,i)=>c*env[16][i]+env[17][i]),...[0,1,2].map(i=>env[4][i]-pos[i])];
 assert(interWant.every((v,i)=>Math.abs(interGot[i]-v)<=1e-4*Math.max(1,Math.abs(v))),
  'packed interaction environment keeps engine slots 4 and 6-17 ['+[...interGot]+']');
 gl.vertexAttrib4fv(1,[0,0,0,1]);gl.vertexAttrib4fv(2,[1,1,1,1]);
 gl.bindBufferBase(gl.TRANSFORM_FEEDBACK_BUFFER,0,null);gl.bindBuffer(gl.TRANSFORM_FEEDBACK_BUFFER,null);
 let p=program('#version 300 es\nvoid main(){'+triangle+'}',s.GLES_FS_HEAD+'out vec4 o_col;uniform float a;void main(){if(!alphaPass(a))discard;o_col=vec4(1);}');
 for(let f=512;f<=519;f++)for(const a of [.25,.5,.75]){
  uniform(p,'a',[a]);uniform(p,'u_alphaTest',[1,.5,f]);
  const pass=[false,a<.5,a===.5,a<=.5,a>.5,a!==.5,a>=.5,true][f-512];
  pixel(pass?[255,255,255,255]:[0,0,0,0],'alpha function '+f+' at '+a);
 }
 uniform(p,'u_alphaTest',[0,.5,512]);pixel([255,255,255,255],'disabled alpha test bypasses NEVER');
 p=program('#version 300 es\nprecision highp float;out vec2 v_bump,v_diff,v_spec;out vec4 v_lproj,v_col;out vec3 v_L,v_H;uniform vec3 testL,testH;void main(){'+triangle+'v_bump=v_diff=v_spec=vec2(.5);v_lproj=vec4(.5,.5,1,.5);v_col=vec4(1);v_L=testL;v_H=testH;}',s.GLES_FS_HEAD+s.GLES_FS_INTERACTION);
 uniform(p,'u_gamma',[1,1,1,1]);uniform(p,'u_diffCol',[1,1,1,1]);uniform(p,'u_specCol',[0,0,0,0]);uniform(p,'testL',[1,0,0]);uniform(p,'testH',[1,0,0]);
 texture(p,'u_bump',1,[0,128,128,255]);texture(p,'u_fall',2,[255,255,255,255]);texture(p,'u_proj',3,[255,255,255,255]);texture(p,'u_diff',4,[64,128,192,255]);texture(p,'u_spec',5,[64,64,64,255]);texture(p,'u_spectab',6,[128,128,128,255]);
 gl.activeTexture(gl.TEXTURE0);const interactionCube=gl.createTexture();gl.bindTexture(gl.TEXTURE_CUBE_MAP,interactionCube);
 gl.texParameteri(gl.TEXTURE_CUBE_MAP,gl.TEXTURE_MIN_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_CUBE_MAP,gl.TEXTURE_MAG_FILTER,gl.NEAREST);
 const lightFaces=[[255,128,128,255],[0,128,128,255],[128,255,128,255],[128,0,128,255],[128,128,255,255],[128,128,0,255]];
 for(let i=0;i<6;i++)gl.texImage2D(gl.TEXTURE_CUBE_MAP_POSITIVE_X+i,0,gl.RGBA8,1,1,0,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array(lightFaces[i]));
 gl.uniform1i(gl.getUniformLocation(p,'u_cube'),0);
 pixel([64,128,192,255],'RXGB alpha channel supplies normal X');
 gl.texImage2D(gl.TEXTURE_CUBE_MAP_POSITIVE_X,0,gl.RGBA8,1,1,0,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array([192,128,128,255]));
 pixel([32,65,97,255],'diffuse light retains normalization-cube sample length instead of renormalizing');
 gl.texImage2D(gl.TEXTURE_CUBE_MAP_POSITIVE_X,0,gl.RGBA8,1,1,0,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array(lightFaces[0]));
 uniform(p,'testL',[-1,0,0]);pixel([0,0,0,255],'back-facing normal rejects diffuse light');
 uniform(p,'testL',[1,0,0]);uniform(p,'u_diffCol',[0,0,0,0]);uniform(p,'u_specCol',[1,1,1,1]);pixel([64,64,64,255],'specular table response and engine factor two');
 uniform(p,'testL',[-1,0,0]);uniform(p,'u_specCol',[1,0,0,1]);pixel([0,0,0,255],'back-facing light cannot leak a red specular highlight');
 uniform(p,'testL',[1,0,0]);uniform(p,'u_diffCol',[1,1,1,1]);uniform(p,'u_specCol',[0,0,0,0]);
 texture(p,'u_fall',2,[255,0,128,255]);pixel([64,0,96,255],'interaction multiplies the whole falloff texel like interaction.vfp');
 texture(p,'u_fall',2,[255,255,255,255]);
 p=program('#version 300 es\nprecision highp float;out vec2 v_tc;out vec4 v_col,v_gen0,v_gen1;void main(){'+triangle+'v_tc=vec2(.5);v_col=vec4(.25,.5,.75,1);v_gen0=v_gen1=vec4(.5,.5,0,1);}',s.GLES_FS_HEAD+s.GLES_FS_FLAT);
 uniform(p,'u_gamma',[1,1,1,1]);uniform(p,'u_flatColor',[.5,.5,.5,1]);uniform(p,'u_useVtx',[1]);texture(p,'u_tex0',0,[255,255,255,255]);texture(p,'u_tex1',1,[255,255,255,255]);
 pixel([32,64,96,255],'material tint multiplies vertex color');uniform(p,'u_inverseVtx',[1]);pixel([96,64,32,255],'inverse vertex RGB retains material tint');
 uniform(p,'u_useVtx',[0]);uniform(p,'u_flatColor',[-1,.125,2,1]);uniform(p,'u_gamma',[2,2,2,.5]);
 pixel([0,128,255,255],'ambient gamma clamps negative and overbright channels before square root');
 uniform(p,'u_flatColor',[.25,.5,.75,1]);uniform(p,'u_gamma',[1,1,1,2]);
 pixel([16,64,143,255],'ambient gamma retains native power response below saturation');
 // Fixed-function color is clamped: material "rgb 5" adds the texture once.
 uniform(p,'u_gamma',[1,1,1,1]);uniform(p,'u_useVtx',[0]);uniform(p,'u_flatColor',[5,5,5,1]);texture(p,'u_tex0',0,[64,128,192,255]);
 pixel([64,128,192,255],'overbright stage color saturates like the fixed-function current color');
 // Blend lights: projected texture (unit 0) and falloff (unit 1) both
 // MODULATE the current color, alpha included (RB_BlendLight).
 uniform(p,'u_gamma',[1,1,1,1]);uniform(p,'u_flatColor',[1,.5,1,.5]);uniform(p,'u_texgenMode',[2]);uniform(p,'u_secondTexgen',[1]);
 texture(p,'u_tex0',0,[255,255,128,128]);texture(p,'u_tex1',1,[128,255,255,255]);
 pixel([128,128,128,64],'blend light modulates projected and falloff color and alpha');
 uniform(p,'u_secondTexgen',[0]);pixel([255,128,128,64],'projected stage without falloff keeps texture alpha');
 uniform(p,'u_texgenMode',[0]);
 p=program(s.GLES_VS_HEAD+s.GLES_VS_ENV,s.GLES_FS_HEAD+s.GLES_FS_ENV);
 gl.uniformMatrix4fv(gl.getUniformLocation(p,'u_mvp'),false,new Float32Array([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]));
 uniform(p,'u_eyeLocal',[0,0,100,1]);uniform(p,'u_gamma',[1,1,1,1]);uniform(p,'u_useVtx',[1]);
 // At the center pixel the interpolated normal is (0.5,0,0.5).
 // Per-fragment reflection samples +X; the old vertex-reflection path
 // samples -X. Distinct cube faces expose the difference directly.
 const mesh=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,mesh);
 gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,0,0,0,1, 3,-1,0,1,0,0, -1,3,0,1,0,0]),gl.STATIC_DRAW);
 gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,3,gl.FLOAT,false,24,0);
 gl.enableVertexAttribArray(3);gl.vertexAttribPointer(3,3,gl.FLOAT,false,24,12);
 gl.vertexAttrib4f(2,.5,1,1,.5);gl.activeTexture(gl.TEXTURE0);
 const cube=gl.createTexture();gl.bindTexture(gl.TEXTURE_CUBE_MAP,cube);
 gl.texParameteri(gl.TEXTURE_CUBE_MAP,gl.TEXTURE_MIN_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_CUBE_MAP,gl.TEXTURE_MAG_FILTER,gl.NEAREST);
 const faces=[[255,0,0,128],[0,255,0,255],[0,0,255,255],[255,255,0,255],[255,0,255,255],[0,255,255,255]];
 for(let i=0;i<6;i++)gl.texImage2D(gl.TEXTURE_CUBE_MAP_POSITIVE_X+i,0,gl.RGBA8,1,1,0,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array(faces[i]));
 gl.uniform1i(gl.getUniformLocation(p,'u_cube'),0);
 pixel([128,0,0,64],'reflection uses interpolated normal per pixel and retains cube alpha');
 uniform(p,'u_alphaTest',[1,.3,516]);pixel([0,0,0,0],'reflection alpha test uses texture times vertex alpha');
 uniform(p,'u_alphaTest',[0,0,0]);uniform(p,'u_useVtx',[0]);uniform(p,'u_flatColor',[.7,.9,.9,1]);
 gl.vertexAttrib4f(2,0,0,0,1);
 pixel([179,0,0,128],'reflection uses material current color when vertex colors are disabled');
 uniform(p,'u_flatColor',[.7,.9,.9,.5]);uniform(p,'u_alphaTest',[1,.3,516]);
 pixel([0,0,0,0],'reflection current color alpha participates in alpha testing');
 uniform(p,'u_alphaTest',[0,0,0]);uniform(p,'u_useVtx',[1]);gl.vertexAttrib4f(2,.5,1,1,.5);
 pixel([128,0,0,64],'reflection color arrays take over current color without double tinting');
 gl.disableVertexAttribArray(0);gl.disableVertexAttribArray(3);gl.bindBuffer(gl.ARRAY_BUFFER,null);gl.deleteBuffer(mesh);
 p=program('#version 300 es\nprecision highp float;out vec3 v_posL,v_nrmL,v_t0L,v_t1L;out vec2 v_bumpTC;out vec4 v_col;uniform vec3 testNormal;void main(){'+triangle+'v_posL=vec3(0);v_nrmL=testNormal;v_t0L=vec3(1,0,0);v_t1L=vec3(0,1,0);v_bumpTC=vec2(.5);v_col=vec4(.05,.01,.7,.5);}',s.GLES_FS_HEAD+s.GLES_FS_BUMPYENV);
 uniform(p,'u_eyeLocal',[0,0,100,1]);uniform(p,'u_gamma',[1,1,1,1]);
 uniform(p,'u_modelR0',[1,0,0,0]);uniform(p,'u_modelR1',[0,1,0,0]);uniform(p,'u_modelR2',[0,0,1,0]);
 gl.uniform1i(gl.getUniformLocation(p,'u_cube'),0);texture(p,'u_bump',1,[0,128,255,128]);
 uniform(p,'testNormal',[.2,0,.6]);
 // Stock ARB reflection uses the interpolated basis as-is: its vector
 // is dominated by -Z. Renormalizing that basis incorrectly selects +Z.
 pixel([0,255,255,128],'bumpy reflection preserves native interpolated tangent-basis length');
 uniform(p,'testNormal',[0,0,1]);pixel([255,0,255,128],'bumpy reflection samples cube RGB without multiplying vertex tint');
 uniform(p,'u_modelR0',[0,0,1,0]);uniform(p,'u_modelR2',[-1,0,0,0]);
 pixel([255,0,0,128],'bumpy reflection transforms eye and tangent basis with model rows');
 uniform(p,'u_modelR0',[1,0,0,0]);uniform(p,'u_modelR2',[0,0,1,0]);texture(p,'u_bump',1,[0,128,128,255]);
 pixel([0,255,255,128],'bumpy reflection reads normal X from RXGB alpha');
 p=program('#version 300 es\nvoid main(){'+triangle+'}',s.GLES_FS_HEAD+s.GLES_FS_COLORPROCESS);
 uniform(p,'u_gamma',[1,1,1,1]);uniform(p,'u_screenRecip',[1,1,0,0]);uniform(p,'u_screenScale',[1,1,0,0]);
 uniform(p,'u_colorTarget',[1,.5,.25,1]);texture(p,'u_screen',0,[64,128,192,255]);
 uniform(p,'u_colorFraction',[0,0,0,0]);pixel([64,128,192,255],'color process zero fraction preserves captured screen');
 uniform(p,'u_colorFraction',[.5,.5,.5,.5]);pixel([95,96,112,255],'color process blends toward tinted 0.33 mean intensity');
 uniform(p,'u_colorFraction',[0,1,.5,1]);pixel([64,63,112,255],'color process retains independent RGB fraction parameters');
 uniform(p,'u_colorTarget',[1,1,1,1]);uniform(p,'u_colorFraction',[1,1,1,1]);pixel([127,127,127,255],'color process full fraction produces native greyscale');
 gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA8,2,2,0,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array([32,64,96,255, 255,0,0,255, 0,255,0,255, 0,0,255,255]));
 uniform(p,'u_colorFraction',[0,0,0,0]);uniform(p,'u_screenRecip',[1,1,0,0]);uniform(p,'u_screenScale',[.5,.5,0,0]);
 pixel([32,64,96,255],'color process samples screen using padded render texture scale');
 // Actual heat vertex shader: stock ARB DP4 broadcasts projection row 0,
 // divides by max(projected W,1), caps only the upper side at .02, then
 // applies the stage's signed deformation. Transform feedback avoids
 // clipping these deliberately far-away test points.
 p=program(s.GLES_VS_HEAD+s.GLES_VS_HEAT,s.GLES_FS_HEAD+s.GLES_FS_HEAT,['v_deform','v_scroll','v_tc','v_col']);
 const identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
 const projection=[1.5,0,0,0,0,2,0,0,0,0,-1,-1,0,0,-2,0];
 gl.uniformMatrix4fv(gl.getUniformLocation(p,'u_mvp'),false,new Float32Array(identity));
 gl.uniformMatrix4fv(gl.getUniformLocation(p,'u_mv'),false,new Float32Array(identity));
 gl.uniformMatrix4fv(gl.getUniformLocation(p,'u_proj'),false,new Float32Array(projection));
 uniform(p,'u_scroll',[.3,-.4,0,0]);uniform(p,'u_deform',[2,-3,0,0]);
 gl.vertexAttrib3f(1,.2,.8,0);gl.vertexAttrib4f(2,.1,.2,.3,.4);
 const heatFeedback=gl.createBuffer();gl.bindBuffer(gl.TRANSFORM_FEEDBACK_BUFFER,heatFeedback);
 gl.bufferData(gl.TRANSFORM_FEEDBACK_BUFFER,40,gl.STREAM_READ);gl.bindBufferBase(gl.TRANSFORM_FEEDBACK_BUFFER,0,heatFeedback);
 function heatVertex(z,expected,label){
  gl.vertexAttrib4f(0,1,2,z,1);gl.enable(gl.RASTERIZER_DISCARD);gl.beginTransformFeedback(gl.POINTS);
  gl.drawArrays(gl.POINTS,0,1);gl.endTransformFeedback();gl.disable(gl.RASTERIZER_DISCARD);
  const got=new Float32Array(10);gl.getBufferSubData(gl.TRANSFORM_FEEDBACK_BUFFER,0,got);
  assert(got.every((v,i)=>Math.abs(v-[...expected,.5,.4,.2,.8,.1,.2,.3,.4][i])<.00001),label+' ['+[...got]+']');
 }
 heatVertex(-100,[.03,-.045],'heat deformation decreases with view-space distance');
 heatVertex(-10,[.04,-.06],'near heat deformation retains the native .02 upper cap');
 heatVertex(2,[.04,-.06],'heat projection protects reciprocal W below one');
 projection[0]=-1.5;gl.uniformMatrix4fv(gl.getUniformLocation(p,'u_proj'),false,new Float32Array(projection));
 heatVertex(-10,[-.3,.45],'heat projection preserves negative deformation without a lower clamp');
 projection[0]=1.5;gl.uniformMatrix4fv(gl.getUniformLocation(p,'u_proj'),false,new Float32Array(projection));
 const moved=identity.slice();moved[14]=-100;gl.uniformMatrix4fv(gl.getUniformLocation(p,'u_mv'),false,new Float32Array(moved));
 heatVertex(0,[.03,-.045],'heat distance is computed after model-view transformation');
 gl.bindBufferBase(gl.TRANSFORM_FEEDBACK_BUFFER,0,null);gl.bindBuffer(gl.TRANSFORM_FEEDBACK_BUFFER,null);gl.deleteBuffer(heatFeedback);
 p=program('#version 300 es\nprecision highp float;out vec2 v_tc,v_scroll,v_deform;out vec4 v_col;uniform vec2 testDeform;uniform vec4 testColor;void main(){'+triangle+'v_tc=v_scroll=vec2(.5);v_deform=testDeform;v_col=testColor;}',s.GLES_FS_HEAD+s.GLES_FS_HEAT);
 uniform(p,'u_screenScale',[1,1,0,1]);uniform(p,'u_screenRecip',[1,1,0,1]);uniform(p,'testDeform',[.2,.2]);uniform(p,'testColor',[.5,.5,.5,.5]);
 texture(p,'u_screen',0,[0,0,0,255]);
 const heatScreen=[];for(let y=0;y<8;y++)for(let x=0;x<8;x++)heatScreen.push(x*32,y*32,128,255);
 gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA8,8,8,0,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array(heatScreen));
 texture(p,'u_normal',1,[0,0,128,255]);texture(p,'u_mask',2,[128,255,0,0]);
 gl.uniform1i(gl.getUniformLocation(p,'u_mode'),1);
 pixel([160,64,128,255],'unmasked heat offset reads normal X from RXGB alpha and Y from green');
 gl.uniform1i(gl.getUniformLocation(p,'u_mode'),2);
 pixel([128,64,128,255],'masked heat subtracts .01 from sampled RG before displacement');
 gl.uniform1i(gl.getUniformLocation(p,'u_mode'),3);
 pixel([128,96,128,255],'vertex-masked heat multiplies vertex RG before the cutoff subtraction');
 uniform(p,'testColor',[0,.5,1,1]);pixel([0,0,0,0],'zero vertex red kills vertex-masked heat');
 uniform(p,'testColor',[.5,0,1,1]);pixel([0,0,0,0],'zero vertex green independently kills vertex-masked heat');
 gl.uniform1i(gl.getUniformLocation(p,'u_mode'),2);
 pixel([128,64,128,255],'mask-only heat ignores vertex-color attenuation');
 texture(p,'u_mask',2,[0,255,255,255]);pixel([0,0,0,0],'mask red below .01 discards heat');
 texture(p,'u_mask',2,[255,0,255,255]);pixel([0,0,0,0],'mask green below .01 discards heat');
 gl.uniform1i(gl.getUniformLocation(p,'u_mode'),1);uniform(p,'testColor',[0,0,0,0]);
 pixel([160,64,128,255],'plain heat ignores both vertex tint and an empty mask');
 uniform(p,'u_screenScale',[.5,.75,0,1]);pixel([64,32,128,255],'heat includes independent padded screen texture scales');
 uniform(p,'u_screenScale',[.5,.5,0,1]);uniform(p,'testDeform',[2,2]);
 pixel([128,0,128,255],'heat saturates warped screen coordinates before applying texture padding');
 uniform(p,'u_screenScale',[1,1,0,1]);uniform(p,'testDeform',[0,0]);uniform(p,'u_screenRecip',[.5,.25,0,1]);
 pixel([64,32,128,255],'heat converts fragment pixels using independent viewport reciprocals');
 assert(gl.getError()===gl.NO_ERROR,'no WebGL errors');report.textContent=count+' checks passed\n'+lines.join('\n');
}catch(e){report.textContent='FAILED: '+e.message+'\n'+lines.join('\n');}
</script>'''
Path(sys.argv[1]).write_text(page.replace('SHADERS', json.dumps(shaders)).replace('STENCIL_OPS', json.dumps(stencil_ops)), encoding='utf-8')
print(f'Wrote {sys.argv[1]} ({len(shaders)} shader sources)')
