"""Write the thesis companion from the actual computed results."""
from pathlib import Path
import json
import pandas as pd

OUT=Path(__file__).resolve().parent
m=json.loads((OUT/'metrics_and_validation.json').read_text())
source=json.loads((OUT/'source_validation.json').read_text())
light=pd.read_csv(OUT/'data/light_metrics_by_taxel.csv')
sessions=pd.read_csv(OUT/'data/light_press_by_recording.csv')
loc=m['matrix_summaries']['localization']['metrics']
con=m['matrix_summaries']['contact']['metrics']
def pct(x):return f'{x*100:.4f}%'
table=['Taxel | Excess response (V levels) | Noise SD (V levels) | Response/noise | Active area (%) | Median force-light rho | Target response share (%)']
for _,r in light.iterrows():
    table.append(f"T{int(r.taxel)} | {r.mean_target_excess_delta_v:.4f} | {r.no_contact_rms_within_recording_sd_delta_v:.4f} | {r.mean_response_to_noise_ratio:.3f} | {r.mean_active_area_percent:.3f} | {r.median_force_light_spearman_rho:.3f} | {r.mean_target_response_share_percent:.2f}")
notes=f'''MANUAL CALIBRATION: HELD-OUT MATRICES AND LIGHT-RESPONSE METRICS
Technical companion for thesis writing
18 October 2026

1. PURPOSE AND EVIDENCE

This package provides a 9 x 9 localization confusion matrix for taxels T1-T9, a 2 x 2 contact/no-contact confusion matrix, separately labeled raw-count and conventional row-normalized figures, and optical diagnostics computed from the manual calibration archive only.

The model predictions are the saved six outer TEST-group-held-out predictions of the "Tuned selected" nested model-selection procedure from tuning_20260909. A recording is never split across outer folds. This is retrospective cross-validation: the recordings were used in prior development. It is not an untouched prospective test, and it is not an evaluation of the final full-data refit on its own training rows. The model family and tuned settings may differ between folds. No models were retrained and no predictions were changed for this package.

Localization includes 7,154 eligible positive frames from 54 recordings: nine taxels times six TEST groups. Contact includes these positives and 1,352 frames from 11 dedicated no-contact recordings, totaling 8,506 frames from 65 recordings. Positive eligibility retains the original lag-aligned 0.05-3 N interval, which remains exploratory. Replay-only and automatic calibration recordings are excluded. The sample sizes are frames and recordings, not independent subjects or devices.

Archive: {source['archive']}
Archive SHA-256: {source['archive_sha256']}
Prediction SHA-256: {source['prediction_sha256']}

2. HOW TO READ THE CLASSIFICATION MATRICES

Rows are ACTUAL class and columns PREDICTED class. T1-T9 are the same taxels/ROIs used in the existing configuration report. For contact, row/column order is No contact, Contact. The upper-left entry is TN, upper-right FP, lower-left FN, lower-right TP.

Raw counts: C[i,j] = number of eligible held-out frames with actual label i and predicted label j.
Conventional row normalization: R[i,j] = 100 C[i,j] / sum_j C[i,j].

Each normalized row sums to 100% before displayed rounding. Its diagonal is class recall. The mean diagonal is balanced accuracy; pooled accuracy is the sum of diagonal COUNTS divided by total frame count. These differ when class supports differ.

Figures 01/02 are the conventional normalized/raw localization views. Figures 03/04 are the conventional normalized/raw contact views. Raw counts are kept separate from percentages. Full-precision matrices are in data/.

The earlier thesis report used EQUAL-RECORDING weights: a frame in recording s has weight 1/n_s, where n_s is the evaluated frame count in that recording. Weighted confusion entries are summed before row normalization. Figures 05/06 retain that convention for comparison with the earlier report. They cannot be reconstructed by dividing unweighted frame counts. Do not silently substitute one weighting convention for the other.

Primary classification results:
Localization, pooled frames: accuracy {pct(loc['frame_weighted']['accuracy'])}; balanced accuracy {pct(loc['frame_weighted']['balanced_accuracy'])}; macro F1 {pct(loc['frame_weighted']['macro_f1'])}.
Localization, equal recording: accuracy {pct(loc['equal_recording']['accuracy'])}; macro F1 {pct(loc['equal_recording']['macro_f1'])}.
Contact, pooled frames: accuracy {pct(con['frame_weighted']['accuracy'])}; balanced accuracy {pct(con['frame_weighted']['balanced_accuracy'])}; contact recall {pct(con['frame_weighted']['recall'])}; contact F1 {pct(con['frame_weighted']['contact_f1'])}.
Contact, equal recording: accuracy {pct(con['equal_recording']['accuracy'])}; balanced accuracy {pct(con['equal_recording']['balanced_accuracy'])}; contact recall {pct(con['equal_recording']['recall'])}; contact F1 {pct(con['equal_recording']['contact_f1'])}.
Contact precision and observed specificity are 100% under both conventions. Raw counts [TN, FP; FN, TP] = [1352, 0; 308, 6846]. Zero observed false positives is limited to 11 archived no-contact recordings.

The strongest pooled localization confusion is T2 classified as T4: 257 of 493 true-T2 frames, or 52.13%. T2 recall is 32.86% in the frame-count view. T9 recall is 99.80%. Recording weights change these percentages because some recordings are much longer than others.

CSV-only supplements evaluate the tuned ensemble localization family and tuned RBF SVC contact family using their own saved outer-fold predictions. These correspond to families chosen for the final refits. Their predictions must not be mixed with the primary nested-selector counts. The SVC-family contact matrix is [1352, 0; 39, 7115]. These are retrospective family comparisons, not a new independent test of the final saved estimator.

3. OPTICAL SOURCE AND MATCHING

The original processed feature-store directory returned Windows access denied. The light-response diagnostics therefore read ORIGINAL ACQUISITION-TIME frame_features.csv files from the verified manual archive. The model matrices still use the original saved video-feature-based model predictions. Acquisition CSV values may differ from features recomputed from compressed video; this package does not claim they are numerically identical model inputs.

All 8,506 required optical rows were matched exactly by the stable frame UID: SHA-256 of archive hash, recording-directory ID, zero-based row/video index, and capture-frame ID. Capture timestamps were independently checked. There was no nearest-neighbor timestamp matching. Labels, validity flags, nine fixed ROI areas, intensity bounds, and count/fraction identities passed checks. All 65 saved baseline summaries specify an active-pixel threshold of 10 V levels. archive_member_manifest.csv lists the 65 source CSVs and their SHA-256 hashes.

4. DEFINITIONS OF THE LIGHT METRICS

V is the camera's 8-bit HSV Value channel. For pixel p in taxel j, positive change is max(V[p,t] - B[p], 0), where B is the saved per-pixel baseline. D[j,t] is the spatial mean of these positive changes: positive delta sum / ROI area. Its units are camera V levels (digital counts). A fractional ROI mean is valid even though individual image pixels are quantized. The reference floor below is an additional no-contact offset applied to this already baseline-subtracted feature.

For outer group g and taxel j, floor b[j,g] = median over training no-contact recordings of each recording's median D[j,t]. All controls assigned to group g are excluded. Excess response E[j,t] = max(D[j,t] - b[j,g], 0). The floors and exact control recording IDs are in light_fold_reference_floors_and_noise.csv. These diagnostics do not refit the prediction models.

Metric A: target light response. Average E for the true pressed taxel within each recording; average the six recording means for a taxel. This gives equal recording weight and retains zero-excess frames. Raw mean positive D is also in the CSV.

Metric B: no-contact temporal noise. Within each of 11 dedicated no-contact recordings, calculate the sample SD (ddof=1) of D for each taxel. Report sqrt(mean of the 11 variances), giving each recording equal weight. This measures temporal variation of an ROI mean, not spatial pixel noise. An additional robust measure is 1.4826 times temporal median absolute deviation, calculated within recording and summarized by its median across recordings.

Metric C: active area. 100 times active-pixel count / ROI area, where positive pixel delta V >= 10. Average within each positive recording and then across six recordings per taxel. This is a fraction of image pixels, not a physical contact area in square millimeters.

Metric D: response-to-noise ratio. For each positive recording, divide its mean target E by the RMS within-recording SD from only no-contact recordings OUTSIDE its held-out group. Average six recording ratios per taxel. This is a dimensionless diagnostic proxy. It is neither a power SNR in dB nor a calibrated photon/electrical SNR; zero-mean temporal noise, baseline drift, and acquisition differences have not been fully modeled.

Metric E: spatial response distribution / cross-talk proxy. Within each positive recording, average E for each of the nine taxels over ALL eligible frames. Normalize the nine means to sum to 100%. Then average the six recording profiles for each actual pressed taxel. Figure 07 is the resulting 9 x 9 optical heatmap. Every recording has a nonzero normalization denominator. All 7,154 frames are retained, including {int(light.zero_total_excess_frames.sum()):,} frames with zero total excess; those frames contribute zero to response sums. This is a profile of area-normalized camera response, not a probability confusion matrix or a measure of optical power leakage. Off-diagonal response can include light spread, mechanical coupling, illumination changes, or baseline mismatch; it does not identify a unique physical cause.

Metric F: force-light association. Compute Spearman correlation within each positive recording between the original aligned reference force and raw target D. Use no additional lag optimization. Report a 6 x 9 heatmap with each cell's frame count and the median of six correlations per taxel. These are descriptive correlations; frames are temporally dependent and recording supports range from {int(sessions.frames.min())} to {int(sessions.frames.max())}. Do not interpret an extreme correlation from a very short recording as strong general evidence. No independent-frame p-values or confidence intervals are claimed.

Other supplied diagnostics: median last-quarter minus first-quarter raw mean V during no contact (a short-recording drift descriptor), and counts of frames whose target ROI maximum V equals 255 (a clipping flag). A max-V flag is not the percentage of saturated pixels or a complete camera saturation assessment.

5. COMPUTED OPTICAL RESULTS

{chr(10).join(table)}

The nine mean excess responses range from {light.mean_target_excess_delta_v.min():.3f} to {light.mean_target_excess_delta_v.max():.3f} V levels. No-contact temporal noise ranges from {light.no_contact_rms_within_recording_sd_delta_v.min():.4f} to {light.no_contact_rms_within_recording_sd_delta_v.max():.4f} V levels. Response-to-noise proxies range from {light.mean_response_to_noise_ratio.min():.2f} to {light.mean_response_to_noise_ratio.max():.2f}. Median within-recording force-light correlations range from {light.median_force_light_spearman_rho.min():.3f} to {light.median_force_light_spearman_rho.max():.3f}, indicating variable and often weak-to-moderate monotonic association in this interval.

T4 has a broad optical response profile: its own taxel receives {light.loc[light.taxel==4,'mean_target_response_share_percent'].iloc[0]:.2f}% of the normalized response on average. This is not T4 localization recall: the model can use a multivariate response pattern. The optical profile and classification confusion matrix describe different quantities.

Cross-taxel response magnitudes are descriptive for the recorded force histories. Manual recordings have different force trajectories and durations, so these means cannot establish intrinsic sensitivity differences at matched force. No conversion to lux, lumens, irradiance, physical spatial resolution, a calibrated minimum detectable force, a fixed sensor gain, response time, or mechanical hysteresis is established by these summaries.

6. VALIDATION AND REPRODUCTION

Source matching and quality checks passed: {len(source['checks'])}. Analysis checks passed: {len(m['checks'])}. Full check names are retained in source_validation.json and metrics_and_validation.json. Numerical checks include independent count reconstruction, row sums, complete held-out groups, recording boundaries, reference-control separation, agreement with the prior recording-weighted model report, and nonzero optical normalization denominators. Figure inspection is recorded separately after rendering.

Run from the SOFTWARE CALIBRATION workspace, using the existing virtual environment:
calibration_gui/.venv/Scripts/python.exe reports/manual_calibration_matrices_and_light_metrics_2026-10-18/prepare_light_data.py --archive "C:/Users/DLSU/Downloads/THESIS DATA/Data Collection/Manual Calibration (2).zip"
calibration_gui/.venv/Scripts/python.exe reports/manual_calibration_matrices_and_light_metrics_2026-10-18/build_analysis.py
calibration_gui/.venv/Scripts/python.exe reports/manual_calibration_matrices_and_light_metrics_2026-10-18/write_notes.py

The first command verifies the source archive and writes matched evidence. The second rebuilds figures and numerical outputs using the saved tuning experiment and matched optical evidence. The third writes this text from those numerical results. The scripts do not change the training data, model bundles, model settings, or stored predictions.

7. THESIS WRITING INSTRUCTIONS

Use this document and Figure_Captions.txt as a companion to the existing full technical report and exact model/segmentation configuration export. Keep the conventional frame-count results distinct from equal-recording results. Identify the primary nested selection procedure and distinguish the family supplements. Explain the original-acquisition-CSV source of the light metrics separately from the video-recomputed model feature source. Preserve the exploratory force interval, retrospective validation status, temporal dependence, and uncalibrated camera-unit limitations. Do not describe any light-response percentage as classifier accuracy, and do not present these diagnostics as improved or retrained model scores.
'''
(OUT/'Technical_Notes_for_Thesis.txt').write_text(notes,encoding='utf-8')
(OUT/'README.txt').write_text('''MANUAL-ONLY HELD-OUT MATRICES AND LIGHT METRICS

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
''',encoding='utf-8')
print(json.dumps({'technical_notes_words':len(notes.split()),'source_checks':len(source['checks']),'analysis_checks':len(m['checks'])}))
