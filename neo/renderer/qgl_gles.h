/*
 * qgl_gles.h — WebGL2 / OpenGL ES 3.0 compatibility for the dhewm3 web port.
 *
 * Included from renderer/qgl.h when __EMSCRIPTEN__ is defined. It provides:
 *  - GLES3 headers instead of desktop GL
 *  - desktop-only enum tokens used across the renderer (compile-time only;
 *    the calls that use them are no-ops on the GLES path — see tr_gles.cpp)
 *  - ARB-suffixed proc typedefs mapped onto core GLES3 signatures
 *  - R_GLES_* entry points implemented in renderer/tr_gles.cpp
 *
 * Status: experimental material shaders are implemented; browser visual and
 * gameplay validation is pending. See docs/WEB.md for remaining milestones.
 */

#ifndef __QGL_GLES_H__
#define __QGL_GLES_H__

#include <GLES3/gl3.h>
#ifndef APIENTRY
#define APIENTRY GL_APIENTRY
#endif
#ifndef APIENTRYP
#define APIENTRYP GL_APIENTRYP
#endif

#ifndef GL_TEXTURE_BORDER_COLOR
#define GL_TEXTURE_BORDER_COLOR 0x1004
#endif
#ifndef GL_SHARED_TEXTURE_PALETTE_EXT
#define GL_SHARED_TEXTURE_PALETTE_EXT 0x81FB
#endif
#ifndef GL_TEXTURE_CUBE_MAP_EXT
#define GL_TEXTURE_CUBE_MAP_EXT GL_TEXTURE_CUBE_MAP
#endif
#ifndef GL_COLOR_INDEX8_EXT
#define GL_COLOR_INDEX8_EXT 0x80E5
#endif
#ifndef GL_CLAMP_TO_BORDER
#define GL_CLAMP_TO_BORDER 0x812D
#endif
#ifndef GL_STACK_OVERFLOW
#define GL_STACK_OVERFLOW 0x0503
#define GL_STACK_UNDERFLOW 0x0504
#endif
#ifndef GL_STENCIL_INDEX
#define GL_STENCIL_INDEX 0x1901
#endif

// Additional legacy tokens referenced by desktop renderer paths.
// These declarations do not enable the corresponding WebGL features.
#ifndef GL_ADD
#define GL_ADD 0x0104
#endif
#ifndef GL_ALL_ATTRIB_BITS
#define GL_ALL_ATTRIB_BITS 0x000FFFFF
#endif
#ifndef GL_ALPHA8
#define GL_ALPHA8 0x803C
#endif
#ifndef GL_COLOR_INDEX
#define GL_COLOR_INDEX 0x1900
#endif
#ifndef GL_COMBINE_EXT
#define GL_COMBINE_EXT 0x8570
#endif
#ifndef GL_FILL
#define GL_FILL 0x1B02
#endif
#ifndef GL_LIGHTING
#define GL_LIGHTING 0x0B50
#endif
#ifndef GL_LINE
#define GL_LINE 0x1B01
#endif
#ifndef GL_LINE_STIPPLE
#define GL_LINE_STIPPLE 0x0B24
#endif
#ifndef GL_MODELVIEW
#define GL_MODELVIEW 0x1700
#endif
#ifndef GL_POLYGON_OFFSET_LINE
#define GL_POLYGON_OFFSET_LINE 0x2A02
#endif
#ifndef GL_PROJECTION
#define GL_PROJECTION 0x1701
#endif
#ifndef GL_RGB5
#define GL_RGB5 0x8050
#endif
#ifndef GL_SMOOTH
#define GL_SMOOTH 0x1D01
#endif
#ifndef GL_TEXTURE_CUBE_MAP_POSITIVE_X_EXT
#define GL_TEXTURE_CUBE_MAP_POSITIVE_X_EXT 0x8515
#endif
#ifndef GL_TEXTURE_SWIZZLE_RGBA
#define GL_TEXTURE_SWIZZLE_RGBA 0x8E46
#endif

// Desktop-only scalar types used by qgl_proc.h declarations (never
// instantiated meaningfully on GLES; stubs only).
#ifndef GLdouble
typedef double GLdouble;
typedef double GLclampd;
#endif

