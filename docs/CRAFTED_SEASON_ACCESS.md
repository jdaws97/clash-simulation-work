# Explicit seasonal Crafting Station access

Base: e6ec982cb4a5086baed63588413c7eaba39f9858. This supersedes the TH18-only
shared gate recorded in the frozen stage6 checkpoint, without editing that tree.

The [official July 31, 2026 announcement](https://supercell.com/en/games/clashofclans/blog/news/the-awesome-quest-is-here/)
states that the season opening August 1 offers Cake-A-Pult, Hero Hunter and Hot
Candle from TH11. That specific exception takes precedence over the permanent
Station unlock in the pinned catalog. It does not certify the trio's October
rotation. The user's current TH16 Station presence is separate observed context;
this engine requires the selected variant and independent module levels instead
of guessing which weapon is present.

The explicit availability_policy is:
official_august_2026_phase4_th11_plus_not_current_date_certified.
It belongs in crafted_parameters and the matching layout settings.crafted.
The existing phase=4, variant, as_of_date, rotation_policy and module_levels remain
required. Observation dates precede neither the August 1 opening nor ISO syntax.
No current-date auto-selection is introduced. Legacy TH18 inputs without the new
key retain permanent-access compatibility; lower TH inputs require the season key.

One helper owns the same TH11–18 availability, source-module and geometry gates.
The adapter no longer rejects selected lower-TH Stations before reaching that
helper. The domain compiler, shared raw contract, full-battle layout binding and
geometry validator retain exact selection provenance. The result reports the
official URL, publication/start dates, selected TH, and unverified current rotation.
The permanent Catalog.available result remains unchanged.

The selected building must be a counted level-1 normal-mode Crafting Station.
Each chosen weapon has the Station's 3x3 footprint. Inventory admits exactly one
physical Station, including the temporary lower-TH exception; modules do not add
buildings, paid resources or destruction credit. Missing selections, extra Stations,
passive substitutions, unknown rotations and mismatched raw provenance fail closed.
Passive permanent TH18 benchmark Stations remain separate explicit inputs.

All three pinned secondary module families independently require TH11..17 at
module levels1..7 and TH18 at levels8..10. Thus TH16 permits each module through
level6, including mixed module levels; season access does not grant level10 stats.
The immutable source digest and crosschecked combat statistics are unchanged from
CRAFTED_SHARED_CHECKPOINT.md. No stats were inferred from the announcement.

Three focused tests cover paid TH16 vs TH16 Cake/Hunter/Candle source death at0,
released damage at.1, actual attacker exhaustion, one Station credit and finite
attacker accounting at steps.017/.25; compiler and geometry admission throughout
TH11–18 with independent module caps and exactly25 occupied tiles for Hall+Station;
and source/date/phase/module/count/mode/raw/legacy negative controls. These augment
the earlier paid shared weapon lifecycle tests, rather than replace them.

This corrects engine legality and input binding. It does not insert a guessed
weapon into a user's blueprint or certify old nonseasonal benchmark inventories as
current. Blueprint authors must add the observed Station once and supply its
confirmed weapon/modules. All combat policies remain explicitly conditional.
Independent recheck is pending. Complete held-out game calibration: zero.
