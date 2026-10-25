// Platform-independent binary64 maths, ported from musl libc's src/math.
// Sources: https://git.musl-libc.org/cgit/musl/tree/src/math/
// sin.c, cos.c, __sin.c, __cos.c, __rem_pio2.c, __rem_pio2_large.c,
// atan.c, atan2.c and scalbn.c; legacy fdlibm pow.c and exp.c (before
// musl's 2018 Arm replacements). See docs/GOLDEN.md for source details.
//
// musl as a whole is licensed under the following standard MIT license:
// Copyright © 2005-2020 Rich Felker, et al.
//
// Permission is hereby granted, free of charge, to any person obtaining
// a copy of this software and associated documentation files (the
// "Software"), to deal in the Software without restriction, including
// without limitation the rights to use, copy, modify, merge, publish,
// distribute, sublicense, and/or sell copies of the Software, and to
// permit persons to whom the Software is furnished to do so, subject to
// the following conditions:
//
// The above copyright notice and this permission notice shall be
// included in all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
// EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
// MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
// IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
// CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
// TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
// SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
//
// The fdlibm / FreeBSD msun routines carry these additional notices:
// ====================================================
// Copyright (C) 1993 by Sun Microsystems, Inc. All rights reserved.
//
// Developed at SunPro, a Sun Microsystems, Inc. business.
// Permission to use, copy, modify, and distribute this
// software is freely granted, provided that this notice
// is preserved.
// ====================================================
// Copyright (C) 1993 by Sun Microsystems, Inc. All rights reserved.
//
// Developed at SunSoft, a Sun Microsystems, Inc. business.
// Permission to use, copy, modify, and distribute this
// software is freely granted, provided that this notice
// is preserved.
// ====================================================
// Copyright (C) 2004 by Sun Microsystems, Inc. All rights reserved.
//
// Permission to use, copy, modify, and distribute this
// software is freely granted, provided that this notice
// is preserved.
// ====================================================

//! Fixed binary64 operation order, round-to-nearest-even, with no libm, FFI,
//! unsafe code, FMA contraction or target-specific implementation selection.
//! Rust's exact sqrt/floor/abs are used where musl calls those operations.
//! Floating-point exception flags and non-default rounding modes are outside
//! the engine contract; musl's FORCE_EVAL expressions only raising flags are
//! omitted. Domain errors use a canonical NaN since NaN payloads are not a
//! portable part of Rust's arithmetic contract. Finite engine inputs and
//! signed-zero/infinity results retain the original algorithms.

#![forbid(unsafe_code)]
#![allow(clippy::excessive_precision, clippy::approx_constant)]

fn high_word(x: f64) -> u32 {
    (x.to_bits() >> 32) as u32
}

fn with_high_word(x: f64, high: u32) -> f64 {
    f64::from_bits((u64::from(high) << 32) | (x.to_bits() & 0xffff_ffff))
}

fn without_low_word(x: f64) -> f64 {
    f64::from_bits(x.to_bits() & 0xffff_ffff_0000_0000)
}

// musl scalbn.c: exact power-of-two scaling, including subnormal outputs.
fn scalbn(mut x: f64, mut n: i32) -> f64 {
    const TWO1023: f64 = f64::from_bits(0x7fe0_0000_0000_0000);
    const TWO_NEG969: f64 = f64::from_bits(0x0360_0000_0000_0000);
    if n > 1023 {
        x *= TWO1023;
        n -= 1023;
        if n > 1023 {
            x *= TWO1023;
            n -= 1023;
            if n > 1023 {
                n = 1023;
            }
        }
    } else if n < -1022 {
        // Keep final n < -53 to avoid double rounding of subnormal results.
        x *= TWO_NEG969;
        n += 1022 - 53;
        if n < -1022 {
            x *= TWO_NEG969;
            n += 1022 - 53;
            if n < -1022 {
                n = -1022;
            }
        }
    }
    x * f64::from_bits(((1023 + n) as u64) << 52)
}

