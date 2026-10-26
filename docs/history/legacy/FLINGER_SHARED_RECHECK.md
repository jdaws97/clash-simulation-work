> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Flinger shared continuation correction

Based on audit-fix checkpoint `59664f99b0ff1d902e990ae7bca97f34417d349e`.
The independently accepted conditional domain delta from
`0c622a13b22fc109607f89d32e2d2742f03247cc` is integrated here. Its source patch
SHA-256 is `05afa60f16862ab84f2a70b0f13214bcc87831033ad390a66f4b4133e47df2e3`.
Original reviewer acceptance does not automatically cover the additional
integration changes below. This checkpoint remains unpublished.

The shared siege continuation wrapper already dispatches to the lifecycle
provider once and passes the actual settled time from the main collector. The
public wrapper now rejects omission of that time for new lifecycle owners;
legacy owners without a provider retain the original packet collector. A future
unlaunched Flinger shot remains a cancellable launch intention, never a forged
damage receipt.

Shared termination now compares pending damage and expiry clocks exactly. A
positive interval smaller than the geometric tolerance must still settle.
Already-due offensive work continues to reject termination. The source's final
partial interval at [0.5499999999999999, 0.55) now continues to 0.55.

A stricter regression exposed a second numerical issue in the integrated domain
delta: the midpoint of that one-ULP interval rounds to its expiry, making its
rate zero. The integral now splits at every creation, expiry and ramp boundary
and evaluates the right-continuous rate at each interval's left endpoint. Ramp
index selection compares the declared absolute ramp boundaries directly. The
tail produces positive requested damage instead of disappearing. This additional
domain edit specifically needs the same siege reviewer's recheck.

The real compiler/launch/resolve/receipt/health/continuation/termination fixture
settles the original short-field union for 40 flame damage and ends at 0.55. Other
fixture troops receive explicit synthetic casualties only after deployment so
the flame clock alone determines this component termination probe. A separate
paid v28 full battle at steps 0.017 and 0.25 exercises short fields, carrier
release and exactly one CC delivery through the normal shared kernel; both runs
produce identical flame event times and amounts. Existing paid Flinger and
Barracks tests also remain included in the full portable suite.

These are declared conditional contracts, not live-game calibration. Drill,
Launcher/Wagon, further spell wiring, and other unsupported families retain
their existing acceptance limits.
