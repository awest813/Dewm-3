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
//
// The same commit's asinf.c, acosf.c, atanf.c, atan2f.c (with the fused
// operations MSVC generates for them), tanf.asm, expf.asm and logf.asm FMA3
// paths, the Payne-Hanek reduction of sinf/tanf and __remainder_piby2_fma3
// (cosf) follow below; sys/web_libm.cpp makes them the web build's float
// functions. Every one of the 2^32 float inputs of sinf, cosf, tanf, asinf,
// acosf, atanf, expf and logf matches UCRT bit for bit, as do 2^32 generated
// atan2f pairs (NaN payloads aside); tests/web_trig_check.py keeps native
// fixtures. UCRT's powf is not part of win-libm and stays musl's.
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

static ID_INLINE float WebLibmFloat( unsigned int bits ) {
	float f;
	memcpy( &f, &bits, sizeof( f ) );
	return f;
}

static ID_INLINE unsigned int WebLibmFloatBits( float f ) {
	unsigned int bits;
	memcpy( &bits, &f, sizeof( bits ) );
	return bits;
}

static const unsigned int webLibmLog128Lead[129] = {
	0x00000000u, 0x3bff0000u, 0x3c7e0000u, 0x3cbdc000u, 0x3cfc1000u, 0x3d1cf000u, 0x3d3ba000u, 0x3d5a1000u,
	0x3d785000u, 0x3d8b2000u, 0x3d9a0000u, 0x3da8d000u, 0x3db78000u, 0x3dc61000u, 0x3dd49000u, 0x3de2f000u,
	0x3df13000u, 0x3dff6000u, 0x3e06b000u, 0x3e0db000u, 0x3e14a000u, 0x3e1b8000u, 0x3e226000u, 0x3e293000u,
	0x3e2ff000u, 0x3e36b000u, 0x3e3d5000u, 0x3e43f000u, 0x3e4a9000u, 0x3e511000u, 0x3e579000u, 0x3e5e1000u,
	0x3e647000u, 0x3e6ae000u, 0x3e713000u, 0x3e778000u, 0x3e7dc000u, 0x3e820000u, 0x3e851000u, 0x3e882000u,
	0x3e8b3000u, 0x3e8e4000u, 0x3e914000u, 0x3e944000u, 0x3e974000u, 0x3e9a3000u, 0x3e9d3000u, 0x3ea02000u,
	0x3ea30000u, 0x3ea5f000u, 0x3ea8d000u, 0x3eabb000u, 0x3eae8000u, 0x3eb16000u, 0x3eb43000u, 0x3eb70000u,
	0x3eb9c000u, 0x3ebc9000u, 0x3ebf5000u, 0x3ec21000u, 0x3ec4d000u, 0x3ec78000u, 0x3eca3000u, 0x3ecce000u,
	0x3ecf9000u, 0x3ed24000u, 0x3ed4e000u, 0x3ed78000u, 0x3eda2000u, 0x3edcc000u, 0x3edf5000u, 0x3ee1e000u,
	0x3ee47000u, 0x3ee70000u, 0x3ee99000u, 0x3eec1000u, 0x3eeea000u, 0x3ef12000u, 0x3ef3a000u, 0x3ef61000u,
	0x3ef89000u, 0x3efb0000u, 0x3efd7000u, 0x3effe000u, 0x3f012000u, 0x3f025000u, 0x3f039000u, 0x3f04c000u,
	0x3f05f000u, 0x3f072000u, 0x3f084000u, 0x3f097000u, 0x3f0aa000u, 0x3f0bc000u, 0x3f0cf000u, 0x3f0e1000u,
	0x3f0f4000u, 0x3f106000u, 0x3f118000u, 0x3f12a000u, 0x3f13c000u, 0x3f14e000u, 0x3f160000u, 0x3f172000u,
	0x3f183000u, 0x3f195000u, 0x3f1a7000u, 0x3f1b8000u, 0x3f1c9000u, 0x3f1db000u, 0x3f1ec000u, 0x3f1fd000u,
	0x3f20e000u, 0x3f21f000u, 0x3f230000u, 0x3f241000u, 0x3f252000u, 0x3f263000u, 0x3f273000u, 0x3f284000u,
	0x3f295000u, 0x3f2a5000u, 0x3f2b5000u, 0x3f2c6000u, 0x3f2d6000u, 0x3f2e6000u, 0x3f2f7000u, 0x3f307000u,
	0x3f317000u,
};
static const unsigned int webLibmLog128Tail[129] = {
	0x00000000u, 0x3429ac41u, 0x35a8b0fcu, 0x368d83eau, 0x361b0e78u, 0x3687b9feu, 0x3631ec65u, 0x36dd7119u,
	0x35c30045u, 0x379b7751u, 0x37ebcb0du, 0x37839f83u, 0x37528ae5u, 0x37a2eb18u, 0x36da7495u, 0x36a91eb7u,
	0x3783b715u, 0x371131dbu, 0x383f3e68u, 0x38156a97u, 0x38297c0fu, 0x387e100fu, 0x3815b665u, 0x37e5e3a1u,
	0x38183853u, 0x35fe719du, 0x38448108u, 0x38503290u, 0x373539e8u, 0x385e0ff1u, 0x3864a740u, 0x3786742du,
	0x387be3cdu, 0x3685ad3eu, 0x3803b715u, 0x37adcbdcu, 0x380c36afu, 0x371652d3u, 0x38927139u, 0x38c5fcd7u,
	0x38ae55d5u, 0x3818c169u, 0x38a0fde7u, 0x38ad09efu, 0x3862bae1u, 0x38eecd4cu, 0x3798aad2u, 0x37421a1au,
	0x38c5e10eu, 0x37bf2aeeu, 0x382d872du, 0x37ee2e8au, 0x38dedfacu, 0x3802f2b9u, 0x38481e9bu, 0x380eaa2bu,
	0x38ebfb5du, 0x38255fddu, 0x38783b82u, 0x3851da1eu, 0x374e1b05u, 0x388f439bu, 0x38ca0e10u, 0x38cac08bu,
	0x3891f65fu, 0x378121cbu, 0x386c9a9au, 0x38949923u, 0x38777bccu, 0x37b12d26u, 0x38a6ced3u, 0x38ebd3e6u,
	0x38fbe3cdu, 0x38d785c2u, 0x387e7e00u, 0x38f392c5u, 0x37d40983u, 0x38081a7cu, 0x3784c3adu, 0x38cce923u,
	0x380f5fafu, 0x3891fd38u, 0x38ac47bcu, 0x3897042bu, 0x392952d2u, 0x396fced4u, 0x37f97073u, 0x385e9eaeu,
	0x3865c84au, 0x38130ba3u, 0x3979cf16u, 0x3938cac9u, 0x38c3d2f4u, 0x39755decu, 0x38e6b467u, 0x395c0fb8u,
	0x383ebce0u, 0x38dcd192u, 0x39186bdfu, 0x392de74cu, 0x392f0944u, 0x391bff61u, 0x38e9ed44u, 0x38686dc8u,
	0x396b99a7u, 0x39099c89u, 0x37a27673u, 0x390bdaa3u, 0x397069abu, 0x388449ffu, 0x39013538u, 0x392dc268u,
	0x3947f423u, 0x394ff17cu, 0x3945e10eu, 0x3929e8f5u, 0x38f85db0u, 0x38735f99u, 0x396c08dbu, 0x3909e600u,
	0x37b4996fu, 0x391233ccu, 0x397cead9u, 0x38adb5cdu, 0x3920261au, 0x3958ee36u, 0x35aa4905u, 0x37cbd11eu,
	0x3805fdf4u,
};
static const unsigned int webLibmLogFInv[129] = {
	0x40000000u, 0x3ffe03f8u, 0x3ffc0fc1u, 0x3ffa232du, 0x3ff83e10u, 0x3ff6603eu, 0x3ff4898du, 0x3ff2b9d6u,
	0x3ff0f0f1u, 0x3fef2eb7u, 0x3fed7304u, 0x3febbdb3u, 0x3fea0ea1u, 0x3fe865acu, 0x3fe6c2b4u, 0x3fe52598u,
	0x3fe38e39u, 0x3fe1fc78u, 0x3fe07038u, 0x3fdee95cu, 0x3fdd67c9u, 0x3fdbeb62u, 0x3fda740eu, 0x3fd901b2u,
	0x3fd79436u, 0x3fd62b81u, 0x3fd4c77bu, 0x3fd3680du, 0x3fd20d21u, 0x3fd0b6a0u, 0x3fcf6475u, 0x3fce168au,
	0x3fcccccdu, 0x3fcb8728u, 0x3fca4588u, 0x3fc907dau, 0x3fc7ce0cu, 0x3fc6980cu, 0x3fc565c8u, 0x3fc43730u,
	0x3fc30c31u, 0x3fc1e4bcu, 0x3fc0c0c1u, 0x3fbfa030u, 0x3fbe82fau, 0x3fbd6910u, 0x3fbc5264u, 0x3fbb3ee7u,
	0x3fba2e8cu, 0x3fb92144u, 0x3fb81703u, 0x3fb70fbbu, 0x3fb60b61u, 0x3fb509e7u, 0x3fb40b41u, 0x3fb30f63u,
	0x3fb21643u, 0x3fb11fd4u, 0x3fb02c0bu, 0x3faf3adeu, 0x3fae4c41u, 0x3fad602bu, 0x3fac7692u, 0x3fab8f6au,
	0x3faaaaabu, 0x3fa9c84au, 0x3fa8e83fu, 0x3fa80a81u, 0x3fa72f05u, 0x3fa655c4u, 0x3fa57eb5u, 0x3fa4a9cfu,
	0x3fa3d70au, 0x3fa3065eu, 0x3fa237c3u, 0x3fa16b31u, 0x3fa0a0a1u, 0x3f9fd80au, 0x3f9f1166u, 0x3f9e4cadu,
	0x3f9d89d9u, 0x3f9cc8e1u, 0x3f9c09c1u, 0x3f9b4c70u, 0x3f9a90e8u, 0x3f99d723u, 0x3f991f1au, 0x3f9868c8u,
	0x3f97b426u, 0x3f97012eu, 0x3f964fdau, 0x3f95a025u, 0x3f94f209u, 0x3f944581u, 0x3f939a86u, 0x3f92f114u,
	0x3f924925u, 0x3f91a2b4u, 0x3f90fdbcu, 0x3f905a38u, 0x3f8fb824u, 0x3f8f177au, 0x3f8e7835u, 0x3f8dda52u,
	0x3f8d3dcbu, 0x3f8ca29cu, 0x3f8c08c1u, 0x3f8b7034u, 0x3f8ad8f3u, 0x3f8a42f8u, 0x3f89ae41u, 0x3f891ac7u,
	0x3f888889u, 0x3f87f781u, 0x3f8767abu, 0x3f86d905u, 0x3f864b8au, 0x3f85bf37u, 0x3f853408u, 0x3f84a9fau,
	0x3f842108u, 0x3f839930u, 0x3f83126fu, 0x3f828cc0u, 0x3f820821u, 0x3f81848eu, 0x3f810204u, 0x3f808081u,
	0x3f800000u,
};
static const unsigned long long webLibmTwoToJBy64[64] = {
	0x3ff0000000000000ull, 0x3ff02c9a3e778061ull, 0x3ff059b0d3158574ull, 0x3ff0874518759bc8ull,
	0x3ff0b5586cf9890full, 0x3ff0e3ec32d3d1a2ull, 0x3ff11301d0125b51ull, 0x3ff1429aaea92de0ull,
	0x3ff172b83c7d517bull, 0x3ff1a35beb6fcb75ull, 0x3ff1d4873168b9aaull, 0x3ff2063b88628cd6ull,
	0x3ff2387a6e756238ull, 0x3ff26b4565e27cddull, 0x3ff29e9df51fdee1ull, 0x3ff2d285a6e4030bull,
	0x3ff306fe0a31b715ull, 0x3ff33c08b26416ffull, 0x3ff371a7373aa9cbull, 0x3ff3a7db34e59ff7ull,
	0x3ff3dea64c123422ull, 0x3ff4160a21f72e2aull, 0x3ff44e086061892dull, 0x3ff486a2b5c13cd0ull,
	0x3ff4bfdad5362a27ull, 0x3ff4f9b2769d2ca7ull, 0x3ff5342b569d4f82ull, 0x3ff56f4736b527daull,
	0x3ff5ab07dd485429ull, 0x3ff5e76f15ad2148ull, 0x3ff6247eb03a5585ull, 0x3ff6623882552225ull,
	0x3ff6a09e667f3bcdull, 0x3ff6dfb23c651a2full, 0x3ff71f75e8ec5f74ull, 0x3ff75feb564267c9ull,
	0x3ff7a11473eb0187ull, 0x3ff7e2f336cf4e62ull, 0x3ff82589994cce13ull, 0x3ff868d99b4492edull,
	0x3ff8ace5422aa0dbull, 0x3ff8f1ae99157736ull, 0x3ff93737b0cdc5e5ull, 0x3ff97d829fde4e50ull,
	0x3ff9c49182a3f090ull, 0x3ffa0c667b5de565ull, 0x3ffa5503b23e255dull, 0x3ffa9e6b5579fdbfull,
	0x3ffae89f995ad3adull, 0x3ffb33a2b84f15fbull, 0x3ffb7f76f2fb5e47ull, 0x3ffbcc1e904bc1d2ull,
	0x3ffc199bdd85529cull, 0x3ffc67f12e57d14bull, 0x3ffcb720dcef9069ull, 0x3ffd072d4a07897cull,
	0x3ffd5818dcfba487ull, 0x3ffda9e603db3285ull, 0x3ffdfc97337b9b5full, 0x3ffe502ee78b3ff6ull,
	0x3ffea4afa2a490daull, 0x3ffefa1bee615a27ull, 0x3fff50765b6e4540ull, 0x3fffa7c1819e90d8ull,
};
static const unsigned char webLibmTwoByPiBits[158] = {
	224, 241, 27, 193, 12, 88, 33, 116, 53, 126, 196, 126, 237, 175, 169, 75,
	74, 41, 222, 231, 28, 244, 236, 197, 151, 175, 31, 235, 158, 212, 181, 168,
	127, 121, 154, 253, 24, 61, 221, 38, 44, 159, 60, 251, 217, 180, 125, 180,
	41, 104, 45, 70, 188, 188, 63, 96, 22, 120, 255, 95, 226, 127, 236, 160,
	228, 247, 46, 126, 17, 114, 210, 231, 76, 13, 230, 88, 71, 230, 4, 249,
	125, 209, 154, 192, 113, 166, 19, 18, 237, 186, 212, 215, 8, 162, 251, 156,
	166, 196, 114, 172, 119, 248, 115, 72, 70, 39, 168, 187, 36, 25, 128, 75,
	55, 9, 233, 184, 145, 220, 134, 21, 239, 122, 175, 142, 69, 249, 7, 65,
	14, 241, 100, 86, 138, 109, 3, 119, 211, 212, 71, 95, 157, 240, 167, 84,
	16, 57, 185, 13, 230, 139, 2, 0, 0, 0, 0, 0, 0, 0,
};