// musl __sin.c (FreeBSD k_sin.c): kernel on [-pi/4, pi/4], tail y.
fn kernel_sin(x: f64, y: f64, tail: bool) -> f64 {
    const S1: f64 = -1.66666666666666324348e-01;
    const S2: f64 = 8.33333333332248946124e-03;
    const S3: f64 = -1.98412698298579493134e-04;
    const S4: f64 = 2.75573137070700676789e-06;
    const S5: f64 = -2.50507602534068634195e-08;
    const S6: f64 = 1.58969099521155010221e-10;
    let z = x * x;
    let w = z * z;
    let r = S2 + z * (S3 + z * S4) + z * w * (S5 + z * S6);
    let v = z * x;
    if tail {
        x - ((z * (0.5 * y - v * r) - y) - v * S1)
    } else {
        x + v * (S1 + z * r)
    }
}

// musl __cos.c (FreeBSD k_cos.c): kernel on [-pi/4, pi/4], tail y.
fn kernel_cos(x: f64, y: f64) -> f64 {
    const C1: f64 = 4.16666666666666019037e-02;
    const C2: f64 = -1.38888888888741095749e-03;
    const C3: f64 = 2.48015872894767294178e-05;
    const C4: f64 = -2.75573143513906633035e-07;
    const C5: f64 = 2.08757232129817482790e-09;
    const C6: f64 = -1.13596475577881948265e-11;
    let z = x * x;
    let w = z * z;
    let r = z * (C1 + z * (C2 + z * C3)) + w * w * (C4 + z * (C5 + z * C6));
    let hz = 0.5 * z;
    let w = 1.0 - hz;
    w + (((1.0 - w) - hz) + (z * r - x * y))
}

/// musl sin.c, with full-range argument reduction.
pub fn sin(x: f64) -> f64 {
    let ix = high_word(x) & 0x7fff_ffff;
    if ix <= 0x3fe9_21fb {
        if ix < 0x3e50_0000 {
            return x;
        }
        return kernel_sin(x, 0.0, false);
    }
    if ix >= 0x7ff0_0000 {
        return f64::NAN;
    }
    let (n, y0, y1) = rem_pio2(x);
    match n & 3 {
        0 => kernel_sin(y0, y1, true),
        1 => kernel_cos(y0, y1),
        2 => -kernel_sin(y0, y1, true),
        _ => -kernel_cos(y0, y1),
    }
}

/// musl cos.c, with full-range argument reduction.
pub fn cos(x: f64) -> f64 {
    let ix = high_word(x) & 0x7fff_ffff;
    if ix <= 0x3fe9_21fb {
        if ix < 0x3e46_a09e {
            return 1.0;
        }
        return kernel_cos(x, 0.0);
    }
    if ix >= 0x7ff0_0000 {
        return f64::NAN;
    }
    let (n, y0, y1) = rem_pio2(x);
    match n & 3 {
        0 => kernel_cos(y0, y1),
        1 => -kernel_sin(y0, y1, true),
        2 => -kernel_cos(y0, y1),
        _ => kernel_sin(y0, y1, true),
    }
}

