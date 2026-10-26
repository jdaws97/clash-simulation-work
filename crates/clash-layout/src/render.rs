//! Small, dependency-free RGB raster renderer. PPM input/output and 8-bit,
//! non-interlaced PNG input/output keep screenshot tools usable offline.
use std::fs;
use std::path::Path;

const MAX_BYTES: usize = 256 * 1024 * 1024;

#[derive(Clone, Debug, PartialEq)]
pub struct Image {
    pub width: usize,
    pub height: usize,
    pub pixels: Vec<[u8; 3]>,
}

impl Image {
    pub fn new(width: usize, height: usize, color: [u8; 3]) -> Result<Self, String> {
        let count = width
            .checked_mul(height)
            .ok_or("image dimensions overflow")?;
        if count == 0 || count > MAX_BYTES / 3 {
            return Err("image dimensions exceed raster limit".to_owned());
        }
        Ok(Self {
            width,
            height,
            pixels: vec![color; count],
        })
    }

    pub fn load(path: &Path) -> Result<Self, String> {
        let bytes = fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
        if bytes.starts_with(b"\x89PNG\r\n\x1a\n") {
            Self::from_png(&bytes)
        } else {
            Self::from_ppm(&bytes)
        }
    }

    pub fn save(&self, path: &Path) -> Result<(), String> {
        let bytes = if path
            .extension()
            .is_some_and(|v| v.eq_ignore_ascii_case("png"))
        {
            self.png()
        } else if path
            .extension()
            .is_some_and(|v| v.eq_ignore_ascii_case("ppm"))
        {
            self.ppm()
        } else {
            return Err("image output must end in .png or .ppm".to_owned());
        };
        fs::write(path, bytes).map_err(|e| format!("{}: {e}", path.display()))
    }

    pub fn get(&self, x: i32, y: i32) -> Option<[u8; 3]> {
        if x < 0 || y < 0 || x as usize >= self.width || y as usize >= self.height {
            None
        } else {
            Some(self.pixels[y as usize * self.width + x as usize])
        }
    }

    pub fn dot(&mut self, x: i32, y: i32, color: [u8; 3], alpha: u8) {
        if self.get(x, y).is_none() {
            return;
        }
        let pixel = &mut self.pixels[y as usize * self.width + x as usize];
        for channel in 0..3 {
            pixel[channel] = ((u32::from(pixel[channel]) * (255 - u32::from(alpha))
                + u32::from(color[channel]) * u32::from(alpha)
                + 127)
                / 255) as u8;
        }
    }

    pub fn line(&mut self, p: (f64, f64), q: (f64, f64), color: [u8; 3], alpha: u8) {
        // Clip before rasterizing: off-screen projection lines may be very long.
        let (dx, dy) = (q.0 - p.0, q.1 - p.1);
        let (mut lo, mut hi) = (0.0_f64, 1.0_f64);
        for (direction, distance) in [
            (-dx, p.0),
            (dx, self.width as f64 - 1.0 - p.0),
            (-dy, p.1),
            (dy, self.height as f64 - 1.0 - p.1),
        ] {
            if direction == 0.0 {
                if distance < 0.0 {
                    return;
                }
            } else if direction < 0.0 {
                lo = lo.max(distance / direction);
            } else {
                hi = hi.min(distance / direction);
            }
        }
        if lo > hi || ![p.0, p.1, q.0, q.1].iter().all(|v| v.is_finite()) {
            return;
        }
        let start = (p.0 + lo * dx, p.1 + lo * dy);
        let end = (p.0 + hi * dx, p.1 + hi * dy);
        let steps = (end.0 - start.0).abs().max((end.1 - start.1).abs()).ceil() as usize;
        for i in 0..=steps {
            let t = i as f64 / steps.max(1) as f64;
            self.dot(
                (start.0 + t * (end.0 - start.0)).round() as i32,
                (start.1 + t * (end.1 - start.1)).round() as i32,
                color,
                alpha,
            );
        }
    }