// ---------------------------------------------------------------------------
// Desktop-only tokens referenced by the renderer. Defined here so translation
// units compile; the fixed-function call sites are stubbed at runtime.
// Values match the desktop GL enums (irrelevant on GLES, never consumed).
// ---------------------------------------------------------------------------
#ifndef GL_VERTEX_PROGRAM_ARB
#define GL_VERTEX_PROGRAM_ARB		0x8620
#endif
#ifndef GL_FRAGMENT_PROGRAM_ARB
#define GL_FRAGMENT_PROGRAM_ARB		0x8804
#endif
#ifndef GL_PROGRAM_FORMAT_ASCII_ARB
#define GL_PROGRAM_FORMAT_ASCII_ARB	0x8875
#endif

#ifndef GL_TEXTURE0_ARB
#define GL_TEXTURE0_ARB			GL_TEXTURE0
#define GL_TEXTURE1_ARB			GL_TEXTURE1
#define GL_TEXTURE2_ARB			GL_TEXTURE2
#define GL_TEXTURE3_ARB			GL_TEXTURE3
#define GL_TEXTURE4_ARB			GL_TEXTURE4
#define GL_TEXTURE5_ARB			GL_TEXTURE5
#define GL_TEXTURE6_ARB			GL_TEXTURE6
#define GL_TEXTURE7_ARB			GL_TEXTURE7
#endif

#ifndef GL_MAX_TEXTURE_UNITS_ARB
#define GL_MAX_TEXTURE_UNITS_ARB	GL_MAX_TEXTURE_IMAGE_UNITS
#endif
#ifndef GL_MAX_TEXTURE_COORDS_ARB
#define GL_MAX_TEXTURE_COORDS_ARB	GL_MAX_TEXTURE_IMAGE_UNITS
#endif
#ifndef GL_MAX_TEXTURE_IMAGE_UNITS_ARB
#define GL_MAX_TEXTURE_IMAGE_UNITS_ARB	GL_MAX_TEXTURE_IMAGE_UNITS
#endif

#ifndef GL_QUADS
#define GL_QUADS			0x0007
#endif
#ifndef GL_QUAD_STRIP
#define GL_QUAD_STRIP			0x0008
#endif
#ifndef GL_POLYGON
#define GL_POLYGON			0x0009
#endif

// ARB program error query tokens (desktop-only code still compiles them;
// the GLES path never executes those branches — see draw_arb2.cpp).
#ifndef GL_PROGRAM_ERROR_POSITION_ARB
#define GL_PROGRAM_ERROR_POSITION_ARB	0x864B
#define GL_PROGRAM_ERROR_STRING_ARB	0x8874
#endif

// Depth-bounds test (checked only when glConfig.depthBoundsTestAvailable,
// which is false on GLES — draw_common.cpp).
#ifndef GL_DEPTH_BOUNDS_TEST_EXT
#define GL_DEPTH_BOUNDS_TEST_EXT	0x8890
#endif

// S3TC / generic compression tokens (Image_load.cpp references; GLES config
// reports textureCompressionAvailable=false so they are never uploaded).
#ifndef GL_COMPRESSED_RGB_S3TC_DXT1_EXT
#define GL_COMPRESSED_RGB_S3TC_DXT1_EXT		0x83F0
#define GL_COMPRESSED_RGBA_S3TC_DXT1_EXT	0x83F1
#define GL_COMPRESSED_RGBA_S3TC_DXT3_EXT	0x83F2
#define GL_COMPRESSED_RGBA_S3TC_DXT5_EXT	0x83F3
#define GL_COMPRESSED_RGB_ARB			0x84ED
#define GL_COMPRESSED_RGBA_ARB			0x84EE
#endif

// Anisotropy / LOD bias (Image_init.cpp; anisotropy is extension-probed on GLES).
#ifndef GL_TEXTURE_MAX_ANISOTROPY_EXT
#define GL_TEXTURE_MAX_ANISOTROPY_EXT		0x84FE
#define GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT	0x84FF
#define GL_TEXTURE_LOD_BIAS_EXT			0x8501
#endif

// Stencil wrap (core INCR_WRAP exists in GLES3; _EXT aliases may not).
#ifndef GL_INCR_WRAP_EXT
#define GL_INCR_WRAP_EXT			GL_INCR_WRAP
#define GL_DECR_WRAP_EXT			GL_DECR_WRAP
#endif