// Payne-Hanek reduction of tanf.asm (and sinf/cosf) for |x| >= 3.373259264e9:
// returns the reduced argument and its quadrant, as the integer code does.
static ID_INLINE unsigned long long WebLibmLoad64( const unsigned char *p ) {
	unsigned long long v = 0;
	for ( int i = 7; i >= 0; i-- ) v = ( v << 8 ) | p[i];
	return v;
}

static ID_INLINE void WebLibmMul64( unsigned long long a, unsigned long long b, unsigned long long &lo, unsigned long long &hi ) {
	const unsigned long long a0 = a & 0xffffffffull, a1 = a >> 32, b0 = b & 0xffffffffull, b1 = b >> 32;
	const unsigned long long p00 = a0 * b0, p01 = a0 * b1, p10 = a1 * b0, p11 = a1 * b1;
	const unsigned long long mid = ( p00 >> 32 ) + ( p01 & 0xffffffffull ) + ( p10 & 0xffffffffull );
	lo = ( mid << 32 ) | ( p00 & 0xffffffffull );
	hi = p11 + ( p01 >> 32 ) + ( p10 >> 32 ) + ( mid >> 32 );
}

// The integer part of the reduction: 2/pi times |x| as fixed point. Returns the
// reduced argument's leading double bits (sign included) and sets the next 64
// mantissa bits, the sign and the biased exponent for the precise variant.
struct webLibmLargeReduction_t {
	unsigned long long head, next, sign;
	long long biasedExp;
	int region;
};

static ID_INLINE webLibmLargeReduction_t WebLibmReduceLargeBits( double ax ) {
	webLibmLargeReduction_t out;
	const unsigned long long ux = WebLibmBits( ax );
	const long long xexp = (long long)( ux >> 52 ) - 1023;
	const long long last = 134 - ( xexp >> 3 );
	const unsigned long long mant = ( ( ux << 12 ) >> 12 ) | ( 1ull << 52 );
	unsigned long long lo, hi, r8, r9, r10, rdx;
	WebLibmMul64( WebLibmLoad64( webLibmTwoByPiBits + last ), mant, lo, hi );
	r8 = lo;
	r10 = hi;
	WebLibmMul64( WebLibmLoad64( webLibmTwoByPiBits + last + 8 ), mant, lo, hi );
	const long long resexp = xexp & 7;
	r9 = lo + r10;
	r10 = hi + ( r9 < lo ? 1 : 0 );
	WebLibmMul64( WebLibmLoad64( webLibmTwoByPiBits + last + 16 ), mant, lo, hi );
	r10 += lo;
	const int shift = (int)( 54 - resexp );
	unsigned long long rax = r10 >> shift;
	const unsigned long long carry = ( r10 >> ( shift - 1 ) ) & 1;	// shr's carry flag
	rdx = 0;
	if ( carry ) {
		r10 = ~r10;
		r9 = ~r9;
		r8 = ~r8;
		rdx = 0x8000000000000000ull;
	}
	out.region = (int)( ( rax + carry ) & 3 );
	long long rcx = resexp + 10;
	r10 = ( r10 << rcx ) >> rcx;
	long long r11 = rcx - 64;
	if ( r10 == 0 ) {
		r10 = r9;
		r9 = r8;
		r8 = 0;
		r11 -= 64;
	}
	int hsb = 63;
	while ( hsb > 0 && !( ( r10 >> hsb ) & 1 ) ) hsb--;
	r11 += hsb;
	rcx = hsb - 52;
	if ( rcx < 0 ) {
		rcx = -rcx;
		rax = r9;
		r10 <<= rcx;
		r9 <<= rcx;
		rcx = 64 - rcx;
		rax >>= rcx;
		r10 |= rax;
		r8 >>= rcx;
		r9 |= r8;
	} else if ( rcx > 0 ) {
		r8 = r10;
		r10 >>= rcx;
		r9 >>= rcx;
		rcx = 64 - rcx;
		r8 <<= rcx;
		r9 |= r8;
	}
	r11 += 1023;
	r10 &= ~( 1ull << 52 );
	r10 |= rdx;
	r10 |= (unsigned long long)r11 << 52;
	out.head = r10;
	out.next = r9;
	out.sign = rdx;
	out.biasedExp = r11;
	return out;
}

// sinf.asm and tanf.asm finish with one multiplication by pi/2.
static ID_INLINE double WebLibmReduceLarge( double ax, int &region ) {
	const webLibmLargeReduction_t red = WebLibmReduceLargeBits( ax );
	region = red.region;
	return WebLibmDouble( red.head ) * WebLibmDouble( 0x3ff921fb54442d18ull );
}

// cosf.asm calls __remainder_piby2_fma3, which also uses the next 64 bits.
static ID_INLINE double WebLibmReduceLargePrecise( double ax, int &region ) {
	const webLibmLargeReduction_t red = WebLibmReduceLargeBits( ax );
	region = red.region;
	unsigned long long r9 = red.next;
	int hsb = 63;
	while ( hsb > 0 && !( ( r9 >> hsb ) & 1 ) ) hsb--;
	long long rcx = 64 - hsb;
	r9 <<= ( rcx & 63 );
	r9 >>= 12;
	rcx += 52;
	const unsigned long long r11 = (unsigned long long)( red.biasedExp - rcx ) << 52;
	r9 |= red.sign;
	r9 |= r11;
	const double x = WebLibmDouble( red.head ), xx = WebLibmDouble( r9 );
	const double hx = WebLibmDouble( red.head & 0xfffffffff8000000ull );
	const double tx = x - hx;
	const double c = x * WebLibmDouble( 0x3ff921fb54442d18ull );
	double cc = hx * WebLibmDouble( 0x3ff921fb50000000ull );
	cc = cc - c;
	cc = fma( tx, WebLibmDouble( 0x3ff921fb50000000ull ), cc );
	cc = fma( hx, WebLibmDouble( 0x3e5110b460000000ull ), cc );
	cc = fma( tx, WebLibmDouble( 0x3e5110b460000000ull ), cc );
	const double t4 = fma( x, WebLibmDouble( 0x3c91a62633145c06ull ), xx * WebLibmDouble( 0x3ff921fb54442d18ull ) );
	cc = cc + t4;
	return c + cc;
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
		// _sincosf_special: NaN is quieted, infinity is invalid. Bit patterns, not
		// xf - xf, which -ffinite-math-only folds to zero.
		return WebLibmFloat( ( xbits & 0x007fffffu ) ? ( xbits | 0x00400000u ) : 0xffc00000u );
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
	int region;
	const double r = ax >= 0x4170008ac0000000ull ? WebLibmReduceLarge( WebLibmDouble( ax ), region ) :
		WebLibmReducePiBy2( WebLibmDouble( ax ), region );
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
		// _sincosf_special: NaN is quieted, infinity is invalid. Bit patterns, not
		// xf - xf, which -ffinite-math-only folds to zero.
		return WebLibmFloat( ( xbits & 0x007fffffu ) ? ( xbits | 0x00400000u ) : 0xffc00000u );
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
	int region;
	const double r = ax >= 0x41e921fb60000000ull ? WebLibmReduceLargePrecise( WebLibmDouble( ax ), region ) :
		WebLibmReducePiBy2( WebLibmDouble( ax ), region );
	double result = ( region & 1 ) ? WebLibmSinPoly( r ) : WebLibmCosPolyCosf( r );
	if ( ( ( region + 1 ) >> 1 ) & 1 ) {
		result = -result;
	}
	return (float)result;
}


// asinf.c; MSVC fuses the rational approximation and reconstruction as in acosf.
static ID_INLINE float WebAsinf( float x ) {
	const float piby2_tail = 7.5497894159e-08F, hpiby2_head = 7.8539812565e-01F, piby2 = 1.5707963705e+00F;
	const unsigned int ux = WebLibmFloatBits( x ), aux = ux & 0x7fffffffu, xneg = ux & 0x80000000u;
	const int xexp = (int)( ( ux & 0x7f800000u ) >> 23 ) - 127;
	float u, v, y, s = 0.0F, r;
	if ( aux > 0x7f800000u ) return WebLibmFloat( ux | 0x00400000u );
	if ( xexp < -14 ) return x;
	if ( xexp >= 0 ) {
		if ( x == 1.0F ) return piby2;
		if ( x == -1.0F ) return -piby2;
		return WebLibmFloat( 0xffc00000u );
	}
	y = xneg ? -x : x;
	const int transform = ( xexp >= -1 );
	if ( transform ) {
		r = 0.5F * ( 1.0F - y );
		s = sqrtf( r );
		y = s;
	} else {
		r = y * y;
	}
	u = r * fmaf( r, fmaf( r, fmaf( -0.00396137437848476485201154797087F, r, -0.0133819288943925804214011424456F ),
		-0.0565298683201845211985026327361F ), 0.184161606965100694821398249421F ) /
		fmaf( -0.836411276854206731913362287293F, r, 1.10496961524520294485512696706F );
	if ( transform ) {
		const float s1 = WebLibmFloat( WebLibmFloatBits( s ) & 0xffff0000u );
		const float c = fmaf( -s1, s1, r ) / ( s + s1 );
		const float p = fmaf( 2.0F * s, u, -fmaf( -2.0F, c, piby2_tail ) );
		const float q = fmaf( -2.0F, s1, hpiby2_head );
		v = hpiby2_head - ( p - q );
	} else {
		v = fmaf( y, u, y );
	}
	return xneg ? -v : v;
}

