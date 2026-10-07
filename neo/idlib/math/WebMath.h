#ifndef __WEBMATH_H__
#define __WEBMATH_H__

#include "Math.h"
#include <cstring>

/*******************************************************************************
MIT License
-----------

Copyright (c) 2002-2019 Advanced Micro Devices, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this Software and associated documentaon files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
*******************************************************************************/

// Adapted from AMD win-libm acosf.c, commit
// 6121d02aef0c775947d5dc655d7fc4ccfe2144ab (MIT license above).
// https://github.com/amd/win-libm/blob/6121d02aef0c775947d5dc655d7fc4ccfe2144ab/acosf.c
// Explicit fused operations reproduce the MSVC/UCRT FMA path. This is used
// only for web matrix rotations; native and shared idMath::ACos stay unchanged.
// Keep float intermediate rounding and the existing idMath endpoint clamps.
static ID_INLINE float WebRotationACos( float x )
{
  /* Some constants and split constants. */

  static const float
    piby2      = 1.5707963705e+00F; /* 0x3fc90fdb */
  static const double
    pi         = 3.1415926535897933e+00, /* 0x400921fb54442d18 */
    piby2_head = 1.5707963267948965580e+00, /* 0x3ff921fb54442d18 */
    piby2_tail = 6.12323399573676603587e-17; /* 0x3c91a62633145c07 */

  float u, y, s = 0.0F, r;
  int xexp, transform = 0;

  unsigned int ux, xneg;

  memcpy(&ux, &x, sizeof(ux));
  xneg = (ux & 0x80000000u);
  xexp = (int)((ux & 0x7f800000u) >> 23) - 127;

  if (x <= -1.0f) return idMath::PI;
  if (x >= 1.0f) return 0.0f;
  if (xexp < -26) return piby2;
  if (xneg) y = -x;
  else y = x;

  transform = (xexp >= -1); /* abs(x) >= 0.5 */

  if (transform)
    { /* Transform y into the range [0,0.5) */
      r = 0.5F*(1.0F - y);
      /* VC++ intrinsic call */
      s = sqrtf(r);
      y = s;
    }
  else
    r = y*y;

  /* Use a rational approximation for [0.0, 0.5] */

  u = r * fmaf(r,
      fmaf(r, fmaf(-0.00396137437848476485201154797087F, r,
                   -0.0133819288943925804214011424456F),
           -0.0565298683201845211985026327361F),
      0.184161606965100694821398249421F) /
      fmaf(-0.836411276854206731913362287293F, r,
           1.10496961524520294485512696706F);
  if (transform)
    {
      /* Reconstruct acos carefully in transformed region */
      if (xneg)
        return (float)(pi - 2.0*(s+(y*u - piby2_tail)));
      else
	{
	  float c, s1;
	  unsigned int us;
	  memcpy(&us, &s, sizeof(us));
	  us &= 0xffff0000u; memcpy(&s1, &us, sizeof(s1));
	  c = fmaf(-s1, s1, r)/(s+s1);
          return 2.0F*s1 + fmaf(2.0F*y, u, 2.0F*c);
	}
    }
  else
    return (float)(piby2_head - (x - (piby2_tail - x*u)));
}

// Adapted from AMD win-libm sinf.asm, cosf.asm and Lsincosf_array.asm at the
// same commit (MIT license above): the FMA3 code paths that MSVC's UCRT uses
// on processors with FMA. Every product, fused multiply-add and subtraction
// follows the assembly so results match UCRT bit for bit; musl's sinf/cosf
// differ in about 0.2% of inputs, enough to change native/web simulation.
// Arguments beyond the moderate reduction range (|x| >= 16779436 for sin,
// >= 3.37e9 for cos) use double-precision sin/cos instead of AMD's
// Payne-Hanek reduction; those results are not verified against UCRT.
static ID_INLINE double WebLibmDouble( unsigned long long bits ) {
	double d;
	memcpy( &d, &bits, sizeof( d ) );
	return d;
}

static ID_INLINE unsigned long long WebLibmBits( double d ) {
	unsigned long long bits;
	memcpy( &bits, &d, sizeof( bits ) );
	return bits;
}