// Debug output (desktop-only branch in RenderSystem_init.cpp still compiles).
#ifndef GL_DEBUG_OUTPUT_SYNCHRONOUS_ARB
#define GL_DEBUG_OUTPUT_SYNCHRONOUS_ARB		0x8242
#define GL_DEBUG_SEVERITY_HIGH_ARB		0x9146
#define GL_DEBUG_SEVERITY_MEDIUM_ARB		0x9147
#define GL_DEBUG_SEVERITY_LOW_ARB		0x9148
#define GL_DEBUG_SOURCE_API_ARB			0x8246
#define GL_DEBUG_SOURCE_WINDOW_SYSTEM_ARB	0x8247
#define GL_DEBUG_SOURCE_SHADER_COMPILER_ARB	0x8248
#define GL_DEBUG_SOURCE_THIRD_PARTY_ARB		0x8249
#define GL_DEBUG_SOURCE_APPLICATION_ARB		0x824A
#define GL_DEBUG_SOURCE_OTHER_ARB		0x824B
#define GL_DEBUG_TYPE_ERROR_ARB			0x824C
#define GL_DEBUG_TYPE_DEPRECATED_BEHAVIOR_ARB	0x824D
#define GL_DEBUG_TYPE_UNDEFINED_BEHAVIOR_ARB	0x824E
#define GL_DEBUG_TYPE_PORTABILITY_ARB		0x824F
#define GL_DEBUG_TYPE_PERFORMANCE_ARB		0x8250
#define GL_DEBUG_TYPE_OTHER_ARB			0x8251
#endif

// texture_env_combine/dot3 tokens used by draw_common.cpp TexEnv calls
// (those calls are runtime no-ops on GLES; tokens only need to exist).
#ifndef GL_COMBINE_ARB
#define GL_COMBINE_ARB			0x8570
#define GL_COMBINE_RGB_ARB		0x8571
#define GL_COMBINE_ALPHA_ARB		0x8572
#define GL_SOURCE0_RGB_ARB		0x8580
#define GL_SOURCE1_RGB_ARB		0x8581
#define GL_SOURCE2_RGB_ARB		0x8582
#define GL_SOURCE0_ALPHA_ARB		0x8588
#define GL_SOURCE1_ALPHA_ARB		0x8589
#define GL_SOURCE2_ALPHA_ARB		0x858A
#define GL_OPERAND0_RGB_ARB		0x8590
#define GL_OPERAND1_RGB_ARB		0x8591
#define GL_OPERAND2_RGB_ARB		0x8592
#define GL_OPERAND0_ALPHA_ARB		0x8598
#define GL_OPERAND1_ALPHA_ARB		0x8599
#define GL_OPERAND2_ALPHA_ARB		0x859A
#define GL_RGB_SCALE_ARB		0x8573
#define GL_ADD_SIGNED_ARB		0x8574
#define GL_INTERPOLATE_ARB		0x8575
#define GL_SUBTRACT_ARB			0x84E7
#define GL_DOT3_RGB_ARB			0x86AE
#define GL_DOT3_RGBA_ARB		0x86AF
#endif

// VBO tokens / types (VertexCache.cpp, sys_imgui.cpp). Values match core.
#ifndef GL_ARRAY_BUFFER_ARB
#define GL_ARRAY_BUFFER_ARB			GL_ARRAY_BUFFER
#define GL_ELEMENT_ARRAY_BUFFER_ARB		GL_ELEMENT_ARRAY_BUFFER
#define GL_STATIC_DRAW_ARB			GL_STATIC_DRAW
#define GL_DYNAMIC_DRAW_ARB			GL_DYNAMIC_DRAW
#define GL_STREAM_DRAW_ARB			GL_STREAM_DRAW
#define GL_WRITE_ONLY_ARB			GL_MAP_WRITE_BIT
#define GL_READ_ONLY_ARB			0x88B8
#define GL_READ_WRITE_ARB			0x88BA
typedef GLsizeiptr GLsizeiptrARB;
typedef GLintptr GLintptrARB;
#endif

// Texgen tokens (removed in GLES3; emulated in tr_gles.cpp for fog, blend
// lights and projected/screen textures).
#ifndef GL_TEXTURE_GEN_S
#define GL_TEXTURE_GEN_S			0x0C60
#define GL_TEXTURE_GEN_T			0x0C61
#define GL_TEXTURE_GEN_R			0x0C62
#define GL_TEXTURE_GEN_Q			0x0C63
#define GL_S					0x2000
#define GL_T					0x2001
#define GL_R					0x2002
#define GL_Q					0x2003
#define GL_OBJECT_PLANE				0x2501
#define GL_EYE_PLANE				0x2502
#define GL_OBJECT_LINEAR			0x2401
#define GL_TEXTURE_GEN_MODE			0x2500
#define GL_REFLECTION_MAP_EXT			0x8512
#endif

