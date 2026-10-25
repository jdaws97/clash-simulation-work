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
        let mut chunks = bytes.chunks_exact(8);
        for chunk in &mut chunks {
            self.add(u64::from_ne_bytes(
                chunk.try_into().expect("eight-byte chunk"),
            ));
        }
        for &byte in chunks.remainder() {
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
