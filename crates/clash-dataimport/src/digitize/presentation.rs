//! Screenshot inspection, portable galleries and layout build guides.
use super::buildings::{size, trap_size};
use super::fit::{self, Grid};
use clash_data::catalog::Catalog;
use clash_layout::model::Layout;
use clash_layout::render::Image;

pub fn overlay(
    image: &Image,
    grid: Grid,
    layout: Option<&Layout>,
    catalog: &Catalog,
) -> Result<Image, String> {
    let mut out = fit::overlay(image, grid);
    if let Some(layout) = layout {
        for b in &layout.buildings {
            let s = f64::from(size(catalog, &b.key)?);
            let (x, y) = (f64::from(b.position.0), f64::from(b.position.1));
            let points = [
                grid.project(x, y),
                grid.project(x + s, y),
                grid.project(x + s, y + s),
                grid.project(x, y + s),
            ];
            out.polygon(&points, [0, 255, 255], 255);
            let p = grid.project(x + s / 2.0, y + s / 2.0);
            out.text(p.0 as i32 - 8, p.1 as i32 - 3, &b.key, [0, 255, 255]);
        }
        for wall in &layout.walls {
            let (x, y) = (f64::from(wall.position.0), f64::from(wall.position.1));
            out.polygon(
                &[
                    grid.project(x + 0.2, y + 0.2),
                    grid.project(x + 0.8, y + 0.2),
                    grid.project(x + 0.8, y + 0.8),
                    grid.project(x + 0.2, y + 0.8),
                ],
                [255, 0, 255],
                200,
            );
        }
        for trap in &layout.traps {
            let s = f64::from(trap_size(catalog, &trap.key)?);
            let p = grid.project(
                f64::from(trap.position.0) + s / 2.0,
                f64::from(trap.position.1) + s / 2.0,
            );
            out.line((p.0 - 4.0, p.1), (p.0 + 4.0, p.1), [255, 80, 0], 255);
            out.line((p.0, p.1 - 4.0), (p.0, p.1 + 4.0), [255, 80, 0], 255);
        }
    }
    Ok(out)
}

pub fn guide(layout: &Layout, catalog: &Catalog) -> Result<Image, String> {
    let grid = Grid {
        cx: 720.0,
        top: 30.0,
        a: 15.0,
        b: 10.0,
    };
    let image = Image::new(1440, 950, [28, 45, 28])?;
    overlay(&image, grid, Some(layout), catalog)
}

pub fn gallery(
    images: &[Image],
    columns: usize,
    cell_width: usize,
    cell_height: usize,
) -> Result<Image, String> {
    if images.is_empty() || columns == 0 || cell_width == 0 || cell_height == 0 {
        return Err("invalid gallery dimensions".to_owned());
    }
    let rows = images.len().div_ceil(columns);
    let mut out = Image::new(
        columns.checked_mul(cell_width).ok_or("gallery overflow")?,
        rows.checked_mul(cell_height).ok_or("gallery overflow")?,
        [20; 3],
    )?;
    for (index, image) in images.iter().enumerate() {
        let scale =
            (cell_width as f64 / image.width as f64).min(cell_height as f64 / image.height as f64);
        let width = (image.width as f64 * scale).floor() as usize;
        let height = (image.height as f64 * scale).floor() as usize;
        let left = index % columns * cell_width;
        let top = index / columns * cell_height;
        for y in 0..height {
            for x in 0..width {
                let sx = (x as f64 / scale).floor() as usize;
                let sy = (y as f64 / scale).floor() as usize;
                out.pixels[(top + y) * out.width + left + x] = image.pixels[sy * image.width + sx];
            }
        }
        out.text(
            left as i32 + 2,
            top as i32 + 2,
            &format!("{}", index + 1),
            [255; 3],
        );
    }
    Ok(out)
}

