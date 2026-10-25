fn main() -> std::process::ExitCode {
    clash_cli::entry(std::env::args_os().skip(1).collect())
}