// acosf.c, the same port as WebRotationACos without idMath's endpoint clamps.
static ID_INLINE float WebAcosf( float x ) {
	const float piby2 = 1.5707963705e+00F;
	const double pi = 3.1415926535897933e+00, piby2_head = 1.5707963267948965580e+00, piby2_tail = 6.12323399573676603587e-17;
	const unsigned int ux = WebLibmFloatBits( x ), aux = ux & 0x7fffffffu, xneg = ux & 0x80000000u;
	const int xexp = (int)( ( ux & 0x7f800000u ) >> 23 ) - 127;
	float u, y, s = 0.0F, r;
	if ( aux > 0x7f800000u ) return WebLibmFloat( ux | 0x00400000u );
	if ( xexp >= 0 ) {
		if ( x == 1.0F ) return 0.0F;
		if ( x == -1.0F ) return (float)pi;
		return WebLibmFloat( 0xffc00000u );
	}
	if ( xexp < -26 ) return piby2;
	y = xneg ? -x : x;
	const int transform = ( xexp >= -1 );
	if ( transform ) {
		r = 0.5F * ( 1.0F - y );
		s = sqrtf( r );
		y = s;
	} else {
		r = y * y;
	}
	u = r * fmaf( r, fmaf( r, fmaf( -0.00396137437848476485201154797087F, r, -0.0133819288943925804214011424456F ),
		-0.0565298683201845211985026327361F ), 0.184161606965100694821398249421F ) /
		fmaf( -0.836411276854206731913362287293F, r, 1.10496961524520294485512696706F );
	if ( transform ) {
		if ( xneg ) {
			return (float)( pi - 2.0 * ( s + ( y * u - piby2_tail ) ) );
		}
		const float s1 = WebLibmFloat( WebLibmFloatBits( s ) & 0xffff0000u );
		const float c = fmaf( -s1, s1, r ) / ( s + s1 );
		return 2.0F * s1 + fmaf( 2.0F * y, u, 2.0F * c );
	}
	return (float)( piby2_head - ( x - ( piby2_tail - x * u ) ) );
}

// atanf.c (double internally).
static ID_INLINE float WebAtanf( float fx ) {
	const double piby2 = 1.5707963267948966e+00;
	double c, v, s, q, z, x = fx;
	const unsigned long long ux = WebLibmBits( x ), aux = ux & ~0x8000000000000000ull, xneg = ux & 0x8000000000000000ull;
	v = xneg ? -x : x;
	if ( aux < 0x3fdc000000000000ull ) {
		x = v;
		c = 0.0;
	} else if ( aux < 0x3fe6000000000000ull ) {
		x = ( 2.0 * v - 1.0 ) / ( 2.0 + v );
		c = 4.63647609000806093515e-01;
	} else if ( aux < 0x3ff3000000000000ull ) {
		x = ( v - 1.0 ) / ( 1.0 + v );
		c = 7.85398163397448278999e-01;
	} else if ( aux < 0x4003800000000000ull ) {
		x = ( v - 1.5 ) / fma( 1.5, v, 1.0 );
		c = 9.82793723247329054082e-01;
	} else {
		if ( aux > 0x7ff0000000000000ull ) return WebLibmFloat( WebLibmFloatBits( fx ) | 0x00400000u );
		// The source compares v with an integer literal: 0x4c80000000000000 as a double, about 5.5e18.
		if ( v > (double)0x4c80000000000000ull ) return xneg ? (float)-piby2 : (float)piby2;
		x = -1.0 / v;
		c = 1.57079632679489655800e+00;
	}
	s = x * x;
	q = x * s * fma( fma( 0.470677934286149214138357545549e-2, s, 0.192324546402108583211697690500e0 ), s, 0.296528598819239217902158651186e0 ) /
		fma( fma( 0.299309699959659728404442796915e0, s, 0.111072499995399550138837673349e1 ), s, 0.889585796862432286486651434570e0 );
	z = c - ( q - x );
	if ( xneg ) z = -z;
	return (float)z;
}

static const unsigned long long webLibmAtanJBy256[241] = {
	0x3faff55bb72cfde9ull,
	0x3fb0f99ea71d52a6ull,
	0x3fb1f86dbf082d58ull,
	0x3fb2f719318a4a9aull,
	0x3fb3f59f0e7c559dull,
	0x3fb4f3fd677292fbull,
	0x3fb5f2324fd2d7b2ull,
	0x3fb6f03bdcea4b0cull,
	0x3fb7ee182602f10eull,
	0x3fb8ebc54478fb28ull,
	0x3fb9e94153cfdcf1ull,
	0x3fbae68a71c722b8ull,
	0x3fbbe39ebe6f07c3ull,
	0x3fbce07c5c3cca32ull,
	0x3fbddd21701eba6eull,
	0x3fbed98c2190043aull,
	0x3fbfd5ba9aac2f6dull,
	0x3fc068d584212b3dull,
	0x3fc0e6adccf40881ull,
	0x3fc1646541060850ull,
	0x3fc1e1fafb043726ull,
	0x3fc25f6e171a535cull,
	0x3fc2dcbdb2fba1ffull,
	0x3fc359e8edeb99a3ull,
	0x3fc3d6eee8c6626cull,
	0x3fc453cec6092a9eull,
	0x3fc4d087a9da4f17ull,
	0x3fc54d18ba11570aull,
	0x3fc5c9811e3ec269ull,
	0x3fc645bfffb3aa73ull,
	0x3fc6c1d4898933d8ull,
	0x3fc73dbde8a7d201ull,
	0x3fc7b97b4bce5b02ull,
	0x3fc8350be398ebc7ull,
	0x3fc8b06ee2879c28ull,
	0x3fc92ba37d050271ull,
	0x3fc9a6a8e96c8626ull,
	0x3fca217e601081a5ull,
	0x3fca9c231b403279ull,
	0x3fcb1696574d780bull,
	0x3fcb90d7529260a2ull,
	0x3fcc0ae54d768466ull,
	0x3fcc84bf8a742e6dull,
	0x3fccfe654e1d5395ull,
	0x3fcd77d5df205736ull,
	0x3fcdf110864c9d9dull,
	0x3fce6a148e96ec4dull,
	0x3fcee2e1451d980cull,
	0x3fcf5b75f92c80ddull,
	0x3fcfd3d1fc40dbe4ull,
	0x3fd025fa510665b5ull,
	0x3fd061eea03d6290ull,
	0x3fd09dc597d86362ull,
	0x3fd0d97ee509acb3ull,
	0x3fd1151a362431c9ull,
	0x3fd150973a9ce546ull,
	0x3fd18bf5a30bf178ull,
	0x3fd1c735212dd883ull,
	0x3fd2025567e47c95ull,
	0x3fd23d562b381041ull,
	0x3fd278372057ef45ull,
	0x3fd2b2f7fd9b5fe2ull,
	0x3fd2ed987a823cfeull,
	0x3fd328184fb58951ull,
	0x3fd362773707ebcbull,
	0x3fd39cb4eb76157bull,
	0x3fd3d6d129271134ull,
	0x3fd410cbad6c7d32ull,
	0x3fd44aa436c2af09ull,
	0x3fd4845a84d0c21bull,
	0x3fd4bdee586890e6ull,
	0x3fd4f75f73869978ull,
	0x3fd530ad9951cd49ull,
	0x3fd569d88e1b4cd7ull,
	0x3fd5a2e0175e0f4eull,
	0x3fd5dbc3fbbe768dull,
	0x3fd614840309cfe1ull,
	0x3fd64d1ff635c1c5ull,
	0x3fd685979f5fa6fdull,
	0x3fd6bdeac9cbd76cull,
	0x3fd6f61941e4def0ull,
	0x3fd72e22d53aa2a9ull,
	0x3fd7660752817501ull,
	0x3fd79dc6899118d1ull,
	0x3fd7d5604b63b3f7ull,
	0x3fd80cd46a14b1d0ull,
	0x3fd84422b8df95d7ull,
	0x3fd87b4b0c1ebedbull,
	0x3fd8b24d394a1b25ull,
	0x3fd8e92916f5cde8ull,
	0x3fd91fde7cd0c662ull,
	0x3fd9566d43a34907ull,
	0x3fd98cd5454d6b18ull,
	0x3fd9c3165cc58107ull,
	0x3fd9f93066168001ull,
	0x3fda2f233e5e530bull,
	0x3fda64eec3cc23fcull,
	0x3fda9a92d59e98cfull,
	0x3fdad00f5422058bull,
	0x3fdb056420ae9343ull,
	0x3fdb3a911da65c6cull,
	0x3fdb6f962e737efbull,
	0x3fdba473378624a5ull,
	0x3fdbd9281e528191ull,
	0x3fdc0db4c94ec9efull,
	0x3fdc42191ff11eb6ull,
	0x3fdc76550aad71f8ull,
	0x3fdcaa6872f3631bull,
	0x3fdcde53432c1350ull,
	0x3fdd121566b7f2adull,
	0x3fdd45aec9ec862bull,
	0x3fdd791f5a1226f4ull,
	0x3fddac670561bb4full,
	0x3fdddf85bb026974ull,
	0x3fde127b6b0744afull,
	0x3fde4548066cf51aull,
	0x3fde77eb7f175a34ull,
	0x3fdeaa65c7cf28c4ull,
	0x3fdedcb6d43f8434ull,
	0x3fdf0ede98f393cfull,
	0x3fdf40dd0b541417ull,
	0x3fdf72b221a4e495ull,
	0x3fdfa45dd3029258ull,
	0x3fdfd5e0175fdf83ull,
	0x3fe0039c73c1a40bull,
	0x3fe01c341e82422dull,
	0x3fe034b709250488ull,
	0x3fe04d25314342e5ull,
	0x3fe0657e94db30cfull,
	0x3fe07dc3324e9b38ull,
	0x3fe095f30861a58full,
	0x3fe0ae0e1639866cull,
	0x3fe0c6145b5b43daull,
	0x3fe0de05d7aa6f7cull,
	0x3fe0f5e28b67e295ull,
	0x3fe10daa77307a0dull,
	0x3fe1255d9bfbd2a8ull,
	0x3fe13cfbfb1b056eull,
	0x3fe1548596376469ull,
	0x3fe16bfa6f5137e1ull,
	0x3fe1835a88be7c13ull,
	0x3fe19aa5e5299f99ull,
	0x3fe1b1dc87904284ull,
	0x3fe1c8fe7341f64full,
	0x3fe1e00babdefeb3ull,
	0x3fe1f7043557138aull,
	0x3fe20de813e823b1ull,
	0x3fe224b74c1d192aull,
	0x3fe23b71e2cc9e6aull,
	0x3fe25217dd17e501ull,
	0x3fe268a940696da6ull,
	0x3fe27f261273d1b3ull,
	0x3fe2958e59308e30ull,
	0x3fe2abe21aded073ull,
	0x3fe2c2215e024465ull,
	0x3fe2d84c2961e48bull,
	0x3fe2ee628406cbcaull,
	0x3fe30464753b090aull,
	0x3fe31a52048874beull,
	0x3fe3302b39b78856ull,
	0x3fe345f01cce37bbull,
	0x3fe35ba0b60eccceull,
	0x3fe3713d0df6c503ull,
	0x3fe386c52d3db11eull,
	0x3fe39c391cd41719ull,
	0x3fe3b198e5e2564aull,
	0x3fe3c6e491c78dc4ull,
	0x3fe3dc1c2a188504ull,
	0x3fe3f13fb89e96f4ull,
	0x3fe4064f47569f48ull,
	0x3fe41b4ae06fea41ull,
	0x3fe430328e4b26d5ull,
	0x3fe445065b795b55ull,
	0x3fe459c652badc7full,
	0x3fe46e727efe4715ull,
	0x3fe4830aeb5f7bfdull,
	0x3fe4978fa3269ee1ull,
	0x3fe4ac00b1c71762ull,
	0x3fe4c05e22de94e4ull,
	0x3fe4d4a8023414e8ull,
	0x3fe4e8de5bb6ec04ull,
	0x3fe4fd013b7dd17eull,
	0x3fe51110adc5ed81ull,
	0x3fe5250cbef1e9faull,
	0x3fe538f57b89061eull,
	0x3fe54ccaf0362c8full,
	0x3fe5608d29c70c34ull,
	0x3fe5743c352b33b9ull,
	0x3fe587d81f732fbaull,
	0x3fe59b60f5cfab9dull,
	0x3fe5aed6c5909517ull,
	0x3fe5c2399c244260ull,
	0x3fe5d58987169b18ull,
	0x3fe5e8c6941043cfull,
	0x3fe5fbf0d0d5cc49ull,
	0x3fe60f084b46e05eull,
	0x3fe6220d115d7b8dull,
	0x3fe634ff312d1f3bull,
	0x3fe647deb8e20b8full,
	0x3fe65aabb6c07b02ull,
	0x3fe66d663923e086ull,
	0x3fe6800e4e7e2857ull,
	0x3fe692a40556fb6aull,
	0x3fe6a5276c4b0575ull,
	0x3fe6b798920b3d98ull,
	0x3fe6c9f7855c3198ull,
	0x3fe6dc44551553aeull,
	0x3fe6ee7f10204aefull,
	0x3fe700a7c5784633ull,
	0x3fe712be84295198ull,
	0x3fe724c35b4fae7bull,
	0x3fe736b65a172dffull,
	0x3fe748978fba8e0full,
	0x3fe75a670b82d8d8ull,
	0x3fe76c24dcc6c6c0ull,
	0x3fe77dd112ea22c7ull,
	0x3fe78f6bbd5d315eull,
	0x3fe7a0f4eb9c19a2ull,
	0x3fe7b26cad2e50fdull,
	0x3fe7c3d311a6092bull,
	0x3fe7d528289fa093ull,
	0x3fe7e66c01c114fdull,
	0x3fe7f79eacb97898ull,
	0x3fe808c03940694aull,
	0x3fe819d0b7158a4cull,
	0x3fe82ad036000005ull,
	0x3fe83bbec5cdee22ull,
	0x3fe84c9c7653f7eaull,
	0x3fe85d69576cc2c5ull,
	0x3fe86e2578f87ae5ull,
	0x3fe87ed0eadc5a2aull,
	0x3fe88f6bbd023118ull,
	0x3fe89ff5ff57f1f7ull,
	0x3fe8b06fc1cf3dfeull,
	0x3fe8c0d9145cf49dull,
	0x3fe8d13206f8c4caull,
	0x3fe8e17aa99cc05dull,
	0x3fe8f1b30c44f167ull,
	0x3fe901db3eeef187ull,
	0x3fe911f35199833bull
	,
	0x3fe921fb54442d18ull
};