// musl __rem_pio2.c (FreeBSD e_rem_pio2.c, optimized by Bruce D. Evans).
// Return n and y0+y1 = x - n*pi/2; large inputs return n modulo 8.
fn rem_pio2(x: f64) -> (i32, f64, f64) {
    const TOINT: f64 = 1.5 / f64::EPSILON;
    const PIO4: f64 = f64::from_bits(0x3fe9_21fb_5444_2d18);
    const INVPIO2: f64 = 6.36619772367581382433e-01;
    const PIO2_1: f64 = 1.57079632673412561417e+00;
    const PIO2_1T: f64 = 6.07710050650619224932e-11;
    const PIO2_2: f64 = 6.07710050630396597660e-11;
    const PIO2_2T: f64 = 2.02226624879595063154e-21;
    const PIO2_3: f64 = 2.02226624871116645580e-21;
    const PIO2_3T: f64 = 8.47842766036889956997e-32;
    let sign = x.is_sign_negative();
    let ix = high_word(x) & 0x7fff_ffff;

    // The original goto medium skips quick reductions near cancellation.
    let quick_n = if ix <= 0x400f_6a7a {
        if ix & 0x000f_ffff == 0x0009_21fb {
            None
        } else if ix <= 0x4002_d97c {
            Some(1)
        } else {
            Some(2)
        }
    } else if ix <= 0x401c_463b {
        if ix <= 0x4015_fdbc {
            if ix == 0x4012_d97c {
                None
            } else {
                Some(3)
            }
        } else if ix == 0x4019_21fb {
            None
        } else {
            Some(4)
        }
    } else {
        None
    };
    if let Some(n) = quick_n {
        let n = if sign { -n } else { n };
        let z = x - n as f64 * PIO2_1;
        let y0 = z - n as f64 * PIO2_1T;
        let y1 = (z - y0) - n as f64 * PIO2_1T;
        return (n, y0, y1);
    }
    if ix < 0x4139_21fb {
        let mut fn_value = x * INVPIO2 + TOINT - TOINT;
        let mut n = fn_value as i32;
        let mut r = x - fn_value * PIO2_1;
        let mut w = fn_value * PIO2_1T;
        if r - w < -PIO4 {
            n -= 1;
            fn_value -= 1.0;
            r = x - fn_value * PIO2_1;
            w = fn_value * PIO2_1T;
        } else if r - w > PIO4 {
            n += 1;
            fn_value += 1.0;
            r = x - fn_value * PIO2_1;
            w = fn_value * PIO2_1T;
        }
        let mut y0 = r - w;
        let ex = (ix >> 20) as i32;
        let mut ey = ((y0.to_bits() >> 52) & 0x7ff) as i32;
        if ex - ey > 16 {
            let t = r;
            w = fn_value * PIO2_2;
            r = t - w;
            w = fn_value * PIO2_2T - ((t - r) - w);
            y0 = r - w;
            ey = ((y0.to_bits() >> 52) & 0x7ff) as i32;
            if ex - ey > 49 {
                let t = r;
                w = fn_value * PIO2_3;
                r = t - w;
                w = fn_value * PIO2_3T - ((t - r) - w);
                y0 = r - w;
            }
        }
        return (n, y0, (r - y0) - w);
    }
    // Split |x| into 24-bit chunks, scaled so the leading chunk is integral.
    let mut z = f64::from_bits((x.to_bits() & 0x000f_ffff_ffff_ffff) | (1046_u64 << 52));
    let mut tx = [0.0; 3];
    for part in &mut tx[..2] {
        *part = (z as i32) as f64;
        z = (z - *part) * 16_777_216.0;
    }
    tx[2] = z;
    let mut nx = 3;
    while tx[nx - 1] == 0.0 {
        nx -= 1;
    }
    let (n, y0, y1) = rem_pio2_large(&tx[..nx], (ix >> 20) as i32 - 1046);
    if sign {
        (-n, -y0, -y1)
    } else {
        (n, y0, y1)
    }
}

