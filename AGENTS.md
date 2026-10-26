# Working rules

- Preserve the v29 engine behavior, deterministic math and explicit
  unsupported-content checks. Do not regenerate goldens for organizational work.
- Rust is the executable reference. Use `cargo fmt --all -- --check` and
  `scripts/verify.sh` for the offline workspace gate; root `verify.py` is absent.
- Retained Python tools use conventional multiline Python and Black 24.10.0.
  Use a writable local Black cache and one worker if required.
- Do not edit the original October 3 checkout or the preserved baseline.
- Keep real profiles, replay media, raw memory captures, transcripts and
  credentials out of Git. Retained working data belongs in ignored `local/` or
  explicitly selected `private/` paths; no memory acquisition workflow is retained.
- Use declared synthetic fixtures; never label synthetic results as real-game
  calibration. Preserve data hashes and fit/evaluation ancestry.
- Respect assigned file ownership. Coordinate shared-kernel edits with the
  integration lead; active writer lanes retain ownership of their files.
- See `docs/README.md` for current documentation and `docs/CLEANUP_G4.md` for
  retained Python workflows and pending Rust path updates.
