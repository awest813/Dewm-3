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


#endif
