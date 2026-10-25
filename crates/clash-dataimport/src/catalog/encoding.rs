//! Stable registry intermediate encoding, including its legacy numeric types.
//!
//! Json stores f64 for every number. The registry schema distinguishes parsed
//! wiki/converted mechanic floats from game-file integer fields. Preserve that
//! distinction when encoding the historical intermediate for provenance.

use clash_data::float::py_float_repr;
use clash_data::json::Json;
use clash_data::wire;

pub(super) fn registry(value: &Json) -> String {
    let mut output = String::new();
    write(value, 0, "", false, &mut output);
    output
}

fn write(value: &Json, depth: usize, container: &str, float: bool, output: &mut String) {
    match value {
        Json::Num(value) if !float && value.fract() == 0.0 => {
            output.push_str(&(*value as i64).to_string())
        }
        Json::Num(value) => output.push_str(&py_float_repr(*value)),
        Json::Arr(values) => {
            output.push('[');
            for (index, value) in values.iter().enumerate() {
                if index > 0 {
                    output.push(',');
                }
                output.push('\n');
                output.push_str(&" ".repeat(depth + 1));
                write(value, depth + 1, container, false, output);
            }
            if !values.is_empty() {
                output.push('\n');
                output.push_str(&" ".repeat(depth));
            }
            output.push(']');
        }
        Json::Obj(values) => {
            output.push('{');
            for (index, (key, value)) in values.iter().enumerate() {
                if index > 0 {
                    output.push(',');
                }
                output.push('\n');
                output.push_str(&" ".repeat(depth + 1));
                output.push_str(&wire::encode(&Json::Str(key.clone())));
                output.push_str(": ");
                let float = (container == "attrs"
                    && !["width", "hitbox", "housing_ck"].contains(&key.as_str()))
                    || (container == "levels" && key == "radius");
                write(value, depth + 1, key, float, output);
            }
            if !values.is_empty() {
                output.push('\n');
                output.push_str(&" ".repeat(depth));
            }
            output.push('}');
        }
        _ => output.push_str(&wire::encode(value)),
    }
}
