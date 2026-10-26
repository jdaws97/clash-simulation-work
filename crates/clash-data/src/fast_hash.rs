//! Lookup-only maps: iteration order always comes from the simulation's Vecs.

use std::collections::HashMap;
use std::hash::{BuildHasherDefault, Hasher};

pub type FastMap<K, V> = HashMap<K, V, BuildHasherDefault<FastHasher>>;

#[derive(Default)]
pub struct FastHasher(u64);

impl FastHasher {
    #[inline]
    fn add(&mut self, value: u64) {
        self.0 = (self.0.rotate_left(5) ^ value).wrapping_mul(0x517c_c1b7_2722_0a95);
    }
}

impl Hasher for FastHasher {
    #[inline]
    fn finish(&self) -> u64 {
        self.0
    }

    fn write(&mut self, bytes: &[u8]) {
        let (chunks, remainder) = bytes.as_chunks::<8>();
        for chunk in chunks {
            self.add(u64::from_ne_bytes(*chunk));
        }
        for &byte in remainder {
            self.add(u64::from(byte));
        }
    }

    #[inline]
    fn write_u64(&mut self, value: u64) {
        self.add(value);
    }

    #[inline]
    fn write_usize(&mut self, value: usize) {
        self.add(value as u64);
    }

    #[inline]
    fn write_u32(&mut self, value: u32) {
        self.add(u64::from(value));
    }

    #[inline]
    fn write_i32(&mut self, value: i32) {
        self.add(value as u64);
    }

    #[inline]
    fn write_i64(&mut self, value: i64) {
        self.add(value as u64);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn chunk_boundaries_match_recorded_hashes() {
        // Captured from the pre-cleanup implementation. Repeated bytes make
        // the native-endian eight-byte words identical on every target.
        let expected = [
            (0, 0x0000_0000_0000_0000),
            (1, 0x8568_db0c_38f0_d209),
            (7, 0x4ecb_b269_665d_6b7f),
            (8, 0xda54_ec11_04cb_db09),
            (9, 0xd6cb_172c_2f9b_fcf6),
            (15, 0x801e_9b7b_6e8a_8cc8),
            (16, 0xa933_e569_5052_9bf6),
            (17, 0xaebe_5749_2068_f730),
            (31, 0xc3df_ffa3_2139_2697),
            (32, 0x6782_d9fa_c99e_b996),
            (33, 0x6606_3843_452a_711d),
        ];
        let bytes = [0xa5; 33];
        for (length, hash) in expected {
            let mut hasher = FastHasher::default();
            hasher.write(&bytes[..length]);
            assert_eq!(hasher.finish(), hash, "input length {length}");
        }
    }
}