// musl __rem_pio2_large.c (FreeBSD k_rem_pio2.c), specialized to prec=1
// (binary64). Keep all 66 binary64 2/pi limbs and the recomputation path;
// engine angles are small, but callers need not impose an artificial limit.
fn rem_pio2_large(x: &[f64], e0: i32) -> (i32, f64, f64) {
    const IPIO2: [i32; 66] = [
        0xA2F983, 0x6E4E44, 0x1529FC, 0x2757D1, 0xF534DD, 0xC0DB62, 0x95993C, 0x439041, 0xFE5163,
        0xABDEBB, 0xC561B7, 0x246E3A, 0x424DD2, 0xE00649, 0x2EEA09, 0xD1921C, 0xFE1DEB, 0x1CB129,
        0xA73EE8, 0x8235F5, 0x2EBB44, 0x84E99C, 0x7026B4, 0x5F7E41, 0x3991D6, 0x398353, 0x39F49C,
        0x845F8B, 0xBDF928, 0x3B1FF8, 0x97FFDE, 0x05980F, 0xEF2F11, 0x8B5A0A, 0x6D1F6D, 0x367ECF,
        0x27CB09, 0xB74F46, 0x3F669E, 0x5FEA2D, 0x7527BA, 0xC7EBE5, 0xF17B3D, 0x0739F7, 0x8A5292,
        0xEA6BFB, 0x5FB11F, 0x8D5D08, 0x560330, 0x46FC7B, 0x6BABF0, 0xCFBC20, 0x9AF436, 0x1DA9E3,
        0x91615E, 0xE61B08, 0x659985, 0x5F14A0, 0x68408D, 0xFFD880, 0x4D7327, 0x310606, 0x1556CA,
        0x73A8C9, 0x60E27B, 0xC08C6B,
    ];
    const PIO2: [f64; 8] = [
        1.57079625129699707031e+00,
        7.54978941586159635335e-08,
        5.39030252995776476554e-15,
        3.28200341580791294123e-22,
        1.27065575308067607349e-29,
        1.22933308981111328932e-36,
        2.73370053816464559624e-44,
        2.16741683877804819444e-51,
    ];
    const JK: usize = 4;
    const TWO24: f64 = 16_777_216.0;
    const TWO_NEG24: f64 = 1.0 / TWO24;
    let jx = x.len() - 1;
    let jv = ((e0 - 3) / 24).max(0) as usize;
    let mut q0 = e0 - 24 * (jv as i32 + 1);
    let mut iq = [0_i32; 20];
    let mut f = [0.0; 20];
    let mut fq = [0.0; 20];
    let mut q = [0.0; 20];
    for i in 0..=jx + JK {
        let j = jv as i32 - jx as i32 + i as i32;
        f[i] = if j < 0 { 0.0 } else { IPIO2[j as usize] as f64 };
    }
    for i in 0..=JK {
        let mut fw = 0.0;
        for j in 0..=jx {
            fw += x[j] * f[jx + i - j];
        }
        q[i] = fw;
    }
    let mut jz = JK;
    let (mut n, mut z, ih) = loop {
        // Distill q into 24-bit integer chunks, in reverse order.
        let mut z = q[jz];
        for i in 0..jz {
            let fw = ((TWO_NEG24 * z) as i32) as f64;
            iq[i] = (z - TWO24 * fw) as i32;
            z = q[jz - i - 1] + fw;
        }
        z = scalbn(z, q0);
        z -= 8.0 * (z * 0.125).floor();
        let mut n = z as i32;
        z -= n as f64;
        let mut ih = 0;
        if q0 > 0 {
            let i = iq[jz - 1] >> (24 - q0);
            n += i;
            iq[jz - 1] -= i << (24 - q0);
            ih = iq[jz - 1] >> (23 - q0);
        } else if q0 == 0 {
            ih = iq[jz - 1] >> 23;
        } else if z >= 0.5 {
            ih = 2;
        }
        if ih > 0 {
            n += 1;
            let mut carry = 0;
            for part in &mut iq[..jz] {
                let j = *part;
                if carry == 0 {
                    if j != 0 {
                        carry = 1;
                        *part = 0x100_0000 - j;
                    }
                } else {
                    *part = 0xff_ffff - j;
                }
            }
            if q0 == 1 {
                iq[jz - 1] &= 0x7f_ffff;
            } else if q0 == 2 {
                iq[jz - 1] &= 0x3f_ffff;
            }
            if ih == 2 {
                z = 1.0 - z;
                if carry != 0 {
                    z -= scalbn(1.0, q0);
                }
            }
        }
        if z == 0.0 && iq[JK..jz].iter().all(|&part| part == 0) {
            let mut k = 1;
            while iq[JK - k] == 0 {
                k += 1;
            }
            for i in jz + 1..=jz + k {
                f[jx + i] = IPIO2[jv + i] as f64;
                let mut fw = 0.0;
                for j in 0..=jx {
                    fw += x[j] * f[jx + i - j];
                }
                q[i] = fw;
            }
            jz += k;
            continue;
        }
        break (n, z, ih);
    };
    if z == 0.0 {
        jz -= 1;
        q0 -= 24;
        while iq[jz] == 0 {
            jz -= 1;
            q0 -= 24;
        }
    } else {
        z = scalbn(z, -q0);
        if z >= TWO24 {
            let fw = ((TWO_NEG24 * z) as i32) as f64;
            iq[jz] = (z - TWO24 * fw) as i32;
            jz += 1;
            q0 += 24;
            iq[jz] = fw as i32;
        } else {
            iq[jz] = z as i32;
        }
    }
    let mut fw = scalbn(1.0, q0);
    for i in (0..=jz).rev() {
        q[i] = fw * iq[i] as f64;
        fw *= TWO_NEG24;
    }
    for i in (0..=jz).rev() {
        let mut fw = 0.0;
        for k in 0..=JK.min(jz - i) {
            fw += PIO2[k] * q[i + k];
        }
        fq[jz - i] = fw;
    }
    let mut fw = 0.0;
    for i in (0..=jz).rev() {
        fw += fq[i];
    }
    let y0 = if ih == 0 { fw } else { -fw };
    fw = fq[0] - fw;
    for part in &fq[1..=jz] {
        fw += part;
    }
    let y1 = if ih == 0 { fw } else { -fw };
    n &= 7;
    (n, y0, y1)
}