// atan2f.c (double internally). The source's x == 0 branch does not return; it
// reaches the exponent test, which returns pi/2 for every nonzero float y.
static ID_INLINE float WebAtan2f( float fy, float fx ) {
	const double pi = 3.1415926535897932e+00, piby2 = 1.5707963267948966e+00, piby4 = 7.8539816339744831e-01, three_piby4 = 2.3561944901923449e+00;
	double u, v, vbyu, q, s, uu, r;
	const double x = fx, y = fy;
	const unsigned long long ux = WebLibmBits( x ), uy = WebLibmBits( y );
	const unsigned long long aux = ux & ~0x8000000000000000ull, auy = uy & ~0x8000000000000000ull;
	const int xexp = (int)( ( ux & 0x7ff0000000000000ull ) >> 52 ), yexp = (int)( ( uy & 0x7ff0000000000000ull ) >> 52 );
	const unsigned long long xneg = ux & 0x8000000000000000ull, yneg = uy & 0x8000000000000000ull;
	const int xzero = ( aux == 0 ), yzero = ( auy == 0 );
	const int xnan = ( aux > 0x7ff0000000000000ull ), ynan = ( auy > 0x7ff0000000000000ull );
	const int xinf = ( aux == 0x7ff0000000000000ull ), yinf = ( auy == 0x7ff0000000000000ull );
	const int diffexp = yexp - xexp;
	if ( xnan ) return WebLibmFloat( WebLibmFloatBits( fx ) | 0x00400000u );
	if ( ynan ) return WebLibmFloat( WebLibmFloatBits( fy ) | 0x00400000u );
	if ( yzero ) {
		if ( xneg ) return yneg ? (float)-pi : (float)pi;
		return (float)y;
	}
	(void)xzero;
	if ( diffexp > 26 ) {
		return yneg ? (float)-piby2 : (float)piby2;
	} else if ( diffexp < -13 && !xneg ) {
		if ( diffexp < -150 ) return yneg ? -0.0F : 0.0F;
		return (float)( y / x );
	} else if ( diffexp < -26 && xneg ) {
		return yneg ? (float)-pi : (float)pi;
	} else if ( yinf && xinf ) {
		if ( xneg ) return yneg ? (float)-three_piby4 : (float)three_piby4;
		return yneg ? (float)-piby4 : (float)piby4;
	}
	u = xneg ? -x : x;
	v = yneg ? -y : y;
	const int swap_vu = ( u < v );
	if ( swap_vu ) { uu = u; u = v; v = uu; }
	vbyu = v / u;
	if ( vbyu > 0.0625 ) {
		const int index = (int)( 256 * vbyu + 0.5 );
		r = ( 256 * v - index * u ) / ( 256 * u + index * v );
		s = r * r;
		q = fma( -( r * s ), 0.33333333333224095522, WebLibmDouble( webLibmAtanJBy256[index - 16] ) + r );
	} else if ( vbyu < 1.e-4 ) {
		q = vbyu;
	} else {
		s = vbyu * vbyu;
		q = fma( -( vbyu * s ), fma( -s, fma( -s, 0.14285713561807169030, 0.19999999999393223405 ), 0.33333333333333170500 ), vbyu );
	}
	if ( swap_vu ) q = piby2 - q;
	if ( xneg ) q = pi - q;
	if ( yneg ) q = -q;
	return (float)q;
}

// tanf.asm, FMA3 path.
static ID_INLINE double WebLibmTanPoly( double r ) {
	const double x2 = r * r;
	const double c = fma( WebLibmDouble( 0xBF919DBA6EFD6AADull ), x2, WebLibmDouble( 0x3FD8A8B0DA56CB17ull ) );
	const double d = fma( fma( WebLibmDouble( 0x3F92E29003C692D9ull ), x2, WebLibmDouble( 0xBFE07266D7B3511Bull ) ), x2,
		WebLibmDouble( 0x3FF27E84A3E73A2Eull ) );
	return fma( x2 * r, c / d, r );
}

static ID_INLINE float WebTanf( float x ) {
	const unsigned int ux = WebLibmFloatBits( x );
	if ( ( ux & 0x7f800000u ) == 0x7f800000u ) {
		// _tanf_special: NaN is quieted, infinity is invalid.
		return ( ux & 0x7fffffu ) ? WebLibmFloat( ux | 0x00400000u ) : WebLibmFloat( 0xffc00000u );
	}
	const double xd = x;
	const unsigned long long ax = WebLibmBits( xd ) & 0x7fffffffffffffffull;
	if ( ax <= 0x3fe921fb54442d18ull ) {
		if ( ax >= 0x3f20000000000000ull ) return (float)WebLibmTanPoly( xd );
		if ( ax >= 0x3e40000000000000ull ) return (float)fma( xd * xd * xd, WebLibmDouble( 0x3FD5555555555555ull ), xd );
		return x;
	}
	const double a = WebLibmDouble( ax );
	double r;
	int region;
	if ( ax >= 0x41E921FB40000000ull ) {
		r = WebLibmReduceLarge( a, region );
	} else {
		const int n = (int)fma( WebLibmDouble( 0x3FE45F306DC9C883ull ), a, 0.5 );
		region = n & 3;
		const double dn = n;
		const double rhead = fma( -dn, WebLibmDouble( 0x3FF921FB54400000ull ), a );
		const double rtail = dn * WebLibmDouble( 0x3DD0B4611A626331ull );
		r = rhead - rtail;
	}
	double t = WebLibmTanPoly( r );
	if ( region & 1 ) t = -1.0 / t;
	if ( WebLibmBits( xd ) & 0x8000000000000000ull ) t = -t;
	return (float)t;
}

// expf.asm, FMA3 path.
static ID_INLINE float WebExpf( float x ) {
	const unsigned int ux = WebLibmFloatBits( x );
	if ( ( ux & 0x7fffffffu ) >= 0x7f800000u ) {
		if ( ux == 0x7f800000u ) return x;
		if ( ux == 0xff800000u ) return 0.0F;
		return WebLibmFloat( ux | 0x00400000u );
	}
	const double xd = x;
	const double t = xd * WebLibmDouble( 0x40571547652b82feull );
	if ( t >= 8192.0 ) return WebLibmFloat( 0x7f800000u );
	if ( t < -9600.0 ) return 0.0F;
	const int n = (int)nearbyint( t );
	const double r = fma( -(double)n, WebLibmDouble( 0x3f862e42fefa39efull ), xd );
	const int j = n & 0x3f;
	const int m = ( n - j ) >> 6;
	const double q = fma( r * r, fma( WebLibmDouble( 0x3fc5555555555555ull ), r, 0.5 ), r );
	const double f = WebLibmDouble( webLibmTwoToJBy64[j] );
	const double e = fma( q, f, f ) * WebLibmDouble( (unsigned long long)( m + 1023 ) << 52 );
	return (float)e;
}

// logf.asm, FMA3 path.
static ID_INLINE float WebLogf( float x ) {
	unsigned int ux = WebLibmFloatBits( x );
	if ( ( ux & 0x7f800000u ) == 0x7f800000u ) {
		if ( ux == 0x7f800000u ) return x;
		if ( ux == 0xff800000u ) return WebLibmFloat( 0xffc00000u );
		return WebLibmFloat( ux | 0x00400000u );
	}
	if ( x <= 0.0F ) return x == 0.0F ? WebLibmFloat( 0xff800000u ) : WebLibmFloat( 0xffc00000u );
	float xexp = (float)( (int)( ux >> 23 ) - 127 );
	unsigned int mant = ux & 0x007fffffu;
	const float xm1 = x - 1.0F;
	if ( xexp == -127.0F ) {
		const unsigned int t = WebLibmFloatBits( WebLibmFloat( mant | 0x3f800000u ) - 1.0F );
		xexp = (float)( (int)( t >> 23 ) - 253 );
		mant = t & 0x007fffffu;
		ux = mant;
	}
	const unsigned int idxbits = ( ux & 0x007f0000u ) + ( ( ux & 0x00008000u ) << 1 );
	if ( WebLibmFloatBits( xm1 ) << 1 < 0x3d800000u << 1 ) {
		const float r = x - 1.0F;
		float u = r / ( 2.0F + r );
		const float correction = r * u;
		u = u + u;
		const float v = u * u;
		const float u3 = u * v;
		const float r2 = fmaf( fmaf( v, WebLibmFloat( 0x3C4CCCCDu ), WebLibmFloat( 0x3DAAAAABu ) ), u3, -correction );
		return r + r2;
	}
	const unsigned int index = idxbits >> 16;
	const float Y = WebLibmFloat( mant | 0x3f000000u );
	const float F = WebLibmFloat( idxbits | 0x3f000000u );
	const float r = ( F - Y ) * WebLibmFloat( webLibmLogFInv[index] );
	const float p = fmaf( WebLibmFloat( 0x3eaaaaabu ), r, 0.5F );
	const float poly = fmaf( p, r * r, r );
	float z2 = fmaf( WebLibmFloat( 0x3805FDF4u ), xexp, -poly );
	const float z1 = fmaf( WebLibmFloat( 0x3F317000u ), xexp, WebLibmFloat( webLibmLog128Lead[index] ) );
	z2 = z2 + WebLibmFloat( webLibmLog128Tail[index] );
	return z1 + z2;
}