// __Lsinfarray s1..s4 and __Lcosfarray c0..c4.
static ID_INLINE double WebLibmSinPoly( double x ) {
	const double x2 = x * x;
	double p = fma( x2, WebLibmDouble( 0x3ec71de3a556c734ull ), WebLibmDouble( 0xbf2a01a01a01a01aull ) );
	p = fma( p, x2, WebLibmDouble( 0x3f81111111111111ull ) );
	p = fma( p, x2, WebLibmDouble( 0xbfc5555555555555ull ) );
	return fma( p, x * x2, x );
}

static ID_INLINE double WebLibmCosTail( double x2 ) {
	double p = fma( x2, WebLibmDouble( 0xbe927e4fb7789f5cull ), WebLibmDouble( 0x3efa01a01a01a019ull ) );
	p = fma( p, x2, WebLibmDouble( 0xbf56c16c16c16c16ull ) );
	return fma( p, x2, WebLibmDouble( 0x3fa5555555555555ull ) );
}

// cosf.asm evaluates 1 - x^2/2 with a separate multiply and subtract.
static ID_INLINE double WebLibmCosPolyCosf( double x ) {
	const double x2 = x * x;
	const double c = 1.0 - x2 * 0.5;
	return fma( WebLibmCosTail( x2 ), x2 * x2, c );
}

// sinf.asm fuses 1 + c0 x^2 for odd quadrants.
static ID_INLINE double WebLibmCosPolySinf( double x ) {
	const double x2 = x * x;
	const double c = fma( x2, WebLibmDouble( 0xbfe0000000000000ull ), 1.0 );
	return fma( WebLibmCosTail( x2 ), x2 * x2, c );
}

// Moderate-range reduction shared by both FMA3 paths; ax = |x|.
static ID_INLINE double WebLibmReducePiBy2( double ax, int &region ) {
	const int n = (int)fma( WebLibmDouble( 0x3fe45f306dc9c883ull ), ax, 0.5 );	// truncating
	const double dn = (double)n;
	region = n & 3;
	const double rhead = fma( -dn, WebLibmDouble( 0x3ff921fb54400000ull ), ax );
	return rhead - dn * WebLibmDouble( 0x3dd0b4611a626331ull );
}

static ID_INLINE float WebSinf( float xf ) {
	unsigned int xbits;
	memcpy( &xbits, &xf, sizeof( xbits ) );
	if ( ( xbits & 0x7f800000u ) == 0x7f800000u ) {
		return xf - xf;
	}
	const double x = xf;
	const unsigned long long ax = WebLibmBits( x ) & 0x7fffffffffffffffull;
	if ( ax <= 0x3fe921fb54442d18ull ) {	// |x| <= pi/4
		if ( ax >= 0x3f80000000000000ull ) {
			return (float)WebLibmSinPoly( x );
		}
		if ( ax >= 0x3f20000000000000ull ) {
			return (float)fma( -( x * x * x ), WebLibmDouble( 0x3fc5555555555555ull ), x );
		}
		return xf;
	}
	if ( ax >= 0x4170008ac0000000ull ) {
		return (float)sin( x );
	}
	int region;
	const double r = WebLibmReducePiBy2( WebLibmDouble( ax ), region );
	double result = ( region & 1 ) ? WebLibmCosPolySinf( r ) : WebLibmSinPoly( r );
	if ( ( region >= 2 ) != ( x < 0.0 ) ) {
		result = -result;
	}
	return (float)result;
}

static ID_INLINE float WebCosf( float xf ) {
	unsigned int xbits;
	memcpy( &xbits, &xf, sizeof( xbits ) );
	if ( ( xbits & 0x7f800000u ) == 0x7f800000u ) {
		return xf - xf;
	}
	const double x = xf;
	const unsigned long long ax = WebLibmBits( x ) & 0x7fffffffffffffffull;
	if ( ax <= 0x3fe921fb54442d18ull ) {	// |x| <= pi/4
		if ( ax >= 0x3f80000000000000ull ) {
			return (float)WebLibmCosPolyCosf( x );
		}
		if ( ax >= 0x3f20000000000000ull ) {
			return (float)fma( -( x * 0.5 ), x, 1.0 );
		}
		return 1.0f;
	}
	if ( ax >= 0x41e921fb60000000ull ) {
		return (float)cos( x );
	}
	int region;
	const double r = WebLibmReducePiBy2( WebLibmDouble( ax ), region );
	double result = ( region & 1 ) ? WebLibmSinPoly( r ) : WebLibmCosPolyCosf( r );
	if ( ( ( region + 1 ) >> 1 ) & 1 ) {
		result = -result;
	}
	return (float)result;
}


#endif
