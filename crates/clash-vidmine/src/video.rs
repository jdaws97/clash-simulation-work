use crate::image::Image;
use std::io::{self, BufReader};
use std::path::Path;
use std::process::{Child, ChildStdout, Command, Stdio};

pub struct Metadata {
    pub width: usize,
    pub height: usize,
    pub duration: f64,
}

pub fn metadata(video: &Path) -> io::Result<Metadata> {
    let result = Command::new("ffprobe")
        .args([
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=duration",
            "-of",
            "default=noprint_wrappers=1",
        ])
        .arg(video)
        .output()?;
    if !result.status.success() {
        return Err(io::Error::other(String::from_utf8_lossy(&result.stderr)));
    }
    let text = String::from_utf8_lossy(&result.stdout);
    let get = |key: &str| -> io::Result<f64> {
        text.lines()
            .find_map(|s| s.strip_prefix(key))
            .and_then(|s| s.parse().ok())
            .ok_or_else(|| io::Error::other(format!("missing ffprobe {key}")))
    };
    Ok(Metadata {
        width: get("width=")? as usize,
        height: get("height=")? as usize,
        duration: get("duration=")?,
    })
}

pub fn frame(video: &Path, t: f64) -> io::Result<Image> {
    if video
        .extension()
        .is_some_and(|s| s == "jpg" || s == "png" || s == "ppm")
    {
        return still(video);
    }
    let result = Command::new("ffmpeg")
        .args([
            "-v",
            "error",
            "-threads",
            "2",
            "-ss",
            &format!("{t:.3}"),
            "-i",
        ])
        .arg(video)
        .args(["-frames:v", "1", "-f", "image2pipe", "-vcodec", "ppm", "-"])
        .output()?;
    if !result.status.success() {
        return Err(io::Error::other(String::from_utf8_lossy(&result.stderr)));
    }
    Image::read(&mut io::Cursor::new(result.stdout))?.ok_or_else(|| io::Error::other("no frame"))
}

pub fn still(path: &Path) -> io::Result<Image> {
    let result = Command::new("ffmpeg")
        .args(["-v", "error", "-threads", "2", "-i"])
        .arg(path)
        .args(["-frames:v", "1", "-f", "image2pipe", "-vcodec", "ppm", "-"])
        .output()?;
    if !result.status.success() {
        return Err(io::Error::other(String::from_utf8_lossy(&result.stderr)));
    }
    Image::read(&mut io::Cursor::new(result.stdout))?
        .ok_or_else(|| io::Error::other(format!("no image in {}", path.display())))
}

pub fn jpeg(video: &Path, t: f64, out: &Path) -> io::Result<()> {
    let result = Command::new("ffmpeg")
        .args([
            "-v",
            "error",
            "-y",
            "-threads",
            "2",
            "-ss",
            &format!("{t:.3}"),
            "-i",
        ])
        .arg(video)
        .args(["-frames:v", "1", "-q:v", "2"])
        .arg(out)
        .output()?;
    if !result.status.success() {
        return Err(io::Error::other(String::from_utf8_lossy(&result.stderr)));
    }
    Ok(())
}

pub struct Stream {
    child: Child,
    reader: BufReader<ChildStdout>,
    ended: bool,
}

impl Stream {
    pub fn new(video: &Path, filter: &str) -> io::Result<Self> {
        let mut child = Command::new("ffmpeg")
            .args(["-v", "error", "-threads", "2", "-i"])
            .arg(video)
            .args([
                "-filter_complex_threads",
                "1",
                "-filter_complex",
                filter,
                "-an",
                "-f",
                "image2pipe",
                "-vcodec",
                "ppm",
                "-",
            ])
            .stdout(Stdio::piped())
            .spawn()?;
        let reader = BufReader::with_capacity(1024 * 1024, child.stdout.take().unwrap());
        Ok(Self {
            child,
            reader,
            ended: false,
        })
    }

    pub fn next(&mut self) -> io::Result<Option<Image>> {
        let image = Image::read(&mut self.reader)?;
        if image.is_none() {
            self.ended = true;
            if !self.child.wait()?.success() {
                return Err(io::Error::other("ffmpeg stream failed"));
            }
        }
        Ok(image)
    }
}

impl Drop for Stream {
    fn drop(&mut self) {
        if !self.ended {
            let _ = self.child.kill();
        }
        let _ = self.child.wait();
    }
}
