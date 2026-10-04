# Publication baseline

This baseline imports a reviewed source tree derived from local integration
checkpoint `4ce79a13ffe4e3d862f829603392e31fc702161d`. Publication adds a child of
the destination repository's existing `main` commit, preserving that history.
The source checkpoint and its development history remain preserved locally;
unreviewed historical blobs are not part of this import.

Included: engine source, development tools, conditional examples, pinned public
data snapshots with separate notices, a synthetic TH16 account, compact neutral
blueprint and execution fixtures, and synthetic replay schema/hash cases. The
legacy observed-counts army example is excluded; the demo uses an experiment
recipe instead. No new numerical behavior is introduced by publication.

Excluded: real player profiles, replay observations and media, raw memory
captures, session transcripts, credentials, environments, caches, generated
reports and large runtime output. Optional private replay integrity verification
remains a separate explicit command. Source tools for inspecting a local process
are preserved as code, but neither the portable tests nor CI run them.

The three public data inputs retain their own attribution and provenance in
[THIRD_PARTY.md](../THIRD_PARTY.md). Catalog and Statscell carry separate MIT
notices; the ClashKing Assets extraction retains its GNU GPL version 3 notice.
No blanket MIT license or rights to Supercell media are asserted.

## Reproducibility

Run from a clean checkout with Python 3.10 or newer:

```console
python -B verify.py
python -B run.py --data data --output reports/catalog-audit.json audit
python -B tools/run_full_army_regression.py
python -B tools/build_candidate_bundle.py --output reports/candidates
python -m pip install black==24.10.0
python -m black --check --workers 1 .
git diff --exit-code
```

CI checks the exact pull-request head on Ubuntu and Windows, Python 3.10 and
3.12, with at most two regression matrix jobs at once, plus one formatting job.
Regression jobs have a ten-minute limit. The existing combined-army suite checks
two identical synthetic runs, resource ownership and explicit unsupported-input
rejection. Candidate output checks inventory and geometry, not game performance.

## Known limitation

The preserved original full-air case encounters genuine Dragon Duke isolation
contact chatter at **18.305471759 simulated seconds**. The baseline reports an
explicit unsupported-contact diagnostic; battle completion is unproven. A
separate isolated investigation owns that numerical behavior and is not included
in this publication.

Passing software checks establish portable execution and declared contracts.
They do not establish live-game calibration, trajectory convergence, a reliable
army ranking, or optimal base recommendations. Keep this pull request in draft
until its limited baseline scope has been reviewed. Do not merge or deploy as
part of publication.
