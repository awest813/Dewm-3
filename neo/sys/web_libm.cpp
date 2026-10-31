/*
===========================================================================

Web libm overrides: the float sinf, cosf, tanf, asinf, acosf, atanf, atan2f,
expf and logf that MSVC's UCRT computes.

Emscripten links musl, whose float functions round differently from the native
Windows build (sinf/cosf in about 0.2% of inputs, tanf and atan2f in over 10%). Game code feeds those results into
animation, AI aim and random draws, so a one-ulp difference can change which
random numbers an entity consumes and split web gameplay from native. These
definitions replace musl's symbols for the whole web executable; they must be
linked as an object file (not from an archive) so the linker never pulls
musl's versions. The ports live in idlib/math/WebMath.h and are checked by
tests/web_trig_check.py.

===========================================================================
*/

#ifdef __EMSCRIPTEN__

#include "sys/platform.h"
#include "idlib/math/WebMath.h"

extern "C" {

float sinf( float x ) {
	return WebSinf( x );
}

float cosf( float x ) {
	return WebCosf( x );
}

void sincosf( float x, float *s, float *c ) {
	*s = WebSinf( x );
	*c = WebCosf( x );
}

float tanf( float x ) {
	return WebTanf( x );
}

float asinf( float x ) {
	return WebAsinf( x );
}

float acosf( float x ) {
	return WebAcosf( x );
}

float atanf( float x ) {
	return WebAtanf( x );
}

float atan2f( float y, float x ) {
	return WebAtan2f( y, x );
}

float expf( float x ) {
	return WebExpf( x );
}

float logf( float x ) {
	return WebLogf( x );
}

// Double functions. sys/platform.h defines function-like macros with these
// names (native float-argument precision), so each name is parenthesized.
// LLVM may merge sin and cos calls into sincos, which therefore uses them too.
double (sin)( double x ) {
	return WebSin( x );
}

double (cos)( double x ) {
	return WebCos( x );
}

void sincos( double x, double *s, double *c ) {
	*s = WebSin( x );
	*c = WebCos( x );
}

double (tan)( double x ) {
	return WebTan( x );
}

double (atan)( double x ) {
	return WebAtan( x );
}

double (atan2)( double y, double x ) {
	return WebAtan2( y, x );
}

double (asin)( double x ) {
	return WebAsin( x );
}

double (acos)( double x ) {
	return WebAcos( x );
}

}

#endif