    pub fn polygon(&mut self, points: &[(f64, f64)], color: [u8; 3], alpha: u8) {
        for i in 0..points.len() {
            self.line(points[i], points[(i + 1) % points.len()], color, alpha);
        }
    }

    /// Compact 3x5 glyphs, sufficient for tile coordinates and building keys.
    pub fn text(&mut self, x: i32, y: i32, text: &str, color: [u8; 3]) {
        for (offset, ch) in text.to_ascii_uppercase().chars().enumerate() {
            let rows = match ch {
                '0' => [7, 5, 5, 5, 7],
                '1' => [2, 6, 2, 2, 7],
                '2' => [7, 1, 7, 4, 7],
                '3' => [7, 1, 7, 1, 7],
                '4' => [5, 5, 7, 1, 1],
                '5' => [7, 4, 7, 1, 7],
                '6' => [7, 4, 7, 5, 7],
                '7' => [7, 1, 2, 2, 2],
                '8' => [7, 5, 7, 5, 7],
                '9' => [7, 5, 7, 1, 7],
                'A' => [2, 5, 7, 5, 5],
                'B' => [6, 5, 6, 5, 6],
                'C' => [7, 4, 4, 4, 7],
                'D' => [6, 5, 5, 5, 6],
                'E' => [7, 4, 6, 4, 7],
                'F' => [7, 4, 6, 4, 4],
                'G' => [7, 4, 5, 5, 7],
                'H' => [5, 5, 7, 5, 5],
                'I' => [7, 2, 2, 2, 7],
                'J' => [1, 1, 1, 5, 7],
                'K' => [5, 5, 6, 5, 5],
                'L' => [4, 4, 4, 4, 7],
                'M' => [5, 7, 7, 5, 5],
                'N' => [5, 7, 7, 7, 5],
                'O' => [7, 5, 5, 5, 7],
                'P' => [7, 5, 7, 4, 4],
                'Q' => [7, 5, 5, 7, 1],
                'R' => [6, 5, 6, 5, 5],
                'S' => [7, 4, 7, 1, 7],
                'T' => [7, 2, 2, 2, 2],
                'U' => [5, 5, 5, 5, 7],
                'V' => [5, 5, 5, 5, 2],
                'W' => [5, 5, 7, 7, 5],
                'X' => [5, 5, 2, 5, 5],
                'Y' => [5, 5, 2, 2, 2],
                'Z' => [7, 1, 2, 4, 7],
                ',' => [0, 0, 0, 2, 4],
                '-' => [0, 0, 7, 0, 0],
                ':' => [0, 2, 0, 2, 0],
                _ => [0; 5],
            };
            for (dy, row) in rows.iter().enumerate() {
                for dx in 0..3 {
                    if row & (4 >> dx) != 0 {
                        self.dot(x + offset as i32 * 4 + dx, y + dy as i32, color, 255);
                    }
                }
            }
        }
    }

    pub fn crop(
        &self,
        x: usize,
        y: usize,
        width: usize,
        height: usize,
        zoom: usize,
    ) -> Result<Self, String> {
        if zoom == 0
            || x.checked_add(width).is_none_or(|v| v > self.width)
            || y.checked_add(height).is_none_or(|v| v > self.height)
        {
            return Err("invalid crop or zoom".to_owned());
        }
        let mut out = Self::new(
            width.checked_mul(zoom).ok_or("zoom overflow")?,
            height.checked_mul(zoom).ok_or("zoom overflow")?,
            [0; 3],
        )?;
        for dy in 0..out.height {
            for dx in 0..out.width {
                out.pixels[dy * out.width + dx] =
                    self.pixels[(y + dy / zoom) * self.width + x + dx / zoom];
            }
        }
        Ok(out)
    }