// Double-precision UCRT functions (win-libm sin.asm, cos.asm, tan.asm FMA3
// paths and atan.c, atan2.c, asin.c, acos.c with MSVC's fused operations).
// platform.h routes the engine's float-argument calls to these on the web.
// __remainder_piby2_fma3: returns r and sets rr (tail) and region.
static ID_INLINE double WebLibmRemPiBy2( double ax, double &rr, int &region ) {
	const webLibmLargeReduction_t red = WebLibmReduceLargeBits( ax );
	region = red.region;
	unsigned long long r9 = red.next;
	int hsb = 63;
	while ( hsb > 0 && !( ( r9 >> hsb ) & 1 ) ) hsb--;
	long long rcx = 64 - hsb;
	r9 <<= ( rcx & 63 );
	r9 >>= 12;
	rcx += 52;
	const unsigned long long r11 = (unsigned long long)( red.biasedExp - rcx ) << 52;
	r9 |= red.sign;
	r9 |= r11;
	const double x = WebLibmDouble( red.head ), xx = WebLibmDouble( r9 );
	const double hx = WebLibmDouble( red.head & 0xfffffffff8000000ull );
	const double tx = x - hx;
	const double c = x * WebLibmDouble( 0x3ff921fb54442d18ull );
	double cc = hx * WebLibmDouble( 0x3ff921fb50000000ull );
	cc = cc - c;
	cc = fma( tx, WebLibmDouble( 0x3ff921fb50000000ull ), cc );
	cc = fma( hx, WebLibmDouble( 0x3e5110b460000000ull ), cc );
	cc = fma( tx, WebLibmDouble( 0x3e5110b460000000ull ), cc );
	const double t4 = fma( x, WebLibmDouble( 0x3c91a62633145c06ull ), xx * WebLibmDouble( 0x3ff921fb54442d18ull ) );
	cc = cc + t4;
	const double r = c + cc;
	rr = ( c - r ) + cc;
	return r;
}

// __remainder_piby2_fma3_bdl (Boldo-Daumas-Li) for |x| < 2e7.
static ID_INLINE double WebLibmRemPiBy2Bdl( double x, double &tail, int &region ) {
	const double sigma = WebLibmDouble( 0x4338000000000000ull );
	const double xc1 = WebLibmDouble( 0x3FF921FB54442D18ull ), xc2 = WebLibmDouble( 0x3C91A62633145C00ull ),
		xc3 = WebLibmDouble( 0x397B839A252049C0ull );
	double z = fma( x, WebLibmDouble( 0x3FE45F306DC9C883ull ), sigma );
	z = z - sigma;
	region = (int)z & 3;
	const double u = fma( -z, xc1, x );
	const double p1 = z * xc2;
	const double p2 = fma( z, xc2, -p1 );
	const double t1 = u - p1;
	const double t2 = ( u - t1 ) - p1;
	const double v1 = fma( -z, xc2, u );
	double v2 = t1 - v1;
	v2 = v2 + t2;
	v2 = v2 - p2;
	tail = fma( -z, xc3, v2 );
	return v1;
}

static ID_INLINE double WebLibmSinTail( double x, double xx ) {
	// sin(r + rr), |r + rr| <= pi/4 (sin.asm Lsin_fma3_calc_sin)
	const double x2 = x * x;
	double p = fma( WebLibmDouble( 0x3de5e0b2f9a43bb8ull ), x2, WebLibmDouble( 0xbe5ae600b42fdfa7ull ) );
	p = fma( p, x2, WebLibmDouble( 0x3ec71de3796cde01ull ) );
	p = fma( p, x2, WebLibmDouble( 0xbf2a01a019e83e5cull ) );
	p = fma( p, x2, WebLibmDouble( 0x3f81111111110bb3ull ) );
	const double x3 = x * x2;
	double t = x3 * p;
	t = xx * 0.5 - t;
	t = x2 * t;
	t = t - xx;
	t = fma( -x3, WebLibmDouble( 0xbfc5555555555555ull ), t );
	return x - t;
}

static ID_INLINE double WebLibmCosTail( double x, double xx ) {
	// cos(r + rr), |r + rr| <= pi/4 (sin.asm Lsin_fma3_calc_cos, cos.asm Lcos_piby4_compute)
	const double x2 = x * x;
	const double r = x2 * 0.5;
	const double t = 1.0 - r;
	double c = ( 1.0 - t ) - r;
	c = fma( -x, xx, c );
	const double x4 = x2 * x2;
	double p = fma( WebLibmDouble( 0xbDA907DB47258AA7ull ), x2, WebLibmDouble( 0x3E21EEB690382EECull ) );
	p = fma( p, x2, WebLibmDouble( 0xbE927E4FA17F667Bull ) );
	p = fma( p, x2, WebLibmDouble( 0x3EFA01A019F4EC91ull ) );
	p = fma( p, x2, WebLibmDouble( 0xbf56c16c16c16967ull ) );
	p = fma( p, x2, WebLibmDouble( 0x3fa5555555555555ull ) );
	p = fma( p, x4, c );
	return p + t;
}

static ID_INLINE double WebLibmReduceDouble( double ax, double &tail, int &region ) {
	if ( WebLibmBits( ax ) >= 0x417312D000000000ull ) return WebLibmRemPiBy2( ax, tail, region );
	return WebLibmRemPiBy2Bdl( ax, tail, region );
}

// sin.asm, FMA3 path.
static ID_INLINE double WebSin( double x ) {
	const unsigned long long ux = WebLibmBits( x ), ax = ux & 0x7fffffffffffffffull;
	if ( ax < 0x3FE921FB54442D18ull ) {
		if ( ax >= 0x3f20000000000000ull ) {
			const double x2 = x * x;
			double p = fma( WebLibmDouble( 0x3de5e0b2f9a43bb8ull ), x2, WebLibmDouble( 0xbe5ae600b42fdfa7ull ) );
			p = fma( p, x2, WebLibmDouble( 0x3ec71de3796cde01ull ) );
			p = fma( p, x2, WebLibmDouble( 0xbf2a01a019e83e5cull ) );
			p = fma( p, x2, WebLibmDouble( 0x3f81111111110bb3ull ) );
			const double x3 = x * x2;
			p = fma( p, x2, WebLibmDouble( 0xbfc5555555555555ull ) );
			return fma( x3, p, x );
		}
		if ( ax >= 0x3e40000000000000ull ) return fma( -( x * x * x ), WebLibmDouble( 0x3FC5555555555555ull ), x );
		return x;
	}
	if ( ax >= 0x7ff0000000000000ull ) {
		// _sin_special: NaN is quieted, infinity is invalid.
		return WebLibmDouble( ( ax & 0x000fffffffffffffull ) ? ( ux | 0x0008000000000000ull ) : 0xfff8000000000000ull );
	}
	double tail;
	int region;
	const double r = WebLibmReduceDouble( WebLibmDouble( ax ), tail, region );
	double result = ( region & 1 ) ? WebLibmCosTail( r, tail ) : WebLibmSinTail( r, tail );
	unsigned long long sign = ( region & 2 ) ? 0x8000000000000000ull : 0;
	sign ^= ux & 0x8000000000000000ull;
	return WebLibmDouble( WebLibmBits( result ) ^ sign );
}

// cos.asm, FMA3 path.
static ID_INLINE double WebCos( double x ) {
	const unsigned long long ux = WebLibmBits( x ), ax = ux & 0x7fffffffffffffffull;
	if ( ax <= 0x3FE921FB54442D18ull ) {
		if ( ax >= 0x3f20000000000000ull ) {
			const double x2 = x * x;
			double p = fma( WebLibmDouble( 0xbDA907DB47258AA7ull ), x2, WebLibmDouble( 0x3E21EEB690382EECull ) );
			p = fma( p, x2, WebLibmDouble( 0xbE927E4FA17F667Bull ) );
			p = fma( p, x2, WebLibmDouble( 0x3EFA01A019F4EC91ull ) );
			p = fma( p, x2, WebLibmDouble( 0xbf56c16c16c16967ull ) );
			p = fma( p, x2, WebLibmDouble( 0x3fa5555555555555ull ) );
			p = fma( p, x2, -0.5 );
			return fma( p, x2, 1.0 );
		}
		if ( ax >= 0x3e40000000000000ull ) return fma( -( x * 0.5 ), x, 1.0 );
		return 1.0;
	}
	if ( ax >= 0x7ff0000000000000ull ) {
		return WebLibmDouble( ( ax & 0x000fffffffffffffull ) ? ( ux | 0x0008000000000000ull ) : 0xfff8000000000000ull );
	}
	double tail;
	int region;
	const double r = WebLibmReduceDouble( WebLibmDouble( ax ), tail, region );
	double result = ( region & 1 ) ? WebLibmSinTail( r, tail ) : WebLibmCosTail( r, tail );
	if ( ( region + 1 ) & 2 ) result = -result;
	return result;
}

// tan.asm, FMA3 path.
static ID_INLINE double WebLibmTanP( double r ) {
	return fma( fma( WebLibmDouble( 0x3F2D5DAF289C385Aull ), r, WebLibmDouble( 0xBF977C24C7569ABBull ) ), r, WebLibmDouble( 0x3FD7D50F6638564Aull ) );
}
static ID_INLINE double WebLibmTanQ( double r ) {
	double q = fma( WebLibmDouble( 0xBF2E7517EF6D98F8ull ), r, WebLibmDouble( 0x3F9AB0F4F80A0ACFull ) );
	q = fma( q, r, WebLibmDouble( 0xBFE08046499EB90Full ) );
	return fma( q, r, WebLibmDouble( 0x3FF1DFCB8CAA40B8ull ) );
}