// Texture-environment tokens (fixed-function combine; calls are no-ops on
// GLES — old-style stages render through the flat GLSL program instead).
#ifndef GL_TEXTURE_ENV
#define GL_TEXTURE_ENV				0x2300
#define GL_TEXTURE_ENV_MODE			0x2200
#define GL_TEXTURE_ENV_COLOR			0x2201
#define GL_MODULATE				0x2100
#define GL_DECAL				0x2101
#define GL_REPLACE				0x1E01
#define GL_PREVIOUS_ARB				0x8578
#define GL_CONSTANT_ARB				0x8579
#define GL_PRIMARY_COLOR_ARB			0x8577
#define GL_ALPHA_SCALE				0x0D1C
#endif

// Legacy client-state array tokens (removed in GLES3; the calls are
// reimplemented as vertex-attrib setup in tr_gles.cpp).
#ifndef GL_VERTEX_ARRAY
#define GL_VERTEX_ARRAY				0x8074
#define GL_NORMAL_ARRAY				0x8075
#define GL_COLOR_ARRAY				0x8076
#define GL_TEXTURE_COORD_ARRAY			0x8078
#endif

// Legacy internal-format / pixel-path tokens (Image_load.cpp, tr_font.cpp,
// tr_rendertools.cpp). Compile-time only on GLES — the upload paths need
// sized internal formats (GL_R8/GL_RGBA8/...) in phase 4; until then texture
// uploads may GL-error and yield placeholder/procedural content.
#ifndef GL_ALPHA_TEST
#define GL_ALPHA_TEST				0x0BC0
#define GL_CLAMP				0x2900
#define GL_INTENSITY8				0x804B
#define GL_LUMINANCE8				0x8040
#define GL_LUMINANCE8_ALPHA8			0x8045
#define GL_LUMINANCE				0x1909
#define GL_LUMINANCE_ALPHA			0x190A
#define GL_BGR_EXT				0x80E0
#define GL_BGRA_EXT				0x80E1
#define GL_TEXTURE_RECTANGLE_NV			0x84F5
#define GL_TEXTURE_RECTANGLE_ARB		0x84F5
#define GL_DEPTH_COMPONENT24_ARB		0x81A6
#endif

// ---------------------------------------------------------------------------
// ARB-suffixed proc typedefs. qgl.h declares the qgl* function pointers with
// these types; on GLES they alias the identical core signatures (or are
// defined explicitly when no core equivalent exists).
// ---------------------------------------------------------------------------
#ifndef PFNGLBINDBUFFERARBPROC
typedef void (APIENTRYP PFNGLBINDBUFFERARBPROC) (GLenum target, GLuint buffer);
typedef void (APIENTRYP PFNGLDELETEBUFFERSARBPROC) (GLsizei n, const GLuint *buffers);
typedef void (APIENTRYP PFNGLGENBUFFERSARBPROC) (GLsizei n, GLuint *buffers);
typedef GLboolean (APIENTRYP PFNGLISBUFFERARBPROC) (GLuint buffer);
typedef void (APIENTRYP PFNGLBUFFERDATAARBPROC) (GLenum target, GLsizeiptr size, const GLvoid *data, GLenum usage);
typedef void (APIENTRYP PFNGLBUFFERSUBDATAARBPROC) (GLenum target, GLintptr offset, GLsizeiptr size, const GLvoid *data);
typedef void (APIENTRYP PFNGLGETBUFFERSUBDATAARBPROC) (GLenum target, GLintptr offset, GLsizeiptr size, GLvoid *data);
typedef GLvoid* (APIENTRYP PFNGLMAPBUFFERARBPROC) (GLenum target, GLenum access);
typedef GLboolean (APIENTRYP PFNGLUNMAPBUFFERARBPROC) (GLenum target);
typedef void (APIENTRYP PFNGLGETBUFFERPARAMETERIVARBPROC) (GLenum target, GLenum pname, GLint *params);
typedef void (APIENTRYP PFNGLGETBUFFERPOINTERVARBPROC) (GLenum target, GLenum pname, GLvoid* *params);
#endif

#ifndef PFNGLACTIVESTENCILFACEEXTPROC
typedef void (APIENTRYP PFNGLACTIVESTENCILFACEEXTPROC) (GLenum face);
#endif