    pub fn ppm(&self) -> Vec<u8> {
        let mut out = format!("P6\n{} {}\n255\n", self.width, self.height).into_bytes();
        for pixel in &self.pixels {
            out.extend(pixel);
        }
        out
    }

    pub fn from_ppm(bytes: &[u8]) -> Result<Self, String> {
        fn token<'a>(bytes: &'a [u8], at: &mut usize) -> Result<&'a [u8], String> {
            loop {
                while bytes.get(*at).is_some_and(u8::is_ascii_whitespace) {
                    *at += 1;
                }
                if bytes.get(*at) != Some(&b'#') {
                    break;
                }
                while bytes.get(*at).is_some_and(|v| *v != b'\n') {
                    *at += 1;
                }
            }
            let start = *at;
            while bytes
                .get(*at)
                .is_some_and(|v| !v.is_ascii_whitespace() && *v != b'#')
            {
                *at += 1;
            }
            if start == *at {
                return Err("truncated PPM header".to_owned());
            }
            Ok(&bytes[start..*at])
        }
        let mut at = 0;
        if token(bytes, &mut at)? != b"P6" {
            return Err("expected binary P6 PPM or PNG".to_owned());
        }
        let mut number = || -> Result<usize, String> {
            std::str::from_utf8(token(bytes, &mut at)?)
                .map_err(|e| e.to_string())?
                .parse()
                .map_err(|_| "invalid PPM header".to_owned())
        };
        let (width, height, max) = (number()?, number()?, number()?);
        if max != 255 || !bytes.get(at).is_some_and(u8::is_ascii_whitespace) {
            return Err("PPM must have 8-bit channels".to_owned());
        }
        // Consume exactly the raster separator, never pixel whitespace.
        at += if bytes.get(at..at + 2) == Some(b"\r\n") {
            2
        } else {
            1
        };
        let mut out = Self::new(width, height, [0; 3])?;
        let raster = bytes.get(at..).ok_or("truncated PPM")?;
        if raster.len() != out.pixels.len() * 3 {
            return Err("PPM raster length mismatch".to_owned());
        }
        for (pixel, raw) in out.pixels.iter_mut().zip(raster.as_chunks::<3>().0) {
            pixel.copy_from_slice(raw);
        }
        Ok(out)
    }

    pub fn png(&self) -> Vec<u8> {
        let mut raw = Vec::new();
        for row in self.pixels.chunks(self.width) {
            raw.push(0);
            for pixel in row {
                raw.extend(pixel);
            }
        }
        let mut zlib = vec![0x78, 0x01];
        let chunks = raw.chunks(65535);
        let count = chunks.len();
        for (i, chunk) in chunks.enumerate() {
            zlib.push(u8::from(i + 1 == count));
            let len = chunk.len() as u16;
            zlib.extend(len.to_le_bytes());
            zlib.extend((!len).to_le_bytes());
            zlib.extend(chunk);
        }
        zlib.extend(adler32(&raw).to_be_bytes());
        let mut out = b"\x89PNG\r\n\x1a\n".to_vec();
        let mut header = Vec::new();
        header.extend((self.width as u32).to_be_bytes());
        header.extend((self.height as u32).to_be_bytes());
        header.extend([8, 2, 0, 0, 0]);
        for (kind, data) in [
            (b"IHDR", header.as_slice()),
            (b"IDAT", zlib.as_slice()),
            (b"IEND", &[][..]),
        ] {
            out.extend((data.len() as u32).to_be_bytes());
            out.extend(kind);
            out.extend(data);
            let mut check = kind.to_vec();
            check.extend(data);
            out.extend(crc32(&check).to_be_bytes());
        }
        out
    }

    pub fn from_png(bytes: &[u8]) -> Result<Self, String> {
        if !bytes.starts_with(b"\x89PNG\r\n\x1a\n") {
            return Err("bad PNG signature".to_owned());
        }
        let (mut at, mut header, mut data, mut ended) = (8, None, Vec::new(), false);
        let mut palette = Vec::new();
        while at < bytes.len() {
            let len = be32(bytes.get(at..at + 4).ok_or("truncated PNG chunk")?) as usize;
            at += 4;
            let chunk = bytes
                .get(at..at.checked_add(len + 8).ok_or("PNG chunk overflow")?)
                .ok_or("truncated PNG chunk")?;
            let (kind, body) = (&chunk[..4], &chunk[4..4 + len]);
            if crc32(&chunk[..4 + len]) != be32(&chunk[4 + len..]) {
                return Err("PNG CRC mismatch".to_owned());
            }
            match kind {
                b"IHDR" => {
                    if header.is_some()
                        || body.len() != 13
                        || body[8] != 8
                        || body[10..] != [0, 0, 0]
                    {
                        return Err("PNG requires 8-bit non-interlaced pixels".to_owned());
                    }
                    header = Some((
                        be32(&body[..4]) as usize,
                        be32(&body[4..8]) as usize,
                        body[9],
                    ));
                }
                b"PLTE" => {
                    palette = body
                        .as_chunks::<3>()
                        .0
                        .iter()
                        .map(|v| [v[0], v[1], v[2]])
                        .collect()
                }
                b"IDAT" => {
                    if data.len() + len > MAX_BYTES {
                        return Err("PNG compressed input too large".to_owned());
                    }
                    data.extend(body);
                }
                b"IEND" => {
                    ended = true;
                    break;
                }
                _ if kind[0] & 32 == 0 => return Err("unsupported critical PNG chunk".to_owned()),
                _ => {}
            }
            at += len + 8;
        }
        if !ended {
            return Err("missing PNG IEND".to_owned());
        }
        let (width, height, color) = header.ok_or("missing PNG IHDR")?;
        let channels = match color {
            0 | 3 => 1,
            2 => 3,
            4 => 2,
            6 => 4,
            _ => return Err("unsupported PNG color type".to_owned()),
        };
        let mut out = Self::new(width, height, [0; 3])?;
        let stride = width * channels;
        let expected = (stride + 1)
            .checked_mul(height)
            .filter(|v| *v <= MAX_BYTES)
            .ok_or("PNG raster too large")?;
        let raw = inflate(&data, expected)?;
        if raw.len() != expected {
            return Err("PNG raster length mismatch".to_owned());
        }
        let mut previous = vec![0_u8; stride];
        for (y, filtered) in raw.chunks_exact(stride + 1).enumerate() {
            let mut row = filtered[1..].to_vec();
            for i in 0..stride {
                let left = if i >= channels { row[i - channels] } else { 0 };
                let above = previous[i];
                let upper_left = if i >= channels {
                    previous[i - channels]
                } else {
                    0
                };
                let predictor = match filtered[0] {
                    0 => 0,
                    1 => left,
                    2 => above,
                    3 => ((u16::from(left) + u16::from(above)) / 2) as u8,
                    4 => paeth(left, above, upper_left),
                    _ => return Err("invalid PNG filter".to_owned()),
                };
                row[i] = row[i].wrapping_add(predictor);
            }
            for (x, p) in row.chunks_exact(channels).enumerate() {
                out.pixels[y * width + x] = match color {
                    0 | 4 => [p[0]; 3],
                    2 | 6 => [p[0], p[1], p[2]],
                    3 => *palette
                        .get(p[0] as usize)
                        .ok_or("PNG palette index out of range")?,
                    _ => unreachable!(),
                };
            }
            previous = row;
        }
        Ok(out)
    }
}

