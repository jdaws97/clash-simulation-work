//! Python's `random.Random`, bit-exact for the calls the engine makes
//! (battle.py:148 `random.Random(seed)`; `random()`, `uniform()`, `choice()`).
//! CPython: Modules/_randommodule.c (MT19937, init_by_array, random_random)
//! and Lib/random.py (uniform, choice, _randbelow_with_getrandbits).

const N: usize = 624;
const M: usize = 397;

pub struct PyRandom {
    mt: [u32; N],
    index: usize,
}

impl PyRandom {
    /// `random.Random(seed)` for an integer seed: the key is |seed| split into
    /// 32-bit words, least significant first (a zero seed gives the key [0]).
    pub fn new(seed: i64) -> Self {
        let mut value = seed.unsigned_abs();
        let mut key = Vec::new();
        while value > 0 {
            key.push(value as u32);
            value >>= 32;
        }
        if key.is_empty() {
            key.push(0);
        }
        let mut rng = Self { mt: [0; N], index: N };
        rng.init_by_array(&key);
        rng
    }

    /// From `random.Random.getstate()[1]`: 624 state words followed by the index.
    pub fn from_state(words: &[u32]) -> Self {
        assert_eq!(words.len(), N + 1, "random state needs 625 integers");
        let mut mt = [0; N];
        mt.copy_from_slice(&words[..N]);
        let index = words[N] as usize;
        assert!(index <= N, "random state index out of range");
        Self { mt, index }
    }

    fn init_genrand(&mut self, s: u32) {
        self.mt[0] = s;
        for i in 1..N {
            let prev = self.mt[i - 1];
            self.mt[i] = 1_812_433_253_u32
                .wrapping_mul(prev ^ (prev >> 30))
                .wrapping_add(i as u32);
        }
        self.index = N;
    }

    fn init_by_array(&mut self, key: &[u32]) {
        self.init_genrand(19_650_218);
        let (mut i, mut j) = (1_usize, 0_usize);
        for _ in 0..N.max(key.len()) {
            let prev = self.mt[i - 1];
            self.mt[i] = (self.mt[i] ^ (prev ^ (prev >> 30)).wrapping_mul(1_664_525))
                .wrapping_add(key[j])
                .wrapping_add(j as u32);
            i += 1;
            j += 1;
            if i >= N {
                self.mt[0] = self.mt[N - 1];
                i = 1;
            }
            if j >= key.len() {
                j = 0;
            }
        }
        for _ in 0..N - 1 {
            let prev = self.mt[i - 1];
            self.mt[i] = (self.mt[i] ^ (prev ^ (prev >> 30)).wrapping_mul(1_566_083_941))
                .wrapping_sub(i as u32);
            i += 1;
            if i >= N {
                self.mt[0] = self.mt[N - 1];
                i = 1;
            }
        }
        self.mt[0] = 0x8000_0000;
    }

    fn genrand_u32(&mut self) -> u32 {
        const UPPER: u32 = 0x8000_0000;
        const LOWER: u32 = 0x7fff_ffff;
        const MATRIX_A: u32 = 0x9908_b0df;
        if self.index >= N {
            for k in 0..N {
                let y = (self.mt[k] & UPPER) | (self.mt[(k + 1) % N] & LOWER);
                let mag = if y & 1 == 1 { MATRIX_A } else { 0 };
                self.mt[k] = self.mt[(k + M) % N] ^ (y >> 1) ^ mag;
            }
            self.index = 0;
        }
        let mut y = self.mt[self.index];
        self.index += 1;
        y ^= y >> 11;
        y ^= (y << 7) & 0x9d2c_5680;
        y ^= (y << 15) & 0xefc6_0000;
        y ^ (y >> 18)
    }

    /// `random.random()`: 53 bits from two draws.
    pub fn random(&mut self) -> f64 {
        let a = (self.genrand_u32() >> 5) as f64;
        let b = (self.genrand_u32() >> 6) as f64;
        (a * 67_108_864.0 + b) * (1.0 / 9_007_199_254_740_992.0)
    }

    /// `random.uniform(a, b)` = a + (b - a) * random().
    pub fn uniform(&mut self, a: f64, b: f64) -> f64 {
        a + (b - a) * self.random()
    }

    /// `random.choice` index: `_randbelow(n)` by rejection on n.bit_length() bits.
    pub fn below(&mut self, n: usize) -> usize {
        assert!(n > 0, "choice from an empty sequence");
        let k = usize::BITS - n.leading_zeros(); // n.bit_length(), at most 32 here
        assert!(k <= 32, "sequence too long for this port");
        loop {
            let r = (self.genrand_u32() >> (32 - k)) as usize;
            if r < n {
                return r;
            }
        }
    }
}
