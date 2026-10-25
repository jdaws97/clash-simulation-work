//! Reproducible declared-synthetic before/after mechanics battles and registry docs.
#[path = "../tests/support/mechanics.rs"]
mod mechanics;

fn main() {
    let catalog = mechanics::catalog();
    let command = std::env::args().nth(1);
    if command.as_deref() == Some("params") {
        print!("{}", clash_engine::params::Params::markdown());
        let mut delays: Vec<_> = catalog.new_target_delays.iter().collect();
        delays.sort_by_key(|(name, _)| *name);
        for (name, delay) in delays {
            println!("| `new_target_delay.{name}` | {delay} | game-data | seconds | Catalog new-target attack delay | ");
        }
    } else if command.as_deref() == Some("summary") {
        let evidence = mechanics::evidence(catalog);
        println!("| Synthetic demo | First target before → after | First building damage before → after | End time before → after |\n|---|---|---|---|");
        for case in evidence.at("cases").arr() {
            let before = case.at("before");
            let after = case.at("after");
            println!(
                "| {} | {} → {} | {} → {} | {} → {} |",
                case.at("id").str(),
                clash_engine::wire::to_json(before.at("samples").arr()[0].at("target")),
                clash_engine::wire::to_json(after.at("samples").arr()[0].at("target")),
                clash_engine::wire::to_json(before.at("first_building_damage")),
                clash_engine::wire::to_json(after.at("first_building_damage")),
                before.at("end_time").f64(),
                after.at("end_time").f64(),
            );
        }
    } else if command.as_deref() == Some("sizes") {
        println!(
            "Params={} Battle={} TargetMemory={} bytes (inline storage only)",
            std::mem::size_of::<clash_engine::params::Params>(),
            std::mem::size_of::<clash_engine::state::Battle>(),
            std::mem::size_of::<clash_engine::targeting::TargetMemory>(),
        );
    } else {
        println!("{}", mechanics::evidence_text(catalog));
    }
}