// musl atan.c (FreeBSD s_atan.c). Only atan2 needs this kernel.
fn atan(mut x: f64) -> f64 {
    const ATANHI: [f64; 4] = [
        4.63647609000806093515e-01,
        7.85398163397448278999e-01,
        9.82793723247329054082e-01,
        1.57079632679489655800e+00,
    ];
    const ATANLO: [f64; 4] = [
        2.26987774529616870924e-17,
        3.06161699786838301793e-17,
        1.39033110312309984516e-17,
        6.12323399573676603587e-17,
    ];
    const AT: [f64; 11] = [
        3.33333333333329318027e-01,
        -1.99999999998764832476e-01,
        1.42857142725034663711e-01,
        -1.11111104054623557880e-01,
        9.09088713343650656196e-02,
        -7.69187620504482999495e-02,
        6.66107313738753120669e-02,
        -5.83357013379057348645e-02,
        4.97687799461593236017e-02,
        -3.65315727442169155270e-02,
        1.62858201153657823623e-02,
    ];
    let sign = x.is_sign_negative();
    let ix = high_word(x) & 0x7fff_ffff;
    if ix >= 0x4410_0000 {
        if x.is_nan() {
            return f64::NAN;
        }
        return if sign { -ATANHI[3] } else { ATANHI[3] };
    }
    let id = if ix < 0x3fdc_0000 {
        if ix < 0x3e40_0000 {
            return x;
        }
        None
    } else {
        x = x.abs();
        if ix < 0x3ff3_0000 {
            if ix < 0x3fe6_0000 {
                x = (2.0 * x - 1.0) / (2.0 + x);
                Some(0)
            } else {
                x = (x - 1.0) / (x + 1.0);
                Some(1)
            }
        } else if ix < 0x4003_8000 {
            x = (x - 1.5) / (1.0 + 1.5 * x);
            Some(2)
        } else {
            x = -1.0 / x;
            Some(3)
        }
    };
    let z = x * x;
    let w = z * z;
    let s1 = z * (AT[0] + w * (AT[2] + w * (AT[4] + w * (AT[6] + w * (AT[8] + w * AT[10])))));
    let s2 = w * (AT[1] + w * (AT[3] + w * (AT[5] + w * (AT[7] + w * AT[9]))));
    if let Some(id) = id {
        let z = ATANHI[id] - (x * (s1 + s2) - ATANLO[id] - x);
        if sign {
            -z
        } else {
            z
        }
    } else {
        x - x * (s1 + s2)
    }
}