pub fn ascii(layout: &Layout, catalog: &Catalog) -> Result<String, String> {
    let mut rows = vec![vec!['.'; 44]; 44];
    for wall in &layout.walls {
        let (x, y) = wall.position;
        if (0..44).contains(&x) && (0..44).contains(&y) {
            rows[y as usize][x as usize] = '#';
        }
    }
    for b in &layout.buildings {
        for (x, y) in super::buildings::footprint(b.position, size(catalog, &b.key)?) {
            if (0..44).contains(&x) && (0..44).contains(&y) {
                let cell = &mut rows[y as usize][x as usize];
                *cell = if *cell != '.' {
                    '!'
                } else {
                    b.key.chars().next().unwrap_or('?').to_ascii_uppercase()
                };
            }
        }
    }
    Ok(rows
        .into_iter()
        .map(|r| r.into_iter().collect::<String>() + "\n")
        .collect())
}

pub fn ruler(
    image: &mut Image,
    origin: (usize, usize),
    zoom: usize,
    step: usize,
) -> Result<(), String> {
    if zoom == 0 || step == 0 {
        return Err("ruler zoom/step must be positive".to_owned());
    }
    for x in 0..image.width {
        let coordinate = origin.0 + x / zoom;
        if coordinate % step == 0 && x % zoom == 0 {
            image.line(
                (x as f64, 0.0),
                (x as f64, image.height as f64),
                [255, 255, 0],
                100,
            );
            image.text(x as i32 + 1, 1, &coordinate.to_string(), [255, 255, 0]);
        }
    }
    for y in 0..image.height {
        let coordinate = origin.1 + y / zoom;
        if coordinate % step == 0 && y % zoom == 0 {
            image.line(
                (0.0, y as f64),
                (image.width as f64, y as f64),
                [0, 255, 255],
                100,
            );
            image.text(1, y as i32 + 1, &coordinate.to_string(), [0, 255, 255]);
        }
    }
    Ok(())
}

/// Optional inspection transform from dewm.py: estimate the washed-out region
/// with a separable sigma=3 Gaussian, then invert the explicit white opacity.
/// It is never used by detection or fitting without the user choosing it.
pub fn undo_white_overlay(image: &Image, alpha: f64) -> Result<Image, String> {
    if !alpha.is_finite() || !(0.0..1.0).contains(&alpha) {
        return Err("white opacity must be in 0..1".to_owned());
    }
    let mut weights: Vec<_> = (-9_i32..=9)
        .map(|i| (-f64::from(i * i) / 18.0).exp())
        .collect();
    let total = weights.iter().sum::<f64>();
    for weight in &mut weights {
        *weight /= total;
    }
    let mask: Vec<_> = image
        .pixels
        .iter()
        .map(|p| if p.iter().all(|&v| v > 95) { 1.0 } else { 0.0 })
        .collect();
    let mut horizontal = vec![0.0; mask.len()];
    let mut blurred = vec![0.0; mask.len()];
    for y in 0..image.height {
        for x in 0..image.width {
            for (index, &weight) in weights.iter().enumerate() {
                let sx = (x as i32 + index as i32 - 9).clamp(0, image.width as i32 - 1) as usize;
                horizontal[y * image.width + x] += mask[y * image.width + sx] * weight;
            }
        }
    }
    for y in 0..image.height {
        for x in 0..image.width {
            for (index, &weight) in weights.iter().enumerate() {
                let sy = (y as i32 + index as i32 - 9).clamp(0, image.height as i32 - 1) as usize;
                blurred[y * image.width + x] += horizontal[sy * image.width + x] * weight;
            }
        }
    }
    let mut out = image.clone();
    for (pixel, wash) in out.pixels.iter_mut().zip(blurred) {
        let opacity = alpha * (wash * 1.2).clamp(0.0, 1.0);
        for channel in pixel {
            *channel =
                ((f64::from(*channel) - opacity * 255.0) / (1.0 - opacity)).clamp(0.0, 255.0) as u8;
        }
    }
    Ok(out)
}
