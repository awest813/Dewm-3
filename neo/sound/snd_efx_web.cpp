/*
EFX entry points for the web build.

Emscripten's OpenAL has no EFX, and its alGetProcAddress only returns the
functions it implements. web/openal_efx.js adds effects, filters, effect slots
and source sends to Emscripten's AL object (with an AudioWorklet port of
OpenAL Soft's reverb) and reports ALC_EXT_EFX; these functions forward to it.
*/
#ifdef __EMSCRIPTEN__

#include <string.h>
#include <emscripten.h>
#include <AL/al.h>
#include <AL/alc.h>

#include "sound/openal_web_compat.h"

// kind: 0 effect, 1 filter, 2 auxiliary effect slot (AL.efx in openal_efx.js)
EM_JS( void, WebEfx_Gen, ( int kind, ALsizei n, ALuint *ids ), {
	if ( n < 0 ) { if ( AL.currentCtx ) AL.currentCtx.err = 0xA003; return; }
	for ( var i = 0; i < n; i++ ) HEAPU32[( ids >> 2 ) + i] = AL.efx.gen( kind );
} );

EM_JS( void, WebEfx_Delete, ( int kind, ALsizei n, const ALuint *ids ), {
	if ( n < 0 ) { if ( AL.currentCtx ) AL.currentCtx.err = 0xA003; return; }
	var list = [];
	for ( var i = 0; i < n; i++ ) list.push( HEAPU32[( ids >> 2 ) + i] );
	AL.efx.remove( kind, list );
} );

EM_JS( int, WebEfx_Is, ( int kind, ALuint id ), {
	return AL.efx.is( kind, id ) ? 1 : 0;
} );

EM_JS( void, WebEfx_Set, ( int kind, ALuint id, ALenum param, int isInt, double value ), {
	AL.efx.set( kind, id, param, !!isInt, value );
} );

EM_JS( void, WebEfx_Setv, ( int kind, ALuint id, ALenum param, const ALfloat *values ), {
	var p = values >> 2;
	AL.efx.set( kind, id, param, false, [HEAPF32[p], HEAPF32[p + 1], HEAPF32[p + 2]] );
} );

EM_JS( void, WebEfx_SourceDirectFilter, ( ALuint source, ALint filter ), {
	AL.efx.sourceDirectFilter( source, filter );
} );

EM_JS( void, WebEfx_SourceSend, ( ALuint source, ALint slot, ALint send, ALint filter ), {
	AL.efx.sourceSend( source, slot, send, filter );
} );

static void AL_APIENTRY WebEfx_GenEffects( ALsizei n, ALuint *ids ) { WebEfx_Gen( 0, n, ids ); }
static void AL_APIENTRY WebEfx_DeleteEffects( ALsizei n, const ALuint *ids ) { WebEfx_Delete( 0, n, ids ); }
static ALboolean AL_APIENTRY WebEfx_IsEffect( ALuint id ) { return WebEfx_Is( 0, id ) ? AL_TRUE : AL_FALSE; }
static void AL_APIENTRY WebEfx_Effecti( ALuint id, ALenum param, ALint value ) { WebEfx_Set( 0, id, param, 1, value ); }
static void AL_APIENTRY WebEfx_Effectf( ALuint id, ALenum param, ALfloat value ) { WebEfx_Set( 0, id, param, 0, value ); }
static void AL_APIENTRY WebEfx_Effectfv( ALuint id, ALenum param, const ALfloat *values ) { WebEfx_Setv( 0, id, param, values ); }
static void AL_APIENTRY WebEfx_GenFilters( ALsizei n, ALuint *ids ) { WebEfx_Gen( 1, n, ids ); }
static void AL_APIENTRY WebEfx_DeleteFilters( ALsizei n, const ALuint *ids ) { WebEfx_Delete( 1, n, ids ); }
static ALboolean AL_APIENTRY WebEfx_IsFilter( ALuint id ) { return WebEfx_Is( 1, id ) ? AL_TRUE : AL_FALSE; }
static void AL_APIENTRY WebEfx_Filteri( ALuint id, ALenum param, ALint value ) { WebEfx_Set( 1, id, param, 1, value ); }
static void AL_APIENTRY WebEfx_Filterf( ALuint id, ALenum param, ALfloat value ) { WebEfx_Set( 1, id, param, 0, value ); }
static void AL_APIENTRY WebEfx_GenAuxiliaryEffectSlots( ALsizei n, ALuint *ids ) { WebEfx_Gen( 2, n, ids ); }
static void AL_APIENTRY WebEfx_DeleteAuxiliaryEffectSlots( ALsizei n, const ALuint *ids ) { WebEfx_Delete( 2, n, ids ); }
static ALboolean AL_APIENTRY WebEfx_IsAuxiliaryEffectSlot( ALuint id ) { return WebEfx_Is( 2, id ) ? AL_TRUE : AL_FALSE; }
static void AL_APIENTRY WebEfx_AuxiliaryEffectSloti( ALuint id, ALenum param, ALint value ) { WebEfx_Set( 2, id, param, 1, value ); }
static void AL_APIENTRY WebEfx_AuxiliaryEffectSlotf( ALuint id, ALenum param, ALfloat value ) { WebEfx_Set( 2, id, param, 0, value ); }