#ifndef PFNGLSTENCILOPSEPARATEPROC
typedef void (APIENTRYP PFNGLSTENCILOPSEPARATEPROC) (GLenum face, GLenum sfail, GLenum dpfail, GLenum dppass);
#endif

#ifndef PFNGLCOMPRESSEDTEXIMAGE2DARBPROC
typedef void (APIENTRYP PFNGLCOMPRESSEDTEXIMAGE2DARBPROC) (GLenum target, GLint level, GLenum internalformat, GLsizei width, GLsizei height, GLint border, GLsizei imageSize, const GLvoid *data);
typedef void (APIENTRYP PFNGLGETCOMPRESSEDTEXIMAGEARBPROC) (GLenum target, GLint level, GLvoid *img);
#endif

#ifndef PFNGLVERTEXATTRIBPOINTERARBPROC
typedef void (APIENTRYP PFNGLVERTEXATTRIBPOINTERARBPROC) (GLuint index, GLint size, GLenum type, GLboolean normalized, GLsizei stride, const GLvoid *pointer);
typedef void (APIENTRYP PFNGLENABLEVERTEXATTRIBARRAYARBPROC) (GLuint index);
typedef void (APIENTRYP PFNGLDISABLEVERTEXATTRIBARRAYARBPROC) (GLuint index);
typedef void (APIENTRYP PFNGLPROGRAMSTRINGARBPROC) (GLenum target, GLenum format, GLsizei len, const GLvoid *string);
typedef void (APIENTRYP PFNGLBINDPROGRAMARBPROC) (GLenum target, GLuint program);
typedef void (APIENTRYP PFNGLGENPROGRAMSARBPROC) (GLsizei n, GLuint *programs);
typedef void (APIENTRYP PFNGLPROGRAMENVPARAMETER4FVARBPROC) (GLenum target, GLuint index, const GLfloat *params);
typedef void (APIENTRYP PFNGLPROGRAMLOCALPARAMETER4FVARBPROC) (GLenum target, GLuint index, const GLfloat *params);
#endif

#ifndef PFNGLDEPTHBOUNDSEXTPROC
typedef void (APIENTRYP PFNGLDEPTHBOUNDSEXTPROC) (GLclampd zmin, GLclampd zmax);
#endif

#ifndef PFNGLDEBUGMESSAGECALLBACKARBPROC
typedef void (APIENTRY *GLDEBUGPROCARB)(GLenum source, GLenum type, GLuint id, GLenum severity, GLsizei length, const GLchar *message, const GLvoid *userParam);
typedef void (APIENTRYP PFNGLDEBUGMESSAGECALLBACKARBPROC) (GLDEBUGPROCARB callback, const GLvoid *userParam);
#endif

#ifdef __cplusplus
extern "C" {
#endif

// Implemented in renderer/tr_gles.cpp (linked only for EMSCRIPTEN builds).
// R_GLES_LoadFunctions: resolves every qgl* pointer — real GLES3 functions
//   where they exist, in-file no-op stubs otherwise. Never FatalErrors.
// R_GLES_InitConfig: fills glConfig with WebGL2-safe values and forces
//   client-array (non-VBO) vertex submission for phase 3a.
void R_GLES_LoadFunctions( void );
void R_GLES_InitConfig( void );
// Ensures the shared passthrough GLSL-ES program exists and returns it.
// Called from R_LoadARBProgram on the GLES path (one program stands in for
// all ARB assembly programs until phase 4 ports them one by one).
unsigned int R_GLES_NoteProgram( const char *name, int ident = 0 );
// Marks draws belonging to RB_ARB2_CreateDrawInteractions (draw_arb2.cpp
// calls with 1 on entry, 0 on exit). Lets draw-time sync tell genuine
// interaction draws apart from later fixed-path draws reusing a stale
// interaction program binding.
void R_GLES_MarkInteraction( int on );
void R_GLES_SetStageColor( const float *color, int vertexColor );
void R_GLES_PerfFrame( double cpuMs );
void R_GLES_DumpDrawSurfs( const struct viewDef_s *view );
void R_GLES_SetShadowMode( bool sharedVertices );
// Deletes and re-links all GLSL programs (web equivalent of the desktop
// reloadARBprograms console command, whose .vfp files don't exist on GLES).
void R_GLES_ReloadPrograms( void );

#ifdef __cplusplus
}
#endif

#endif // __QGL_GLES_H__
