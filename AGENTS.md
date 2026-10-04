# Working rules

- Preserve the v29 engine and its explicit unsupported-content checks.
- Use conventional multiline Python and Black 24.10.0.
- Do not edit the original October 3 checkout or the preserved baseline.
- Keep real profiles, replay media, raw memory captures, transcripts and credentials out of Git.
- Use declared synthetic fixtures; never label synthetic results as real-game calibration.
- Respect assigned file ownership. Coordinate shared-kernel edits with the integration lead.
- Test with `python -B verify.py`; use writable local Black cache and one worker if required.
