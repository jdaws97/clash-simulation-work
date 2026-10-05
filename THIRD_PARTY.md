# Third-party data

The engine uses separately attributed source snapshots. No blanket license for
this repository is asserted. These notices apply to the listed upstream inputs,
not to Supercell artwork or to private player observations.

| Input | Pinned source | Upstream notice retained here |
| --- | --- | --- |
| `data/catalog.json` | [chiefpansancolt/clash-of-clans-data, c6967314](https://github.com/chiefpansancolt/clash-of-clans-data/tree/c6967314d7281bb87c362993e2635e58cd77b351) | [MIT](data/DATA-LICENSE.txt) |
| `data/secondary-raw.json` | [Statscell/clash-of-clans-data, 7c30a6da](https://github.com/Statscell/clash-of-clans-data/tree/7c30a6da56a337aee9d6f2b4e0e6be3a5861b350) | [MIT](data/SECONDARY-LICENSE.txt) |
| `data/clashking-static-data.json` | [ClashKingInc/ClashKingAssets, b8f42a70](https://github.com/ClashKingInc/ClashKingAssets/tree/b8f42a707fe92d5293d46088bf536450ae422e7b) | [GNU GPL version 3](data/CLASHKING-LICENSE.txt) |

Credit: ClashKing extracted and published the static game data; Clash of Clans
belongs to Supercell. The ClashKing input is retained separately from the two MIT
inputs. Its original path is `assets/static_data.json`; its SHA-256 is
`ff2b72ec8a71b403d247b061c5d0edb0c59dfe0dbea8f199f3451de2ece26cb8`.
See [the provenance record](data/clashking-static-source.json) for the exact URL.

The pinned ClashKing LICENSE was checked against Git blob
`f288702d2fa16d3cdf0035b15a9fcbc552cd88e7`. Attribution and the actual full notice
are preserved; the existing MIT notices do not cover that input. Private media,
game-memory captures, account screenshots, and session transcripts are excluded.

Source agreement is not model calibration. The snapshot contains unresolved
conflicts and uncertain interpretations. The engine requires explicit selection
policies rather than automatically replacing one source with another.
