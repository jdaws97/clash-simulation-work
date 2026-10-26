use std::fs;
use std::io::{self, BufRead, Write};
use std::path::Path;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Rect {
    pub x: usize,
    pub y: usize,
    pub w: usize,
    pub h: usize,
}

impl Rect {
    pub fn new(x: usize, y: usize, w: usize, h: usize) -> Self {
        Self { x, y, w, h }
    }

    pub fn json(self) -> String {
        format!("[{}, {}, {}, {}]", self.x, self.y, self.w, self.h)
    }
}

#[derive(Clone)]
pub struct Image {
    pub w: usize,
    pub h: usize,
    pub data: Vec<u8>,
}

impl Image {
    pub fn blank(w: usize, h: usize) -> Self {
        Self {
            w,
            h,
            data: vec![0; w * h * 3],
        }
    }

    pub fn pixel(&self, x: usize, y: usize) -> [u8; 3] {
        let i = (y * self.w + x) * 3;
        [self.data[i], self.data[i + 1], self.data[i + 2]]
    }

    pub fn crop(&self, r: Rect) -> Self {
        let mut out = Self::blank(r.w, r.h);
        for y in 0..r.h {
            if r.y + y >= self.h || r.x + r.w > self.w {
                continue;
            }
            let src = ((r.y + y) * self.w + r.x) * 3;
            out.data[y * r.w * 3..(y + 1) * r.w * 3]
                .copy_from_slice(&self.data[src..src + r.w * 3]);
        }
        out
    }

    pub fn paste(&mut self, other: &Self, x: usize, y: usize, scale: usize) {
        for sy in 0..other.h {
            for sx in 0..other.w {
                let color = other.pixel(sx, sy);
                for dy in 0..scale {
                    for dx in 0..scale {
                        let tx = x + sx * scale + dx;
                        let ty = y + sy * scale + dy;
                        if tx < self.w && ty < self.h {
                            let i = (ty * self.w + tx) * 3;
                            self.data[i..i + 3].copy_from_slice(&color);
                        }
                    }
                }
            }
        }
    }

    pub fn save(&self, path: &Path) -> io::Result<()> {
        let mut file = fs::File::create(path)?;
        write!(file, "P6\n{} {}\n255\n", self.w, self.h)?;
        file.write_all(&self.data)
    }

    pub fn read(reader: &mut impl BufRead) -> io::Result<Option<Self>> {
        fn token(reader: &mut impl BufRead) -> io::Result<Option<String>> {
            let mut out = Vec::new();
            let mut b = [0];
            loop {
                if reader.read(&mut b)? == 0 {
                    return Ok(if out.is_empty() {
                        None
                    } else {
                        Some(String::from_utf8_lossy(&out).into_owned())
                    });
                }
                if b[0] == b'#' && out.is_empty() {
                    let mut line = String::new();
                    reader.read_line(&mut line)?;
                } else if b[0].is_ascii_whitespace() {
                    if !out.is_empty() {
                        return Ok(Some(String::from_utf8_lossy(&out).into_owned()));
                    }
                } else {
                    out.push(b[0]);
                }
            }
        }
        let Some(magic) = token(reader)? else {
            return Ok(None);
        };
        if magic != "P6" {
            return Err(io::Error::other("expected binary PPM (P6)"));
        }
        let mut number = || -> io::Result<usize> {
            token(reader)?
                .ok_or_else(|| io::Error::other("truncated PPM"))?
                .parse()
                .map_err(|_| io::Error::other("invalid PPM dimension"))
        };
        let w = number()?;
        let h = number()?;
        if number()? != 255 || w == 0 || h == 0 || w * h > 20_000_000 {
            return Err(io::Error::other("unsupported PPM"));
        }
        let mut image = Self::blank(w, h);
        reader.read_exact(&mut image.data)?;
        Ok(Some(image))
    }
}

#[derive(Clone, Debug)]
pub struct Mask {
    pub w: usize,
    pub h: usize,
    pub data: Vec<u8>,
}

impl Mask {
    pub fn keep_components(&self, min_height: usize, max_width: usize, min_pixels: usize) -> Self {
        let mut visited = vec![false; self.data.len()];
        let mut data = vec![0; self.data.len()];
        let mut stack = Vec::new();
        let mut component = Vec::new();
        for start in 0..self.data.len() {
            if self.data[start] == 0 || visited[start] {
                continue;
            }
            visited[start] = true;
            stack.push(start);
            component.clear();
            let mut x0 = self.w;
            let mut x1 = 0;
            let mut y0 = self.h;
            let mut y1 = 0;
            while let Some(i) = stack.pop() {
                component.push(i);
                let x = i % self.w;
                let y = i / self.w;
                x0 = x0.min(x);
                x1 = x1.max(x);
                y0 = y0.min(y);
                y1 = y1.max(y);
                for (nx, ny) in [
                    (x.wrapping_sub(1), y),
                    (x + 1, y),
                    (x, y.wrapping_sub(1)),
                    (x, y + 1),
                ] {
                    if nx < self.w && ny < self.h {
                        let j = ny * self.w + nx;
                        if self.data[j] != 0 && !visited[j] {
                            visited[j] = true;
                            stack.push(j);
                        }
                    }
                }
            }
            if y1 + 1 - y0 >= min_height
                && x1 + 1 - x0 <= max_width
                && component.len() >= min_pixels
            {
                for i in &component {
                    data[*i] = 1;
                }
            }
        }
        Self {
            w: self.w,
            h: self.h,
            data,
        }
    }