/// musl atan2.c (FreeBSD e_atan2.c), including signed axes and infinities.
pub fn atan2(y: f64, x: f64) -> f64 {
    const PI: f64 = 3.1415926535897931160e+00;
    const PI_LO: f64 = 1.2246467991473531772e-16;
    if x.is_nan() || y.is_nan() {
        return f64::NAN;
    }
    let ix = high_word(x);
    let lx = x.to_bits() as u32;
    let iy = high_word(y);
    let ly = y.to_bits() as u32;
    if x.to_bits() == 0x3ff0_0000_0000_0000 {
        return atan(y);
    }
    let m = ((iy >> 31) & 1) | ((ix >> 30) & 2);
    let ix = ix & 0x7fff_ffff;
    let iy = iy & 0x7fff_ffff;
    if iy | ly == 0 {
        return match m {
            0 | 1 => y,
            2 => PI,
            _ => -PI,
        };
    }
    if ix | lx == 0 {
        return if m & 1 != 0 { -PI / 2.0 } else { PI / 2.0 };
    }
    if ix == 0x7ff0_0000 {
        return if iy == 0x7ff0_0000 {
            match m {
                0 => PI / 4.0,
                1 => -PI / 4.0,
                2 => 3.0 * PI / 4.0,
                _ => -3.0 * PI / 4.0,
            }
        } else {
            match m {
                0 => 0.0,
                1 => -0.0,
                2 => PI,
                _ => -PI,
            }
        };
    }
    if ix + (64 << 20) < iy || iy == 0x7ff0_0000 {
        return if m & 1 != 0 { -PI / 2.0 } else { PI / 2.0 };
    }
    let z = if m & 2 != 0 && iy + (64 << 20) < ix {
        0.0
    } else {
        atan((y / x).abs())
    };
    match m {
        0 => z,
        1 => -z,
        2 => PI - (z - PI_LO),
        _ => (z - PI_LO) - PI,
    }
}

// Shared fdlibm coefficients used by the legacy musl exp and pow routines.
const P1: f64 = 1.66666666666666019037e-01;
const P2: f64 = -2.77777777770155933842e-03;
const P3: f64 = 6.61375632143793436117e-05;
const P4: f64 = -1.65339022054652515390e-06;
const P5: f64 = 4.13813679705723846039e-08;

/// Legacy musl exp.c (FreeBSD e_exp.c): ln(2) reduction and rational kernel.
pub fn exp(mut x: f64) -> f64 {
    const HALF: [f64; 2] = [0.5, -0.5];
    const LN2HI: f64 = 6.93147180369123816490e-01;
    const LN2LO: f64 = 1.90821492927058770002e-10;
    const INVLN2: f64 = 1.44269504088896338700e+00;
    let sign = (high_word(x) >> 31) as usize;
    let hx = high_word(x) & 0x7fff_ffff;
    if hx >= 0x4086_232b {
        if x.is_nan() {
            return f64::NAN;
        }
        if x > 709.782712893383973096 {
            return f64::INFINITY;
        }
        if x < -745.13321910194110842 {
            return 0.0;
        }
    }
    let (k, hi, lo) = if hx > 0x3fd6_2e42 {
        let k = if hx >= 0x3ff0_a2b2 {
            (INVLN2 * x + HALF[sign]) as i32
        } else {
            1 - 2 * sign as i32
        };
        let hi = x - k as f64 * LN2HI;
        let lo = k as f64 * LN2LO;
        x = hi - lo;
        (k, hi, lo)
    } else if hx > 0x3e30_0000 {
        (0, x, 0.0)
    } else {
        return 1.0 + x;
    };
    let xx = x * x;
    let c = x - xx * (P1 + xx * (P2 + xx * (P3 + xx * (P4 + xx * P5))));
    let y = 1.0 + (x * c / (2.0 - c) - lo + hi);
    if k == 0 {
        y
    } else {
        scalbn(y, k)
    }
}