static ID_INLINE double WebTan( double xin ) {
	const double piby4_lead = WebLibmDouble( 0x3FE921FB54442D18ull ), piby4_tail = WebLibmDouble( 0x3C81A62633145C06ull );
	const double p68 = WebLibmDouble( 0x3FE5C28F5C28F5C3ull );
	const unsigned long long ux = WebLibmBits( xin ), ax = ux & 0x7fffffffffffffffull;
	if ( ax < 0x3FE921FB54442D18ull ) {
		double x = xin, transform = 0.0;
		if ( x > p68 ) {
			transform = 1.0;
			x = piby4_lead - x;
			x = x + piby4_tail;
		} else if ( !( x >= -p68 ) ) {
			transform = -1.0;
			x = piby4_lead + x;
			x = x + piby4_tail;
		}
		const double r = x * x;
		double r3 = WebLibmTanP( r ) / WebLibmTanQ( r );
		r3 = r3 * r;
		const double t = fma( x, r3, x );
		if ( transform == 0.0 ) return t;
		const double d = t / ( t + 1.0 );
		return fma( -d, 2.0, 1.0 ) * transform;
	}
	if ( ax >= 0x7ff0000000000000ull ) {
		return WebLibmDouble( ( ax & 0x000fffffffffffffull ) ? ( ux | 0x0008000000000000ull ) : 0xfff8000000000000ull );
	}
	double xx;
	int region;
	double x = WebLibmReduceDouble( WebLibmDouble( ax ), xx, region );
	double transform = 0.0;
	if ( x > p68 ) {
		transform = 1.0;
		x = piby4_lead - x;
		const double xl = piby4_tail - xx;
		x = x + xl;
		xx = 0.0;
	} else if ( !( x >= -p68 ) ) {
		transform = -1.0;
		x = piby4_lead + x;
		const double xl = piby4_tail + xx;
		x = x + xl;
		xx = 0.0;
	}
	const double r = fma( xx * x, 2.0, x * x );
	double t2 = WebLibmTanP( r ) / WebLibmTanQ( r );
	t2 = t2 * r;
	t2 = fma( t2, x, xx );
	const double t = x + t2;
	double result;
	if ( transform != 0.0 ) {
		if ( region & 1 ) {
			const double d = t / ( t - 1.0 );
			result = fma( d, 2.0, -1.0 ) * transform;
		} else {
			const double d = t / ( t + 1.0 );
			result = fma( -d, 2.0, 1.0 ) * transform;
		}
	} else if ( region & 1 ) {
		const double z1 = WebLibmDouble( WebLibmBits( t ) & 0xffffffff00000000ull );
		const double z2 = t2 - ( z1 - x );
		const double trec = -1.0 / t;
		const double trecTop = WebLibmDouble( WebLibmBits( trec ) & 0xffffffff00000000ull );
		double u = fma( z1, trecTop, 1.0 );
		u = fma( z2, trecTop, u );
		result = fma( u, trec, trecTop );
	} else {
		result = t;
	}
	return WebLibmDouble( WebLibmBits( result ) ^ ( ux & 0x8000000000000000ull ) );
}

// atan.c (double), with the fused operations MSVC generates.
static ID_INLINE double WebAtan( double xin ) {
	const double piby2 = 1.5707963267948966e+00;
	double x = xin, chi, clo, v, s, q, z;
	const unsigned long long ux = WebLibmBits( x ), aux = ux & ~0x8000000000000000ull;
	const bool xneg = ( ux != aux );
	v = xneg ? -x : x;
	if ( aux > 0x4003800000000000ull ) {
		if ( aux > 0x7ff0000000000000ull ) return WebLibmDouble( ux | 0x0008000000000000ull );
		// The source compares v with the integer 0x4370000000000000 (about 4.85e18).
		if ( v > (double)0x4370000000000000ull ) return xneg ? -piby2 : piby2;
		x = -1.0 / v;
		chi = WebLibmDouble( 0x3ff921fb54442d18ull );
		clo = WebLibmDouble( 0x3c91a62633145c06ull );
	} else if ( aux > 0x3ff3000000000000ull ) {
		x = ( v - 1.5 ) / fma( 1.5, v, 1.0 );
		chi = WebLibmDouble( 0x3fef730bd281f69bull );
		clo = WebLibmDouble( 0x3c7007887af0cbbcull );
	} else if ( aux > 0x3fe6000000000000ull ) {
		x = ( v - 1.0 ) / ( 1.0 + v );
		chi = WebLibmDouble( 0x3fe921fb54442d18ull );
		clo = WebLibmDouble( 0x3c81a62633145c06ull );
	} else if ( aux > 0x3fdc000000000000ull ) {
		x = fma( 2.0, v, -1.0 ) / ( 2.0 + v );
		chi = WebLibmDouble( 0x3fddac670561bb4full );
		clo = WebLibmDouble( 0x3c7a2b7f222f65e0ull );
	} else {
		x = v;
		chi = 0.0;
		clo = 0.0;
	}
	s = x * x;
	const double p = fma( fma( fma( fma( 0.142316903342317766e-3, s, 0.304455919504853031e-1 ), s, 0.220638780716667420e0 ), s,
		0.447677206805497472e0 ), s, 0.268297920532545909e0 );
	const double d = fma( fma( fma( fma( 0.389525873944742195e-1, s, 0.424602594203847109e0 ), s, 0.141254259931958921e1 ), s,
		0.182596787737507063e1 ), s, 0.804893761597637733e0 );
	q = x * s * p / d;
	z = chi - ( ( q - clo ) - x );
	if ( xneg ) z = -z;
	return z;
}