    pub fn white(image: &Image, threshold: u8) -> Self {
        let data = image
            .data
            .as_chunks::<3>()
            .0
            .iter()
            .map(|p| {
                let lo = *p.iter().min().unwrap();
                let hi = *p.iter().max().unwrap();
                u8::from(lo >= threshold && hi - lo < 85)
            })
            .collect();
        Self {
            w: image.w,
            h: image.h,
            data,
        }
    }

    pub fn crop(&self, r: Rect) -> Self {
        let mut data = vec![0; r.w * r.h];
        for y in 0..r.h {
            for x in 0..r.w {
                data[y * r.w + x] = self.data[(y + r.y) * self.w + x + r.x];
            }
        }
        Self {
            w: r.w,
            h: r.h,
            data,
        }
    }

    pub fn trimmed(&self) -> Option<(Rect, Self)> {
        let mut x0 = self.w;
        let mut y0 = self.h;
        let mut x1 = 0;
        let mut y1 = 0;
        for y in 0..self.h {
            for x in 0..self.w {
                if self.data[y * self.w + x] != 0 {
                    x0 = x0.min(x);
                    y0 = y0.min(y);
                    x1 = x1.max(x + 1);
                    y1 = y1.max(y + 1);
                }
            }
        }
        if x0 >= x1 {
            return None;
        }
        let rect = Rect::new(x0, y0, x1 - x0, y1 - y0);
        Some((rect, self.crop(rect)))
    }

    pub fn glyphs(&self) -> Vec<(Rect, Self)> {
        let mut out = Vec::new();
        let mut start = None;
        for x in 0..=self.w {
            let present = x < self.w && (0..self.h).any(|y| self.data[y * self.w + x] != 0);
            if present && start.is_none() {
                start = Some(x);
            }
            if !present {
                if let Some(x0) = start.take() {
                    let stripe = self.crop(Rect::new(x0, 0, x - x0, self.h));
                    if let Some((mut rect, glyph)) = stripe.trimmed() {
                        rect.x += x0;
                        if rect.h >= 4 && glyph.data.iter().map(|v| *v as usize).sum::<usize>() >= 6
                        {
                            out.push((rect, glyph));
                        }
                    }
                }
            }
        }
        out
    }

    pub fn normalized(&self) -> Self {
        let w = 16;
        let h = 24;
        let mut data = vec![0; w * h];
        for y in 0..h {
            for x in 0..w {
                data[y * w + x] = self.data[(y * self.h / h) * self.w + x * self.w / w];
            }
        }
        Self { w, h, data }
    }

    pub fn distance(&self, other: &Self) -> f64 {
        let different = self
            .data
            .iter()
            .zip(&other.data)
            .filter(|(a, b)| a != b)
            .count();
        different as f64 / self.data.len() as f64
    }

    pub fn as_image(&self) -> Image {
        let mut image = Image::blank(self.w, self.h);
        for (i, value) in self.data.iter().enumerate() {
            image.data[i * 3..i * 3 + 3].fill(value * 255);
        }
        image
    }

    pub fn save_text(&self, path: &Path) -> io::Result<()> {
        let mut text = format!("{} {}\n", self.w, self.h);
        for row in self.data.chunks(self.w) {
            for v in row {
                text.push(if *v == 0 { '.' } else { '#' });
            }
            text.push('\n');
        }
        fs::write(path, text)
    }

    pub fn load_text(path: &Path) -> io::Result<Self> {
        let text = fs::read_to_string(path)?;
        let mut lines = text.lines();
        let dimensions: Vec<usize> = lines
            .next()
            .unwrap_or("")
            .split_whitespace()
            .filter_map(|s| s.parse().ok())
            .collect();
        if dimensions.len() != 2 {
            return Err(io::Error::other("bad mask dimensions"));
        }
        let data: Vec<u8> = lines
            .flat_map(|s| s.bytes().map(|c| u8::from(c == b'#')))
            .collect();
        if data.len() != dimensions[0] * dimensions[1] {
            return Err(io::Error::other("bad mask data"));
        }
        Ok(Self {
            w: dimensions[0],
            h: dimensions[1],
            data,
        })
    }
}
