fn main() -> std::process::ExitCode {
    let mut arguments = vec![std::ffi::OsString::from("video")];
    arguments.extend(std::env::args_os().skip(1));
    clash_cli::entry(arguments)
}
