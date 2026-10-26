> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Complete Giga Bomb response selection

The paid v27+ scene accepts `giga_bomb_response_binding`. It expands only after
all ordinary actors, heroes, paired pets and finite generated reserves have been
compiled. The existing raw runtime still requires exactly every attacking unit;
the trap remains in the battle, with its catalog threshold/radii/damage and
existing delayed blast, protection, displacement and continuation behavior.

The binding has exactly these fields:

```json
{
  "source": "caller-evidence-or-explicit-hypothesis",
  "status": "explicit_uncalibrated_hypothesis",
  "selection": "exact_actor_then_catalog_identity",
  "actor_responses": {},
  "entity_responses": {}
}
```

Each entry in either response map has `trigger_weight`, `damage_multiplier`, and
`push_multiplier`. Trigger weight is an explicit nonnegative integer. Only an
entity response may instead request `"catalog_housing_space"`, which requires
the catalog identity to have an integer housing quantity. Damage and push are
explicit nonnegative finite multipliers. No hero, pet, siege or child weight or
response coefficient is inferred. Exact actor entries take precedence.

Compiler-generated summons, clones, spell units/decoys and siege barrel children
require exact actor entries; they cannot inherit a parent identity's response.
Regular controlled army and donated CC reserves may use exact catalog identity.
All attacker identities must resolve, and stale actor entries fail closed.
Unused valid entity selectors permit a caller's explicitly supplied family table.

Every selected Giga Bomb must have an **empty** input `unit_responses` map when
this binding is used. This prevents silently replacing an old, contradictory
roster. Without the binding, the existing exact per-actor response interface
remains unchanged. Supplying a binding without a Giga Bomb is rejected.

The compiled scene records `giga_bomb_response_audit`, including capability
`complete-giga-response-binding-v1`, exact actor selections, numeric responses,
trap IDs and pinned catalog commit. The input scene is not mutated.

For the layout pipeline, replace its unconditional higher-TH rejection only
after the owner explicitly supplies this contract and clears the legacy trap
map. Its synthetic hero/pet/Mirror hypotheses must be named; they are not game
facts. The pipeline's independent audit fixes and recheck remain separate.

Two bounded paid family checks cover TH16 versus TH18 with active crafted defense,
troops, Queen, Unicorn, finite Mirror children and a later controlled reserve.
They verify one actual delayed blast, per-recipient requested/effective damage,
reserve death, paid deployment/ability receipts, two step limits, unchanged inputs,
missing child/pet responses, stale/ambiguous maps and the raw missing-ID guard.
Pinned statistics remain unverified; complete held-out game calibration is zero.