static const unsigned long long webLibmAtanJby256Lead[241] = {
	0x3faff55b00000000ull, 0x3fb0f99e00000000ull, 0x3fb1f86d00000000ull, 0x3fb2f71900000000ull,
	0x3fb3f59f00000000ull, 0x3fb4f3fd00000000ull, 0x3fb5f23200000000ull, 0x3fb6f03b00000000ull,
	0x3fb7ee1800000000ull, 0x3fb8ebc500000000ull, 0x3fb9e94100000000ull, 0x3fbae68a00000000ull,
	0x3fbbe39e00000000ull, 0x3fbce07c00000000ull, 0x3fbddd2100000000ull, 0x3fbed98c00000000ull,
	0x3fbfd5ba00000000ull, 0x3fc068d500000000ull, 0x3fc0e6ad00000000ull, 0x3fc1646500000000ull,
	0x3fc1e1fa00000000ull, 0x3fc25f6e00000000ull, 0x3fc2dcbd00000000ull, 0x3fc359e800000000ull,
	0x3fc3d6ee00000000ull, 0x3fc453ce00000000ull, 0x3fc4d08700000000ull, 0x3fc54d1800000000ull,
	0x3fc5c98100000000ull, 0x3fc645bf00000000ull, 0x3fc6c1d400000000ull, 0x3fc73dbd00000000ull,
	0x3fc7b97b00000000ull, 0x3fc8350b00000000ull, 0x3fc8b06e00000000ull, 0x3fc92ba300000000ull,
	0x3fc9a6a800000000ull, 0x3fca217e00000000ull, 0x3fca9c2300000000ull, 0x3fcb169600000000ull,
	0x3fcb90d700000000ull, 0x3fcc0ae500000000ull, 0x3fcc84bf00000000ull, 0x3fccfe6500000000ull,
	0x3fcd77d500000000ull, 0x3fcdf11000000000ull, 0x3fce6a1400000000ull, 0x3fcee2e100000000ull,
	0x3fcf5b7500000000ull, 0x3fcfd3d100000000ull, 0x3fd025fa00000000ull, 0x3fd061ee00000000ull,
	0x3fd09dc500000000ull, 0x3fd0d97e00000000ull, 0x3fd1151a00000000ull, 0x3fd1509700000000ull,
	0x3fd18bf500000000ull, 0x3fd1c73500000000ull, 0x3fd2025500000000ull, 0x3fd23d5600000000ull,
	0x3fd2783700000000ull, 0x3fd2b2f700000000ull, 0x3fd2ed9800000000ull, 0x3fd3281800000000ull,
	0x3fd3627700000000ull, 0x3fd39cb400000000ull, 0x3fd3d6d100000000ull, 0x3fd410cb00000000ull,
	0x3fd44aa400000000ull, 0x3fd4845a00000000ull, 0x3fd4bdee00000000ull, 0x3fd4f75f00000000ull,
	0x3fd530ad00000000ull, 0x3fd569d800000000ull, 0x3fd5a2e000000000ull, 0x3fd5dbc300000000ull,
	0x3fd6148400000000ull, 0x3fd64d1f00000000ull, 0x3fd6859700000000ull, 0x3fd6bdea00000000ull,
	0x3fd6f61900000000ull, 0x3fd72e2200000000ull, 0x3fd7660700000000ull, 0x3fd79dc600000000ull,
	0x3fd7d56000000000ull, 0x3fd80cd400000000ull, 0x3fd8442200000000ull, 0x3fd87b4b00000000ull,
	0x3fd8b24d00000000ull, 0x3fd8e92900000000ull, 0x3fd91fde00000000ull, 0x3fd9566d00000000ull,
	0x3fd98cd500000000ull, 0x3fd9c31600000000ull, 0x3fd9f93000000000ull, 0x3fda2f2300000000ull,
	0x3fda64ee00000000ull, 0x3fda9a9200000000ull, 0x3fdad00f00000000ull, 0x3fdb056400000000ull,
	0x3fdb3a9100000000ull, 0x3fdb6f9600000000ull, 0x3fdba47300000000ull, 0x3fdbd92800000000ull,
	0x3fdc0db400000000ull, 0x3fdc421900000000ull, 0x3fdc765500000000ull, 0x3fdcaa6800000000ull,
	0x3fdcde5300000000ull, 0x3fdd121500000000ull, 0x3fdd45ae00000000ull, 0x3fdd791f00000000ull,
	0x3fddac6700000000ull, 0x3fdddf8500000000ull, 0x3fde127b00000000ull, 0x3fde454800000000ull,
	0x3fde77eb00000000ull, 0x3fdeaa6500000000ull, 0x3fdedcb600000000ull, 0x3fdf0ede00000000ull,
	0x3fdf40dd00000000ull, 0x3fdf72b200000000ull, 0x3fdfa45d00000000ull, 0x3fdfd5e000000000ull,
	0x3fe0039c00000000ull, 0x3fe01c3400000000ull, 0x3fe034b700000000ull, 0x3fe04d2500000000ull,
	0x3fe0657e00000000ull, 0x3fe07dc300000000ull, 0x3fe095f300000000ull, 0x3fe0ae0e00000000ull,
	0x3fe0c61400000000ull, 0x3fe0de0500000000ull, 0x3fe0f5e200000000ull, 0x3fe10daa00000000ull,
	0x3fe1255d00000000ull, 0x3fe13cfb00000000ull, 0x3fe1548500000000ull, 0x3fe16bfa00000000ull,
	0x3fe1835a00000000ull, 0x3fe19aa500000000ull, 0x3fe1b1dc00000000ull, 0x3fe1c8fe00000000ull,
	0x3fe1e00b00000000ull, 0x3fe1f70400000000ull, 0x3fe20de800000000ull, 0x3fe224b700000000ull,
	0x3fe23b7100000000ull, 0x3fe2521700000000ull, 0x3fe268a900000000ull, 0x3fe27f2600000000ull,
	0x3fe2958e00000000ull, 0x3fe2abe200000000ull, 0x3fe2c22100000000ull, 0x3fe2d84c00000000ull,
	0x3fe2ee6200000000ull, 0x3fe3046400000000ull, 0x3fe31a5200000000ull, 0x3fe3302b00000000ull,
	0x3fe345f000000000ull, 0x3fe35ba000000000ull, 0x3fe3713d00000000ull, 0x3fe386c500000000ull,
	0x3fe39c3900000000ull, 0x3fe3b19800000000ull, 0x3fe3c6e400000000ull, 0x3fe3dc1c00000000ull,
	0x3fe3f13f00000000ull, 0x3fe4064f00000000ull, 0x3fe41b4a00000000ull, 0x3fe4303200000000ull,
	0x3fe4450600000000ull, 0x3fe459c600000000ull, 0x3fe46e7200000000ull, 0x3fe4830a00000000ull,
	0x3fe4978f00000000ull, 0x3fe4ac0000000000ull, 0x3fe4c05e00000000ull, 0x3fe4d4a800000000ull,
	0x3fe4e8de00000000ull, 0x3fe4fd0100000000ull, 0x3fe5111000000000ull, 0x3fe5250c00000000ull,
	0x3fe538f500000000ull, 0x3fe54cca00000000ull, 0x3fe5608d00000000ull, 0x3fe5743c00000000ull,
	0x3fe587d800000000ull, 0x3fe59b6000000000ull, 0x3fe5aed600000000ull, 0x3fe5c23900000000ull,
	0x3fe5d58900000000ull, 0x3fe5e8c600000000ull, 0x3fe5fbf000000000ull, 0x3fe60f0800000000ull,
	0x3fe6220d00000000ull, 0x3fe634ff00000000ull, 0x3fe647de00000000ull, 0x3fe65aab00000000ull,
	0x3fe66d6600000000ull, 0x3fe6800e00000000ull, 0x3fe692a400000000ull, 0x3fe6a52700000000ull,
	0x3fe6b79800000000ull, 0x3fe6c9f700000000ull, 0x3fe6dc4400000000ull, 0x3fe6ee7f00000000ull,
	0x3fe700a700000000ull, 0x3fe712be00000000ull, 0x3fe724c300000000ull, 0x3fe736b600000000ull,
	0x3fe7489700000000ull, 0x3fe75a6700000000ull, 0x3fe76c2400000000ull, 0x3fe77dd100000000ull,
	0x3fe78f6b00000000ull, 0x3fe7a0f400000000ull, 0x3fe7b26c00000000ull, 0x3fe7c3d300000000ull,
	0x3fe7d52800000000ull, 0x3fe7e66c00000000ull, 0x3fe7f79e00000000ull, 0x3fe808c000000000ull,
	0x3fe819d000000000ull, 0x3fe82ad000000000ull, 0x3fe83bbe00000000ull, 0x3fe84c9c00000000ull,
	0x3fe85d6900000000ull, 0x3fe86e2500000000ull, 0x3fe87ed000000000ull, 0x3fe88f6b00000000ull,
	0x3fe89ff500000000ull, 0x3fe8b06f00000000ull, 0x3fe8c0d900000000ull, 0x3fe8d13200000000ull,
	0x3fe8e17a00000000ull, 0x3fe8f1b300000000ull, 0x3fe901db00000000ull, 0x3fe911f300000000ull,
	0x3fe921fb00000000ull,
};
static const unsigned long long webLibmAtanJby256Tail[241] = {
	0x3e56e59fbd38db2cull, 0x3e64e3aa54dedf96ull, 0x3e67e105ab1bda88ull, 0x3e48c5254d013fd0ull,
	0x3e2cf8ab3ad62670ull, 0x3e59dca4bec80468ull, 0x3e53f4b5ec98a8daull, 0x3e6b9d49619d81feull,
	0x3e43017887460934ull, 0x3e511e3eca0b9944ull, 0x3e54f3f73c5a332eull, 0x3e5c71c8ae0e00a6ull,
	0x3e67cde0f86fbdc7ull, 0x3e570f328c889c72ull, 0x3e5c07ae9b994efeull, 0x3e40c8021d7b1698ull,
	0x3e635585edb8cb22ull, 0x3e70842567b30e96ull, 0x3e799e811031472eull, 0x3e6041821416bceeull,
	0x3e7f6086e4dc96f4ull, 0x3e471a535c5f1b58ull, 0x3e765f743fe63ca1ull, 0x3e7dbd733472d014ull,
	0x3e7d18cc4d8b0d1dull, 0x3e78c12553c8fb29ull, 0x3e753b49e2e8f991ull, 0x3e77422ae148c141ull,
	0x3e4e3ec269df56a8ull, 0x3e7ff6754e7e0ac9ull, 0x3e7131267b1b5aadull, 0x3e7d14fa403a94bcull,
	0x3e62f396c089a3d8ull, 0x3e7c731d78fa95bbull, 0x3e7c50f385177399ull, 0x3e6f41409c6f2c20ull,
	0x3e7d2d90c4c39ec0ull, 0x3e680420696f2106ull, 0x3e4b40327943a2e8ull, 0x3e65d35e02f3d2a2ull,
	0x3e64a498288117b0ull, 0x3e635da119afb324ull, 0x3e714e85cdb9a908ull, 0x3e638754e5547b9aull,
	0x3e7be40ae6ce3246ull, 0x3e70c993b3bea7e7ull, 0x3e71d2dd89ac3359ull, 0x3e61476603332c46ull,
	0x3e7f25901bac55b7ull, 0x3e7f881b7c826e28ull, 0x3e7441996d698d20ull, 0x3e8407ac521ea089ull,
	0x3e82fb0c6c4b1723ull, 0x3e8ca135966a3e18ull, 0x3e6b1218e4d646e4ull, 0x3e6d4e72a350d288ull,
	0x3e84617e2f04c329ull, 0x3e6096ec41e82650ull, 0x3e79f91f25773e6eull, 0x3e659c0820f1d674ull,
	0x3e602bf7a2df1064ull, 0x3e8fb36bfc40508full, 0x3e7ea08f3f8dc892ull, 0x3e73ed6254656a0eull,
	0x3e6b83f5e5e69c58ull, 0x3e8d6ec2af768592ull, 0x3e6493889a226f94ull, 0x3e85ad8fa65279baull,
	0x3e6b615784d45434ull, 0x3e809a184368f145ull, 0x3e761a2439b0d91cull, 0x3e7ce1a65e39a978ull,
	0x3e832a39a93b6a66ull, 0x3e81c3699af804e7ull, 0x3e575e0f4e44ede8ull, 0x3e8f77ced1a7a83bull,
	0x3e284e7f0cb1b500ull, 0x3e8ec6b838b02dfeull, 0x3e83ebf4dfbeda87ull, 0x3e89397aed9cb475ull,
	0x3e707937bc239c54ull, 0x3e8aa754553131b6ull, 0x3e74a05d407c45dcull, 0x3e8132231a206dd0ull,
	0x3e72d8ecfdd69c88ull, 0x3e7a852c74218606ull, 0x3e871bf2baeebb50ull, 0x3e483d7db7491820ull,
	0x3e6ca50d92b6da14ull, 0x3e56f5cde8530298ull, 0x3e7f343198910740ull, 0x3e70e8d241ccd80aull,
	0x3e71535ac619e6c8ull, 0x3e77316041c36cd2ull, 0x3e7985a000637d8eull, 0x3e6f2f29858c0a68ull,
	0x3e8879847f96d909ull, 0x3e8ab3d319e12e42ull, 0x3e75088162dfc4c2ull, 0x3e605749a1cd9d8cull,
	0x3e5da65c6c6b8618ull, 0x3e6739bf7df1ad64ull, 0x3e6bc31252aa3340ull, 0x3e5e528191ad3aa8ull,
	0x3e8929d93df19f18ull, 0x3e5ff11eb693a080ull, 0x3e455ae3f145a3a0ull, 0x3e7cbcd8c6c0ca82ull,
	0x3e70cb04d425d304ull, 0x3e79adfcab5be678ull, 0x3e893d90c5662508ull, 0x3e768489bd35ff40ull,
	0x3e3586ed3da2b7e0ull, 0x3e87604d2e850eeeull, 0x3e7ac1d12bfb53d8ull, 0x3e39b3d468274740ull,
	0x3e7fc5d68d10e53cull, 0x3e88f9e51884becbull, 0x3e8a87f0869c06d1ull, 0x3e831e7279f685faull,
	0x3e46a8282f9719b0ull, 0x3e60d2724a8a44e0ull, 0x3e8a60524b11ad4eull, 0x3e575fdf832750f0ull,
	0x3e8cf06902e4cd36ull, 0x3e6e82422d4f6d10ull, 0x3e524a091063e6c0ull, 0x3e78a1a172dc6f38ull,
	0x3e929b6619f8a92dull, 0x3e79274d9c1b70c8ull, 0x3e50c34b1fbb7930ull, 0x3e6639866c20eb50ull,
	0x3e86d6d0f6832e9eull, 0x3e9af54def99f25eull, 0x3e916cfc52a00262ull, 0x3e8dcc1e83569c32ull,
	0x3e937f7a551ed425ull, 0x3e9f6360adc98887ull, 0x3e92c6ec8d35a2c1ull, 0x3e8bd44df84cb036ull,
	0x3e9117cf826e310eull, 0x3e9ca533f332cfc9ull, 0x3e90f208509dbc2eull, 0x3e8cd07d93c945deull,
	0x3e957bdfd67e6d72ull, 0x3e7aab89c516c658ull, 0x3e63e823b1a1b8a0ull, 0x3e8307464a9d6d3cull,
	0x3e9c5993cd438843ull, 0x3e9ba2fca02ab554ull, 0x3e801a5b6983a268ull, 0x3e6273d1b350efc8ull,
	0x3e864c238c37b0c6ull, 0x3e6aded07370a300ull, 0x3e878091197eb47eull, 0x3e74b0f245e0dabcull,
	0x3e9080d9794e2eafull, 0x3e8d4ec242b60c76ull, 0x3e4221d2f940caa0ull, 0x3e7cdbc42b2bba5cull,
	0x3e6cce37bb440840ull, 0x3e96c1d999cf1dd0ull, 0x3e5bed8a07eb0870ull, 0x3e769ed88f490e3cull,
	0x3e6cd41719b73ef0ull, 0x3e9cbc4ac95b41b7ull, 0x3e9238f1b890f5d7ull, 0x3e750c4282259cc4ull,
	0x3e9713d2de87b3e2ull, 0x3e81d5a7d2255276ull, 0x3e9c0dfd48227ac1ull, 0x3e91c964dab76753ull,
	0x3e86de56d5704496ull, 0x3e84aeb71fd19968ull, 0x3e8fbf91c57b1918ull, 0x3e9d6bef7fbe5d9aull,
	0x3e9464d3dc249066ull, 0x3e9638e2ec4d9073ull, 0x3e716f4a7247ea7cull, 0x3e31a0a740f1d440ull,
	0x3e86edbb0114a33cull, 0x3e7dbee8bf1d513cull, 0x3e95b8bdb0248f73ull, 0x3e97de3d3f5eac64ull,
	0x3e8ee24187ae448aull, 0x3e9e06c591ec5192ull, 0x3e74e3861a332738ull, 0x3e7a9599dcc2bfe4ull,
	0x3e6f732fbad43468ull, 0x3e9eb9f573b727d9ull, 0x3e98b212a2eb9897ull, 0x3e9384884c167215ull,
	0x3e90e2d363020051ull, 0x3e92820879fbd022ull, 0x3e9a1ab9893e4b30ull, 0x3e82d1b817a24478ull,
	0x3e615d7b8ded4878ull, 0x3e78968f9db3a5e4ull, 0x3e971c4171fe135full, 0x3e96d80f605d0d8cull,
	0x3e7c91f043691590ull, 0x3e839f8a15fce2b2ull, 0x3e455beda9d94b80ull, 0x3e8b12c15d60949aull,
	0x3e924167b312bfe3ull, 0x3e90ab8633070277ull, 0x3e854554ebbc80eeull, 0x3e60204aef5a4bb8ull,
	0x3e98af08c679cf2cull, 0x3e90852a330ae6c8ull, 0x3e86d3eb9ec32916ull, 0x3e8685cb7fcbbafeull,
	0x3e91f751c1e0bd95ull, 0x3e5705b1b0f72560ull, 0x3e9b98d8d808ca92ull, 0x3e62ea22c75cc980ull,
	0x3e97aba62bca0350ull, 0x3e9d73833442278cull, 0x3e95a5ca1fb18bf9ull, 0x3e61a6092b6ecf28ull,
	0x3e744fd049aac104ull, 0x3e2c114fd8df5180ull, 0x3e95972f130feae5ull, 0x3e7ca034a55fe198ull,
	0x3e96e2b149990227ull, 0x3e7b00000294592cull, 0x3e98b9bdc442620eull, 0x3e8d94fdfabf3e4eull,
	0x3e85db30b145ad9aull, 0x3e8e3e1eb95022b0ull, 0x3e9d5b8b45442bd6ull, 0x3e97a046231ecd2eull,
	0x3e9feafe3ef55232ull, 0x3e9839e7bfd78267ull, 0x3e645cf49d6fa900ull, 0x3e4be3132b27f380ull,
	0x3e9533980bb84f9full, 0x3e5889e2ce3ba390ull, 0x3e7f7778c3ad0cc8ull, 0x3e846660cec4eba2ull,
	0x3e85110b4611a626ull,
};


