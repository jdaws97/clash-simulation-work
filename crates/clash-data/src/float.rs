//! Exact presentation of runtime floats.
use std::fmt::Write;

// Python's repr uses shortest round-trip digits, fixed notation for exponents
// -4..15, two or more exponent digits, and .0 on fixed integral floats.
pub fn py_float_repr(value: f64) -> String {
    if value.is_nan() {
        return "nan".to_owned();
    }
    if value.is_infinite() {
        return if value.is_sign_negative() {
            "-inf"
        } else {
            "inf"
        }
        .to_owned();
    }
    let sign = if value.is_sign_negative() { "-" } else { "" };
    if value == 0.0 {
        return format!("{sign}0.0");
    }
    // Rust's Debug formatter supplies shortest round-trip significand digits.
    // Normalize its presentation separately from Python's presentation rules.
    let shortest = format!("{:?}", value.abs());
    let (mantissa, explicit_exponent) =
        shortest
            .split_once('e')
            .map_or((shortest.as_str(), 0), |(mantissa, exponent)| {
                (
                    mantissa,
                    exponent.parse::<i32>().expect("formatted float exponent"),
                )
            });
    let dot = mantissa.find('.').unwrap_or(mantissa.len()) as i32;
    let all_digits: String = mantissa.chars().filter(|c| *c != '.').collect();
    let leading = all_digits.bytes().take_while(|byte| *byte == b'0').count();
    let exponent = explicit_exponent + dot - leading as i32 - 1;
    let digits = all_digits[leading..].trim_end_matches('0');
    if !(-4..16).contains(&exponent) {
        let mut result = format!("{sign}{}", &digits[..1]);
        if digits.len() > 1 {
            result.push('.');
            result.push_str(&digits[1..]);
        }
        write!(
            result,
            "e{}{:02}",
            if exponent < 0 { '-' } else { '+' },
            exponent.abs()
        )
        .expect("write to string");
        return result;
    }
    let position = exponent + 1;
    if position <= 0 {
        format!("{sign}0.{}{digits}", "0".repeat((-position) as usize))
    } else if position as usize >= digits.len() {
        format!(
            "{sign}{digits}{}.0",
            "0".repeat(position as usize - digits.len())
        )
    } else {
        let position = position as usize;
        format!("{sign}{}.{}", &digits[..position], &digits[position..])
    }
}
