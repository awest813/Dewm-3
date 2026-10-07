/*
===========================================================================

Web libm overrides: the float sine and cosine that MSVC's UCRT computes.

Emscripten links musl, whose sinf/cosf round differently from the native
Windows build in about 0.2% of inputs. Game code feeds those results into
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

}

#endif