static const struct {
	const char *name;
	void *func;
} webEfxFuncs[] = {
	{ "alGenEffects", (void *)WebEfx_GenEffects },
	{ "alDeleteEffects", (void *)WebEfx_DeleteEffects },
	{ "alIsEffect", (void *)WebEfx_IsEffect },
	{ "alEffecti", (void *)WebEfx_Effecti },
	{ "alEffectf", (void *)WebEfx_Effectf },
	{ "alEffectfv", (void *)WebEfx_Effectfv },
	{ "alGenFilters", (void *)WebEfx_GenFilters },
	{ "alDeleteFilters", (void *)WebEfx_DeleteFilters },
	{ "alIsFilter", (void *)WebEfx_IsFilter },
	{ "alFilteri", (void *)WebEfx_Filteri },
	{ "alFilterf", (void *)WebEfx_Filterf },
	{ "alGenAuxiliaryEffectSlots", (void *)WebEfx_GenAuxiliaryEffectSlots },
	{ "alDeleteAuxiliaryEffectSlots", (void *)WebEfx_DeleteAuxiliaryEffectSlots },
	{ "alIsAuxiliaryEffectSlot", (void *)WebEfx_IsAuxiliaryEffectSlot },
	{ "alAuxiliaryEffectSloti", (void *)WebEfx_AuxiliaryEffectSloti },
	{ "alAuxiliaryEffectSlotf", (void *)WebEfx_AuxiliaryEffectSlotf },
};

void *WebEfx_GetProcAddress( const ALchar *name ) {
	for ( size_t i = 0; i < sizeof( webEfxFuncs ) / sizeof( webEfxFuncs[0] ); i++ ) {
		if ( !strcmp( name, webEfxFuncs[i].name ) ) {
			return webEfxFuncs[i].func;
		}
	}
	return alGetProcAddress( name );
}

// Emscripten's alSourcei/alSource3i reject the EFX source parameters.
void WebEfx_Sourcei( ALuint source, ALenum param, ALint value ) {
	if ( param == AL_DIRECT_FILTER ) {
		WebEfx_SourceDirectFilter( source, value );
	} else {
		alSourcei( source, param, value );
	}
}

void WebEfx_Source3i( ALuint source, ALenum param, ALint value1, ALint value2, ALint value3 ) {
	if ( param == AL_AUXILIARY_SEND_FILTER ) {
		WebEfx_SourceSend( source, value1, value2, value3 );
	} else {
		alSource3i( source, param, value1, value2, value3 );
	}
}

#endif