fn be32(v: &[u8]) -> u32 {
    u32::from_be_bytes(v[..4].try_into().expect("four bytes"))
}
fn adler32(bytes: &[u8]) -> u32 {
    let (mut a, mut b) = (1_u32, 0_u32);
    for &v in bytes {
        a = (a + u32::from(v)) % 65521;
        b = (b + a) % 65521;
    }
    (b << 16) | a
}
fn crc32(bytes: &[u8]) -> u32 {
    let mut crc = !0_u32;
    for &v in bytes {
        crc ^= u32::from(v);
        for _ in 0..8 {
            crc = (crc >> 1) ^ (0xedb8_8320 & 0_u32.wrapping_sub(crc & 1));
        }
    }
    !crc
}
fn paeth(a: u8, b: u8, c: u8) -> u8 {
    let p = i32::from(a) + i32::from(b) - i32::from(c);
    let distances = [
        (p - i32::from(a)).abs(),
        (p - i32::from(b)).abs(),
        (p - i32::from(c)).abs(),
    ];
    if distances[0] <= distances[1] && distances[0] <= distances[2] {
        a
    } else if distances[1] <= distances[2] {
        b
    } else {
        c
    }
}

struct Bits<'a> {
    data: &'a [u8],
    bit: usize,
}
impl Bits<'_> {
    fn read(&mut self, count: usize) -> Result<u32, String> {
        if self.bit + count > self.data.len() * 8 {
            return Err("truncated deflate stream".to_owned());
        }
        let mut out = 0;
        for i in 0..count {
            out |= u32::from((self.data[self.bit / 8] >> (self.bit % 8)) & 1) << i;
            self.bit += 1;
        }
        Ok(out)
    }
}
struct Huffman {
    codes: Vec<Vec<(u32, usize)>>,
}
impl Huffman {
    fn new(lengths: &[u32]) -> Result<Self, String> {
        let mut counts = [0_u32; 16];
        for &len in lengths {
            if len > 15 {
                return Err("invalid deflate code length".to_owned());
            }
            if len > 0 {
                counts[len as usize] += 1;
            }
        }
        let mut next = [0_u32; 16];
        for len in 1..16 {
            next[len] = (next[len - 1] + counts[len - 1]) << 1;
            if next[len] + counts[len] > 1 << len {
                return Err("oversubscribed deflate tree".to_owned());
            }
        }
        let mut codes = vec![Vec::new(); 16];
        for (symbol, &len) in lengths.iter().enumerate() {
            if len == 0 {
                continue;
            }
            let code = next[len as usize];
            next[len as usize] += 1;
            codes[len as usize].push((code.reverse_bits() >> (32 - len), symbol));
        }
        Ok(Self { codes })
    }
    fn symbol(&self, bits: &mut Bits<'_>) -> Result<usize, String> {
        let mut code = 0;
        for len in 1..16 {
            code |= bits.read(1)? << (len - 1);
            if let Some((_, symbol)) = self.codes[len].iter().find(|(v, _)| *v == code) {
                return Ok(*symbol);
            }
        }
        Err("invalid deflate symbol".to_owned())
    }
}
fn inflate(zlib: &[u8], limit: usize) -> Result<Vec<u8>, String> {
    if zlib.len() < 6
        || zlib[0] & 15 != 8
        || zlib[0] >> 4 > 7
        || zlib[1] & 32 != 0
        || (u16::from(zlib[0]) * 256 + u16::from(zlib[1])) % 31 != 0
    {
        return Err("invalid zlib header".to_owned());
    }
    let mut bits = Bits {
        data: &zlib[2..zlib.len() - 4],
        bit: 0,
    };
    let mut out = Vec::new();
    loop {
        let final_block = bits.read(1)? != 0;
        let kind = bits.read(2)?;
        if kind == 0 {
            bits.bit = (bits.bit + 7) & !7;
            let len = bits.read(16)? as usize;
            if bits.read(16)? != (!len as u32 & 65535) {
                return Err("invalid stored deflate length".to_owned());
            }
            if out.len() + len > limit {
                return Err("deflate exceeds raster limit".to_owned());
            }
            for _ in 0..len {
                out.push(bits.read(8)? as u8);
            }
        } else if kind <= 2 {
            let (literal, distance) = if kind == 1 {
                let lengths: Vec<_> = (0..288)
                    .map(|i| match i {
                        0..=143 => 8,
                        144..=255 => 9,
                        256..=279 => 7,
                        _ => 8,
                    })
                    .collect();
                (Huffman::new(&lengths)?, Huffman::new(&[5; 32])?)
            } else {
                let (nl, nd, nc) = (
                    bits.read(5)? as usize + 257,
                    bits.read(5)? as usize + 1,
                    bits.read(4)? as usize + 4,
                );
                let order = [
                    16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15,
                ];
                let mut lengths = [0; 19];
                for i in 0..nc {
                    lengths[order[i]] = bits.read(3)?;
                }
                let code = Huffman::new(&lengths)?;
                let mut all = Vec::new();
                while all.len() < nl + nd {
                    match code.symbol(&mut bits)? {
                        v @ 0..=15 => all.push(v as u32),
                        v @ 16..=18 => {
                            let (value, count) = match v {
                                16 => (
                                    *all.last().ok_or("deflate repeat without previous length")?,
                                    bits.read(2)? + 3,
                                ),
                                17 => (0, bits.read(3)? + 3),
                                _ => (0, bits.read(7)? + 11),
                            };
                            if all.len() + count as usize > nl + nd {
                                return Err("deflate code repeat overflow".to_owned());
                            }
                            all.extend(std::iter::repeat_n(value, count as usize));
                        }
                        _ => return Err("invalid deflate length symbol".to_owned()),
                    }
                }
                if all[256] == 0 {
                    return Err("deflate missing end code".to_owned());
                }
                (Huffman::new(&all[..nl])?, Huffman::new(&all[nl..])?)
            };
            loop {
                match literal.symbol(&mut bits)? {
                    v @ 0..=255 => {
                        if out.len() == limit {
                            return Err("deflate exceeds raster limit".to_owned());
                        }
                        out.push(v as u8);
                    }
                    256 => break,
                    v @ 257..=285 => {
                        const LENGTH: [usize; 29] = [
                            3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51,
                            59, 67, 83, 99, 115, 131, 163, 195, 227, 258,
                        ];
                        const EXTRA: [usize; 29] = [
                            0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4,
                            5, 5, 5, 5, 0,
                        ];
                        const DISTANCE: [usize; 30] = [
                            1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385,
                            513, 769, 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385,
                            24577,
                        ];
                        let length = LENGTH[v - 257] + bits.read(EXTRA[v - 257])? as usize;
                        let d = distance.symbol(&mut bits)?;
                        if d >= 30 {
                            return Err("invalid deflate distance code".to_owned());
                        }
                        let extra = if d < 4 { 0 } else { (d - 2) / 2 };
                        let back = DISTANCE[d] + bits.read(extra)? as usize;
                        if back > out.len() || out.len() + length > limit {
                            return Err("invalid deflate back reference".to_owned());
                        }
                        for _ in 0..length {
                            out.push(out[out.len() - back]);
                        }
                    }
                    _ => return Err("invalid deflate literal".to_owned()),
                }
            }
        } else {
            return Err("reserved deflate block type".to_owned());
        }
        if final_block {
            break;
        }
    }
    if adler32(&out) != be32(&zlib[zlib.len() - 4..]) {
        return Err("zlib Adler checksum mismatch".to_owned());
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn raster_round_trip_and_binary_separator() {
        let mut image = Image::new(300, 100, [10, 13, 32]).unwrap();
        image.pixels[1] = [255, 0, 128];
        assert_eq!(Image::from_ppm(&image.ppm()).unwrap(), image);
        assert_eq!(Image::from_png(&image.png()).unwrap(), image);
        let mut corrupt = image.png();
        corrupt[50] ^= 1;
        assert!(Image::from_png(&corrupt).is_err());
        assert!(Image::from_png(&corrupt[..40]).is_err());
        assert!(Image::new(usize::MAX, 2, [0; 3]).is_err());
    }
}
