// entities.py:15-16,59-64: center distance and distance to a square hitbox.
pub fn dist(ax: f64, ay: f64, bx: f64, by: f64) -> f64 {
    py_hypot(ax - bx, ay - by)
}

pub fn edge_distance(x: f64, y: f64, cx: f64, cy: f64, half_hit: f64) -> f64 {
    let dx = ((x - cx).abs() - half_hit).max(0.0);
    let dy = ((y - cy).abs() - half_hit).max(0.0);
    py_hypot(dx, dy)
}

// units.py:60-74: closed slabs; contact at either segment endpoint counts.
pub fn segment_entry(
    x: f64,
    y: f64,
    tx: f64,
    ty: f64,
    cx: f64,
    cy: f64,
    half_hit: f64,
) -> Option<f64> {
    let mut enter: f64 = 0.0;
    let mut leave: f64 = 1.0;
    for (start, end, center) in [(x, tx, cx), (y, ty, cy)] {
        let low = center - half_hit;
        let high = center + half_hit;
        let delta = end - start;
        if delta == 0.0 {
            if start < low || start > high {
                return None;
            }
            continue;
        }
        let first = (low - start) / delta;
        let last = (high - start) / delta;
        enter = enter.max(first.min(last));
        leave = leave.min(first.max(last));
    }
    if enter <= leave {
        Some(enter)
    } else {
        None
    }
}

// pathing.py:190-193 and battle.py:938-950 use Python's nearest-even rounding.
pub fn round_half_even(value: f64) -> f64 {
    value.round_ties_even()
}

pub fn round6(value: f64) -> f64 {
    // battle.py:950: round the exact binary value, avoiding value * 1e6,
    // whose rounding can turn a near tie into an exact tie.
    if !value.is_finite() || value.abs() >= 17_179_869_184.0 {
        // At 2^34 the spacing already exceeds the decimal rounding adjustment.
        return value;
    }
    let bits = value.abs().to_bits();
    let biased_exponent = ((bits >> 52) & 0x7ff) as i32;
    let fraction = bits & ((1_u64 << 52) - 1);
    let (significand, exponent) = if biased_exponent == 0 {
        (fraction, -1074)
    } else {
        ((1_u64 << 52) | fraction, biased_exponent - 1023 - 52)
    };
    // 1e6 = 15625 * 2^6. The integer product fits comfortably in u128.
    let numerator = u128::from(significand) * 15_625;
    let shift = (-(exponent + 6)) as u32;
    let rounded = if shift >= 128 {
        0
    } else {
        let whole = numerator >> shift;
        let remainder = numerator - (whole << shift);
        let halfway = 1_u128 << (shift - 1);
        if remainder > halfway || (remainder == halfway && whole & 1 == 1) {
            whole + 1
        } else {
            whole
        }
    };
    // Decimal parsing gives one correctly rounded conversion back to binary,
    // even if the scaled integer would itself need rounding when cast to f64.
    let decimal = format!("{}.{:06}", rounded / 1_000_000, rounded % 1_000_000);
    decimal
        .parse::<f64>()
        .expect("valid rounded decimal")
        .copysign(value)
}

/// math.hypot(a, b) exactly as CPython 3.10 computes it (mathmodule.c
/// vector_norm): power-of-two scaling, compensated sum of squares, one
/// Newton correction. Rust's f64::hypot differs in the last bit for ~16% of
/// inputs, enough to change battle outcomes.
pub fn py_hypot(a: f64, b: f64) -> f64 {
    let (a, b) = (a.abs(), b.abs());
    let max = a.max(b);
    if max.is_infinite() {
        return max;
    }
    if a.is_nan() || b.is_nan() {
        return f64::NAN;
    }
    if max == 0.0 {
        return max;
    }
    let bits = max.to_bits();
    let biased = ((bits >> 52) & 0x7ff) as i32;
    if biased == 0 {
        return (a * a + b * b).sqrt(); // subnormal max: never reached in battles
    }
    let max_e = biased - 1022; // frexp exponent: max = m * 2^max_e, m in [0.5, 1)
    let scale = f64::from_bits(((1023 - max_e) as u64) << 52); // ldexp(1.0, -max_e)
    const T27: f64 = 134217729.0;
    let (mut csum, mut frac1, mut frac2, mut frac3) = (1.0_f64, 0.0_f64, 0.0_f64, 0.0_f64);
    for v in [a, b] {
        let x = v * scale;
        let t = x * T27;
        let hi = t - (t - x);
        let lo = x - hi;
        let sq = hi * hi;
        let old = csum;
        csum += sq;
        frac1 += (old - csum) + sq;
        let cross = 2.0 * hi * lo;
        let old = csum;
        csum += cross;
        frac2 += (old - csum) + cross;
        frac3 += lo * lo;
    }
    let h = (csum - 1.0 + (frac1 + frac2 + frac3)).sqrt();
    let t = h * T27;
    let hi = t - (t - h);
    let lo = h - hi;
    let x = -hi * hi;
    let old = csum;
    csum += x;
    frac1 += (old - csum) + x;
    let x = -2.0 * hi * lo;
    let old = csum;
    csum += x;
    frac2 += (old - csum) + x;
    let x = -lo * lo;
    let old = csum;
    csum += x;
    frac3 += (old - csum) + x;
    let x = csum - 1.0 + (frac1 + frac2 + frac3);
    (h + x / (2.0 * h)) / scale
}

// Since python-frozen, maths is platform-identical by construction through
// detmath's fixed musl algorithms on every platform (see docs/GOLDEN.md).

/// math.cos
pub fn py_cos(x: f64) -> f64 {
    crate::detmath::cos(x)
}

/// math.sin
pub fn py_sin(x: f64) -> f64 {
    crate::detmath::sin(x)
}

/// math.atan2(y, x)
pub fn py_atan2(y: f64, x: f64) -> f64 {
    crate::detmath::atan2(y, x)
}

/// Floating-point power, using the same fixed algorithm on every platform.
pub fn py_pow(x: f64, y: f64) -> f64 {
    crate::detmath::pow(x, y)
}
