MANUAL-ONLY HELD-OUT MATRICES AND LIGHT METRICS

Start with Technical_Notes_for_Thesis.txt for methods, numerical results, formulas and limitations.

figures/ contains 300 dpi PNG and editable-text SVG versions:
01 localization 9 x 9: conventional row-normalized percentages.
02 localization 9 x 9: separately labeled raw frame counts.
03 contact 2 x 2: conventional row-normalized percentages.
04 contact 2 x 2: separately labeled raw frame counts.
05-06 supplemental equal-recording normalized views, compatible with the earlier technical report.
07 optical response-distribution heatmap (a cross-talk proxy, not a classifier matrix).
08 response amplitude, temporal noise, active-area fraction, and response-to-noise proxy.
09 per-recording force-light correlation, with frame counts.

data/ contains full-precision CSV matrices, primary and supplemental family metrics, optical results by taxel and recording, fold-specific reference floors/noise, the original manual archive member manifest, and matched frame evidence in Parquet format.

Figure_Captions.txt provides thesis-ready captions. Technical_Notes_for_Thesis.txt is ready to supply to ChatGPT Writing alongside the earlier full report.

Primary model evidence is unchanged. All sources are manual calibration only. The light diagnostics use original acquisition CSV measurements; these are not claimed to be identical to the video-recomputed model features. See the technical notes before combining metrics from different weighting conventions or procedures.