/// Legacy musl pow.c (FreeBSD e_pow.c): split log2, product, then exp2.
pub fn pow(x: f64, y: f64) -> f64 {
    const BP: [f64; 2] = [1.0, 1.5];
    const DP_H: [f64; 2] = [0.0, 5.84962487220764160156e-01];
    const DP_L: [f64; 2] = [0.0, 1.35003920212974897128e-08];
    const TWO53: f64 = 9007199254740992.0;
    const L1: f64 = 5.99999999999994648725e-01;
    const L2: f64 = 4.28571428578550184252e-01;
    const L3: f64 = 3.33333329818377432918e-01;
    const L4: f64 = 2.72728123808534006489e-01;
    const L5: f64 = 2.30660745775561754067e-01;
    const L6: f64 = 2.06975017800338417784e-01;
    const LG2: f64 = 6.93147180559945286227e-01;
    const LG2_H: f64 = 6.93147182464599609375e-01;
    const LG2_L: f64 = -1.90465429995776804525e-09;
    const OVT: f64 = 8.0085662595372944372e-017;
    const CP: f64 = 9.61796693925975554329e-01;
    const CP_H: f64 = 9.61796700954437255859e-01;
    const CP_L: f64 = -7.02846165095275826516e-09;
    const IVLN2: f64 = 1.44269504088896338700e+00;
    const IVLN2_H: f64 = 1.44269502162933349609e+00;
    const IVLN2_L: f64 = 1.92596299112661746887e-08;
    let hx = high_word(x) as i32;
    let hy = high_word(y) as i32;
    let mut ix = hx & 0x7fff_ffff;
    let iy = hy & 0x7fff_ffff;
    let lx = x.to_bits() as u32;
    let ly = y.to_bits() as u32;
    if y == 0.0 || x == 1.0 {
        return 1.0;
    }
    if x.is_nan() || y.is_nan() {
        return f64::NAN;
    }
    // yisint: 0 = noninteger, 1 = odd, 2 = even (needed only for x < 0).
    let mut yisint = 0;
    if hx < 0 {
        if iy >= 0x4340_0000 {
            yisint = 2;
        } else if iy >= 0x3ff0_0000 {
            let k = (iy >> 20) - 1023;
            if k > 20 {
                let j = ly >> (52 - k);
                if j << (52 - k) == ly {
                    yisint = 2 - (j & 1) as i32;
                }
            } else if ly == 0 {
                let j = iy >> (20 - k);
                if j << (20 - k) == iy {
                    yisint = 2 - (j & 1);
                }
            }
        }
    }
    if ly == 0 {
        if iy == 0x7ff0_0000 {
            if x.abs() == 1.0 {
                return 1.0;
            }
            return if ix >= 0x3ff0_0000 {
                if hy >= 0 {
                    y
                } else {
                    0.0
                }
            } else if hy < 0 {
                -y
            } else {
                0.0
            };
        }
        if iy == 0x3ff0_0000 {
            return if hy < 0 { 1.0 / x } else { x };
        }
        if hy == 0x4000_0000 {
            return x * x;
        }
        if hy == 0x3fe0_0000 && hx >= 0 {
            return x.sqrt();
        }
    }
    let mut ax = x.abs();
    if lx == 0 && (ix == 0x7ff0_0000 || ix == 0 || ix == 0x3ff0_0000) {
        let mut z = ax;
        if hy < 0 {
            z = 1.0 / z;
        }
        if hx < 0 {
            if ix == 0x3ff0_0000 && yisint == 0 {
                return f64::NAN;
            }
            if yisint == 1 {
                z = -z;
            }
        }
        return z;
    }
    if hx < 0 && yisint == 0 {
        return f64::NAN;
    }
    let s = if hx < 0 && yisint == 1 { -1.0 } else { 1.0 };
    let (t1, t2) = if iy > 0x41e0_0000 {
        if iy > 0x43f0_0000 {
            if ix <= 0x3fef_ffff {
                return if hy < 0 { f64::INFINITY } else { 0.0 };
            }
            if ix >= 0x3ff0_0000 {
                return if hy > 0 { f64::INFINITY } else { 0.0 };
            }
        }
        if ix < 0x3fef_ffff {
            return s * if hy < 0 { f64::INFINITY } else { 0.0 };
        }
        if ix > 0x3ff0_0000 {
            return s * if hy > 0 { f64::INFINITY } else { 0.0 };
        }
        // For |1-x| <= 2^-20 and huge y, four log terms suffice.
        let t = ax - 1.0;
        let w = (t * t) * (0.5 - t * (0.3333333333333333333333 - t * 0.25));
        let u = IVLN2_H * t;
        let v = t * IVLN2_L - w * IVLN2;
        let t1 = without_low_word(u + v);
        (t1, v - (t1 - u))
    } else {
        let mut n = 0;
        if ix < 0x0010_0000 {
            ax *= TWO53;
            n -= 53;
            ix = high_word(ax) as i32;
        }
        n += (ix >> 20) - 1023;
        let j = ix & 0x000f_ffff;
        ix = j | 0x3ff0_0000;
        let k = if j <= 0x0003_988e {
            0
        } else if j < 0x000b_b67a {
            1
        } else {
            n += 1;
            ix -= 0x0010_0000;
            0
        };
        ax = with_high_word(ax, ix as u32);
        let u = ax - BP[k];
        let v = 1.0 / (ax + BP[k]);
        let ss = u * v;
        let s_h = without_low_word(ss);
        let t_h = with_high_word(
            0.0,
            ((ix >> 1) | 0x2000_0000) as u32 + 0x0008_0000 + ((k as u32) << 18),
        );
        let t_l = ax - (t_h - BP[k]);
        let s_l = v * ((u - s_h * t_h) - s_h * t_l);
        let s2 = ss * ss;
        let mut r = s2 * s2 * (L1 + s2 * (L2 + s2 * (L3 + s2 * (L4 + s2 * (L5 + s2 * L6)))));
        r += s_l * (s_h + ss);
        let s2 = s_h * s_h;
        let t_h = without_low_word(3.0 + s2 + r);
        let t_l = r - ((t_h - 3.0) - s2);
        let u = s_h * t_h;
        let v = s_l * t_h + t_l * ss;
        let p_h = without_low_word(u + v);
        let p_l = v - (p_h - u);
        let z_h = CP_H * p_h;
        let z_l = CP_L * p_h + p_l * CP + DP_L[k];
        let t = n as f64;
        let t1 = without_low_word(((z_h + z_l) + DP_H[k]) + t);
        (t1, z_l - (((t1 - t) - DP_H[k]) - z_h))
    };
    let y1 = without_low_word(y);
    let p_l = (y - y1) * t1 + y * t2;
    let mut p_h = y1 * t1;
    let z = p_l + p_h;
    let j = high_word(z) as i32;
    let low = z.to_bits() as u32;
    if j >= 0x4090_0000 {
        if j != 0x4090_0000 || low != 0 || p_l + OVT > z - p_h {
            return s * f64::INFINITY;
        }
    } else if j & 0x7fff_ffff >= 0x4090_cc00
        && (j as u32 != 0xc090_cc00 || low != 0 || p_l <= z - p_h)
    {
        return s * 0.0;
    }
    // Compute 2^(p_h+p_l), extracting its integer exponent first.
    let i = j & 0x7fff_ffff;
    let mut k = (i >> 20) - 1023;
    let mut n = 0;
    if i > 0x3fe0_0000 {
        let bits = j.wrapping_add(0x0010_0000 >> (k + 1));
        k = ((bits & 0x7fff_ffff) >> 20) - 1023;
        let t = with_high_word(0.0, (bits & !(0x000f_ffff >> k)) as u32);
        n = ((bits & 0x000f_ffff) | 0x0010_0000) >> (20 - k);
        if j < 0 {
            n = -n;
        }
        p_h -= t;
    }
    let t = without_low_word(p_l + p_h);
    let u = t * LG2_H;
    let v = (p_l - (t - p_h)) * LG2 + t * LG2_L;
    let z = u + v;
    let w = v - (z - u);
    let t = z * z;
    let t1 = z - t * (P1 + t * (P2 + t * (P3 + t * (P4 + t * P5))));
    let r = (z * t1) / (t1 - 2.0) - (w + z * w);
    let z = 1.0 - (r - z);
    let j = (high_word(z) as i32).wrapping_add(n << 20);
    let z = if j >> 20 <= 0 {
        scalbn(z, n)
    } else {
        with_high_word(z, j as u32)
    };
    s * z
}
