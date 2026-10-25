//! Command dispatch for the offline workspace and legacy binary names.

use std::ffi::OsString;
use std::process::ExitCode;

pub use clash_armysearch as armysearch;
pub use clash_basesearch as basesearch;
pub use clash_engine::*;
pub use clash_plans::{armies, compile};
pub use clash_scoring::{scoring, scouting};

pub mod compile_cli;
pub mod golden;
pub mod jobs;
pub mod layout_cli;
pub mod layout_proof;
pub mod layout_rules;
mod legacy;
pub mod plan_golden;
#[path = "scoring_cli.rs"]
pub mod score_cli;

fn text_arguments(arguments: Vec<OsString>) -> Result<Vec<String>, String> {
    arguments
        .into_iter()
        .map(|argument| {
            argument
                .into_string()
                .map_err(|_| "tool arguments must be valid UTF-8".to_owned())
        })
        .collect()
}

pub fn run(mut arguments: Vec<OsString>) -> Result<(), String> {
    let command = arguments.first().and_then(|value| value.to_str());
    match command {
        Some("--help" | "-h" | "help") => {
            println!(concat!(
                "clash run|trace|jobs|bench-runner|stats-check|setup-check|trace-job ...\n",
                "clash compile|compile-check|score|score-check ...\n",
                "clash golden check|record ... | golden plans check|record ...\n",
                "clash guardian-check | armysearch ... | armysearch-proof ...\n",
                "clash layout ... | basesearch-proof ...\n",
                "clash fidelity ... | video ...\n",
                "Aliases: simulate run|trace|jobs|bench; plan compile|check; ",
                "armysearch run|proof; basesearch proof; vidmine ...\n",
                "Existing subcommand arguments are preserved."
            ));
            return Ok(());
        }
        Some("fidelity") => {
            arguments.remove(0);
            return clash_fidelity::run(text_arguments(arguments)?);
        }
        Some("video" | "vidmine") => {
            arguments.remove(0);
            return clash_vidmine::run(text_arguments(arguments)?)
                .map_err(|error| error.to_string());
        }
        Some("simulate") => {
            arguments.remove(0);
            if arguments.first().and_then(|value| value.to_str()) == Some("bench") {
                arguments[0] = OsString::from("bench-runner");
            }
        }
        Some("plan") => {
            arguments.remove(0);
            if arguments.first().and_then(|value| value.to_str()) == Some("check") {
                arguments[0] = OsString::from("compile-check");
            }
        }
        Some("armysearch") => match arguments.get(1).and_then(|value| value.to_str()) {
            Some("run") => {
                arguments.remove(1);
            }
            Some("proof") => {
                arguments.remove(1);
                arguments[0] = OsString::from("armysearch-proof");
            }
            _ => {}
        },
        Some("basesearch")
            if arguments.get(1).and_then(|value| value.to_str()) == Some("proof") =>
        {
            arguments.remove(1);
            arguments[0] = OsString::from("basesearch-proof");
        }
        _ => {}
    }
    legacy::run(arguments)
}

pub fn entry(arguments: Vec<OsString>) -> ExitCode {
    match run(arguments) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("clash: {error}");
            ExitCode::FAILURE
        }
    }
}
