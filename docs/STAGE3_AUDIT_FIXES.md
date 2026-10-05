# Stage 3 follow-up corrections

This checkpoint is based on stage 3 commit
`7f150ed9afff1b8629f5fee751744d7a8681c45a`. It remains unpublished and requires
the original reviewers' independent rechecks. All cases are declared synthetic
contracts, not game calibration.

Shared health now accepts sparse damage and healing dictionaries. Omitted known
actors receive zero; every supplied recipient must exist and every amount must
be finite and nonnegative. Validation precedes receipt settlement and actor
mutation. Receipt attribution and protection remain unchanged. Other sparse
producers include recipe troop damage and the unbound Logger component; the
contract is fixed centrally rather than padding the Earthquake producer alone.

The raw shared-kernel boundary now includes `inferno_ammunition_model` in its
v26-or-later capability guard. An ordinary v13 Inferno remains usable without
the optional ammunition hypothesis. Valid v26 zero-fuel behavior remains bound.

Town Halls explicitly declared initially active enter their defense state before
time-zero ability selection. Only the initial active declaration is processed in
this phase. Dormant damage/threshold activation, hazard settlement, activation
delay and ordinary freeze handling retain their existing mechanisms. A Seeking
Shield can select the initially active Hall; released impacts persist after the
Royal Champion dies. A dormant Hall remains ineligible until ordinary activation.

Six added regression methods cover sparse maps and malformed recipients, a paid
TH17 live-source Earthquake with an unaffected Hall at two solver steps, four
Titan/Earthquake clock arrangements at two steps (including lethal suppression),
raw Inferno scope and controls, time-zero/delayed Shield after source loss at two
steps, and dormant Hall control. The full portable suite passes 1,311 tests.

External, uncommitted probes also replayed the original reviewer inputs. The
time-zero Shield now impacts at 0.7549509756796392 after source death at 0; Hall
HP is 7,500. The delayed v28 control retains its impact and attack-exhaustion
time of 0.7649509756796392 after source death at 0.256. Life Gem and Archer Puppet
original outcomes and resources remain equal to the reviewers' stage-3 results.

Advanced spell bindings, the Flinger overlap correction and its positive tail
continuation edge, other unbound families and Root Rider TH16 throughput remain
separate work. This correction does not claim their acceptance.
