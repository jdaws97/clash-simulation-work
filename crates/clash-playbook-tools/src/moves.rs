use clash_data::wire::{self, list, obj, string};
use clash_plans::moves::{library, lower, validate, MoveLibrary};

use crate::{io, report, Options};

pub(super) fn command(options: &Options) -> Result<(), String> {
    let mode = options
        .positional
        .first()
        .map(String::as_str)
        .ok_or("moves needs index|check|lower")?;
    if options.positional.len() != 1 {
        return Err(
            "moves accepts one subcommand; use --playbooks to select the corpus".to_owned(),
        );
    }
    let root = options.root();
    let directory = options.path("moves", root.join("data/source/moves"));
    let books = library::read_books(&options.playbooks())?;
    for book in &books {
        let errors = crate::schema::validate(&book.value);
        if !errors.is_empty() {
            return Err(format!("{}: {}", book.source_file, errors.join("; ")));
        }
    }
    if mode == "index" {
        let path = options.path("out", directory.join("occurrences.json"));
        let previous = if path.exists() {
            Some(io::read(&path)?)
        } else {
            None
        };
        let indexed = library::index(&books, previous.as_ref())?;
        io::atomic_write(
            &path,
            clash_plans::moves::schema::format_json(&indexed).as_bytes(),
        )?;
        if options.has("roles") {
            let registry =
                MoveLibrary::from_json(&io::read(&directory.join("library.json"))?, &indexed)?;
            validate::check(&registry, &books)?;
            let catalog = wire::read(&clash_data::catalog::path(&root))?;
            io::atomic_write(
                &directory.join("roles.json"),
                clash_plans::moves::schema::format_json(&library::roles(
                    &books, &registry, &catalog,
                ))
                .as_bytes(),
            )?;
        }
        println!(
            "moves index: {} books, {} occurrences -> {}",
            books.len(),
            list(&indexed, "occurrences").len(),
            path.display()
        );
        return report(
            options,
            &obj([(
                "occurrences",
                wire::num(list(&indexed, "occurrences").len() as f64),
            )]),
        );
    }
    if !["check", "lower"].contains(&mode) {
        return Err(format!(
            "unknown moves command {mode}; use index|check|lower"
        ));
    }
    let registry = MoveLibrary::load(&directory)?;
    let catalog_path = clash_data::catalog::path(&root);
    let catalog_hash = wire::sha256(
        &std::fs::read(&catalog_path)
            .map_err(|error| format!("{}: {error}", catalog_path.display()))?,
    );
    if catalog_hash != registry.catalog_sha256 {
        return Err("move library catalog identity differs; review applicability before changing its pinned hash".to_owned());
    }
    let mut result = validate::check(&registry, &books)?;
    let role_matrix = library::roles(&books, &registry, &wire::read(&catalog_path)?);
    let recorded_roles = io::read(&directory.join("roles.json"))?;
    if clash_plans::moves::schema::canonical(&role_matrix)
        != clash_plans::moves::schema::canonical(&recorded_roles)
    {
        return Err(
            "move role matrix is stale; review and refresh with moves index --roles".to_owned(),
        );
    }
    wire::put(
        &mut result,
        "role_entities",
        wire::num(list(&role_matrix, "entities").len() as f64),
    );
    wire::put(
        &mut result,
        "lossless_books",
        wire::num(lower::check_books(&books, &registry)? as f64),
    );
    if mode == "lower" {
        if let Some(path) = options.get("out") {
            let output = std::path::Path::new(path);
            std::fs::create_dir_all(output).map_err(|error| error.to_string())?;
            for book in &books {
                let name = std::path::Path::new(&book.source_file)
                    .file_name()
                    .ok_or("invalid book name")?;
                let destination = output.join(name);
                if destination.canonicalize().ok()
                    == root.join(&book.source_file).canonicalize().ok()
                {
                    return Err("lower output must not overwrite a source book".to_owned());
                }
                io::write(&destination, &lower::lower_book(book, &registry)?)?;
            }
            wire::put(&mut result, "output", string(output.display().to_string()));
        }
    }
    if options.has("compiled") {
        wire::put(
            &mut result,
            "compiled_plans",
            lower::check_compiled_plans(
                &root,
                &clash_data::catalog::path(&root),
                &books,
                &registry,
            )?,
        );
    }
    report(options, &result)?;
    println!("moves {mode}: {}", wire::encode(&result));
    Ok(())
}
