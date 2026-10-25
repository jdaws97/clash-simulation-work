# M4 reviewed Town Hall features

Each `.rgb` file contains a TH label, a source ID and 1,680 decimal RGB bytes
(20×28×3). These are small derived sprite features, not full replay frames.
`spatial-learn` reads a reviewed TSV with fields
`source image cx top a b center_x center_y level`. It supports labels 16–18 only.
The center is the chosen sprite reference point in native source pixels; feature
sampling spans 9 horizontal tile steps and vertical offsets -8b through +2b.
Masks in the matcher exclude extreme corners and the lowest ground pixels.

The source images were viewed manually. TH16 examples show the red/gold nature
building, TH17 examples the gold eagle/artillery roof, and TH18 examples the
wooden roof and blue meteor columns. Defender names and video titles were not
used as labels. The local editor images add TH16 examples absent from the two
dev battle sets. They are training data, not independent battle validation.

`provenance.tsv` records image/time, normalization and inspected centers. Video
frames were temporary under `/tmp/vidmine-work-m4` and must be deleted after
review. Regenerating those pixels requires the caller's read-only source videos.
Saved legacy JPEGs and local editor images remain in their existing output
locations; no source media is added to Git. The fitted origin is provisional;
only a and b determine a feature's normalization once its center is labeled.

Six dev keyframes supply TH18 variants. Their measurements are resubstitution
and must be excluded from the non-template accuracy denominator. The library
is intentionally small and rendering-specific. A positive similarity margin
is not a calibrated confidence or proof that an unfamiliar building is a TH.