// scaleUpDouble1024 / scaleDouble_1 / scaleDouble_2 / scaleDownDouble from libm_inlines.h.
static ID_INLINE unsigned long long WebLibmScaleUp1024( unsigned long long ux ) {
	if ( ( ux & 0x7ff0000000000000ull ) == 0 ) {
		double y = WebLibmDouble( ux | 0x4010000000000000ull );
		if ( ux & 0x8000000000000000ull ) y += 4.0;
		else y -= 4.0;
		return WebLibmBits( y );
	}
	return ux + 0x4000000000000000ull;
}
static ID_INLINE double WebLibmScale1( double x, int n ) {
	return x * WebLibmDouble( (unsigned long long)( (long long)n + 1023 ) << 52 );
}
static ID_INLINE double WebLibmScale2( double x, int n ) {
	const int n1 = n / 2, n2 = n - n1;
	return ( x * WebLibmDouble( (unsigned long long)( (long long)n1 + 1023 ) << 52 ) ) *
		WebLibmDouble( (unsigned long long)( (long long)n2 + 1023 ) << 52 );
}
static ID_INLINE unsigned long long WebLibmScaleDown( unsigned long long ux, int k ) {
	const unsigned long long xsign = ux & 0x8000000000000000ull, ax = ux & ~0x8000000000000000ull;
	const int n = (int)( ( ax & 0x7ff0000000000000ull ) >> 52 ) - k;
	unsigned long long uy;
	if ( n > 0 ) {
		uy = ( ax & ~0x7ff0000000000000ull ) | ( (unsigned long long)n << 52 );
	} else {
		uy = ( ax & ~0x7ff0000000000000ull ) | 0x0010000000000000ull;
		const int shift = 1 - n;
		if ( shift > 53 + 1 ) {
			uy = 0;
		} else {
			uy >>= shift - 1;
			uy = ( uy >> 1 ) + ( uy & 1 );
		}
	}
	return uy | xsign;
}

// atan2.c (double), with the fused operations MSVC generates. As in the
// source, the x == 0 branch does not return.
static ID_INLINE double WebAtan2( double y, double x ) {
	const double pi = WebLibmDouble( 0x400921fb54442d18ull ), piby2 = WebLibmDouble( 0x3ff921fb54442d18ull ),
		piby4 = WebLibmDouble( 0x3fe921fb54442d18ull ), three_piby4 = WebLibmDouble( 0x4002d97c7f3321d2ull ),
		pi_head = WebLibmDouble( 0x400921fb50000000ull ), pi_tail = WebLibmDouble( 0x3e6110b4611a6263ull ),
		piby2_head = WebLibmDouble( 0x3ff921fb54442d18ull ), piby2_tail = WebLibmDouble( 0x3c91a62633145c07ull );
	double u, v, vbyu, q1, q2, s, u1, vu1, u2, vu2, uu, c, r;
	unsigned long long ux = WebLibmBits( x ), uy = WebLibmBits( y );
	const unsigned long long aux = ux & ~0x8000000000000000ull, auy = uy & ~0x8000000000000000ull;
	int xexp = (int)( ( ux & 0x7ff0000000000000ull ) >> 52 ), yexp = (int)( ( uy & 0x7ff0000000000000ull ) >> 52 );
	const unsigned long long xneg = ux & 0x8000000000000000ull, yneg = uy & 0x8000000000000000ull;
	const bool yzero = ( auy == 0 );
	const bool xnan = ( aux > 0x7ff0000000000000ull ), ynan = ( auy > 0x7ff0000000000000ull );
	const bool xinf = ( aux == 0x7ff0000000000000ull ), yinf = ( auy == 0x7ff0000000000000ull );
	int diffexp = yexp - xexp;
	if ( xnan ) return WebLibmDouble( ux | 0x0008000000000000ull );
	if ( ynan ) return WebLibmDouble( uy | 0x0008000000000000ull );
	if ( yzero ) {
		if ( xneg ) return yneg ? -pi : pi;
		return y;
	}
	if ( xexp < 1021 && yexp < 1021 ) {
		ux = WebLibmScaleUp1024( ux );
		uy = WebLibmScaleUp1024( uy );
		x = WebLibmDouble( ux );
		y = WebLibmDouble( uy );
		xexp = (int)( ( ux & 0x7ff0000000000000ull ) >> 52 );
		yexp = (int)( ( uy & 0x7ff0000000000000ull ) >> 52 );
		diffexp = yexp - xexp;
	}
	if ( diffexp > 56 ) {
		return yneg ? -piby2 : piby2;
	} else if ( diffexp < -28 && !xneg ) {
		if ( diffexp < -1074 ) return yneg ? -0.0 : 0.0;
		if ( diffexp < -1022 ) {
			y = WebLibmScale1( y, 100 );
			y /= x;
			return WebLibmDouble( WebLibmScaleDown( WebLibmBits( y ), 100 ) );
		}
		return y / x;
	} else if ( diffexp < -56 && xneg ) {
		return yneg ? -pi : pi;
	} else if ( yinf && xinf ) {
		if ( xneg ) return yneg ? -three_piby4 : three_piby4;
		return yneg ? -piby4 : piby4;
	}
	u = xneg ? -x : x;
	v = yneg ? -y : y;
	const bool swap_vu = ( u < v );
	if ( swap_vu ) { uu = u; u = v; v = uu; }
	vbyu = v / u;
	if ( vbyu > 0.0625 ) {
		const int index = (int)( 256 * vbyu + 0.5 );
		q1 = WebLibmDouble( webLibmAtanJby256Lead[index - 16] );
		q2 = WebLibmDouble( webLibmAtanJby256Tail[index - 16] );
		c = index * 1. / 256;
		const int m = (int)( ( WebLibmBits( u ) & 0x7ff0000000000000ull ) >> 52 ) - 1023;
		u = WebLibmScale2( u, -m );
		v = WebLibmScale2( v, -m );
		u1 = WebLibmDouble( 0xfffffffff8000000ull & WebLibmBits( u ) );
		u2 = u - u1;
		r = fma( -c, u2, fma( -c, u1, v ) ) / fma( c, v, u );
		s = r * r;
		q2 = fma( -r, s * fma( -s, 0.19999918038989143496, 0.33333333333224095522 ), q2 + r );
	} else if ( vbyu < 1.e-8 ) {
		q1 = 0.0;
		q2 = vbyu;
	} else {
		u1 = WebLibmDouble( 0xffffffff00000000ull & WebLibmBits( u ) );
		vu1 = WebLibmDouble( 0xffffffff00000000ull & WebLibmBits( vbyu ) );
		u2 = u - u1;
		vu2 = vbyu - vu1;
		q1 = 0.0;
		s = vbyu * vbyu;
		const double poly = fma( -s, fma( -s, fma( -s, fma( -s, 0.90029810285449784439E-01, 0.11110736283514525407 ),
			0.14285713561807169030 ), 0.19999999999393223405 ), 0.33333333333333170500 );
		q2 = vbyu + fma( -( vbyu * s ), poly, fma( -u, vu2, fma( -u2, vu1, fma( -u1, vu1, v ) ) ) / u );
	}
	if ( swap_vu ) { q1 = piby2_head - q1; q2 = piby2_tail - q2; }
	if ( xneg ) { q1 = pi_head - q1; q2 = pi_tail - q2; }
	q1 = q1 + q2;
	if ( yneg ) q1 = -q1;
	return q1;
}

// asin.c / acos.c (double): rational approximation u(r) shared by both.
static ID_INLINE double WebLibmAsinRational( double r ) {
	const double p = fma( fma( fma( fma( fma( 0.0000482901920344786991880522822991, r, 0.00109242697235074662306043804220 ), r,
		-0.0549989809235685841612020091328 ), r, 0.275558175256937652532686256258 ), r, -0.445017216867635649900123110649 ), r,
		0.227485835556935010735943483075 );
	const double q = fma( fma( fma( fma( 0.105869422087204370341222318533, r, -0.943639137032492685763471240072 ), r,
		2.76568859157270989520376345954 ), r, -3.28431505720958658909889444194 ), r, 1.36491501334161032038194214209 );
	return r * p / q;
}

static ID_INLINE double WebAsin( double x ) {
	const double piby2_tail = WebLibmDouble( 0x3c91a62633145c07ull ), hpiby2_head = WebLibmDouble( 0x3fe921fb54442d18ull ),
		piby2 = WebLibmDouble( 0x3ff921fb54442d18ull );
	const unsigned long long ux = WebLibmBits( x ), aux = ux & ~0x8000000000000000ull, xneg = ux & 0x8000000000000000ull;
	const int xexp = (int)( ( ux & 0x7ff0000000000000ull ) >> 52 ) - 1023;
	double y, s = 0.0, r, v;
	if ( aux > 0x7ff0000000000000ull ) return WebLibmDouble( ux | 0x0008000000000000ull );
	if ( xexp < -28 ) return x;
	if ( xexp >= 0 ) {
		if ( x == 1.0 ) return piby2;
		if ( x == -1.0 ) return -piby2;
		return WebLibmDouble( 0xfff8000000000000ull );
	}
	y = xneg ? -x : x;
	const bool transform = ( xexp >= -1 );
	if ( transform ) {
		r = 0.5 * ( 1.0 - y );
		s = sqrt( r );
		y = s;
	} else {
		r = y * y;
	}
	const double u = WebLibmAsinRational( r );
	if ( transform ) {
		const double s1 = WebLibmDouble( 0xffffffff00000000ull & WebLibmBits( s ) );
		const double c = fma( -s1, s1, r ) / ( s + s1 );
		const double p = fma( 2.0 * s, u, -fma( -2.0, c, piby2_tail ) );
		const double q = fma( -2.0, s1, hpiby2_head );
		v = hpiby2_head - ( p - q );
	} else {
		v = fma( y, u, y );
	}
	return xneg ? -v : v;
}

static ID_INLINE double WebAcos( double x ) {
	const double pi = WebLibmDouble( 0x400921fb54442d18ull ), piby2 = WebLibmDouble( 0x3ff921fb54442d18ull ),
		piby2_head = WebLibmDouble( 0x3ff921fb54442d18ull ), piby2_tail = WebLibmDouble( 0x3c91a62633145c07ull );
	const unsigned long long ux = WebLibmBits( x ), aux = ux & ~0x8000000000000000ull, xneg = ux & 0x8000000000000000ull;
	const int xexp = (int)( ( ux & 0x7ff0000000000000ull ) >> 52 ) - 1023;
	double y, s = 0.0, r;
	if ( aux > 0x7ff0000000000000ull ) return WebLibmDouble( ux | 0x0008000000000000ull );
	if ( xexp < -56 ) return piby2;
	if ( xexp >= 0 ) {
		if ( x == 1.0 ) return 0.0;
		if ( x == -1.0 ) return pi;
		return WebLibmDouble( 0xfff8000000000000ull );
	}
	y = xneg ? -x : x;
	const bool transform = ( xexp >= -1 );
	if ( transform ) {
		r = 0.5 * ( 1.0 - y );
		s = sqrt( r );
		y = s;
	} else {
		r = y * y;
	}
	const double u = WebLibmAsinRational( r );
	if ( transform ) {
		if ( xneg ) return fma( -2.0, s + fma( y, u, -piby2_tail ), pi );
		const double s1 = WebLibmDouble( 0xffffffff00000000ull & WebLibmBits( s ) );
		const double c = fma( -s1, s1, r ) / ( s + s1 );
		return 2.0 * s1 + fma( 2.0 * y, u, 2.0 * c );
	}
	return piby2_head - ( x - fma( -x, u, piby2_tail ) );
}

#endif
