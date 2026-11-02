# BAURods Live Demo

Double-click **run_baurods_demo.bat** in the project root. For a rehearsal without hardware, choose **RECORDED VIDEO REPLAY → Center press → Start**. **F11** enters presentation mode and **Esc** exits it. The two input modes share the same optical extractor, fitted classifiers and display.

**Current laptop setup.** Select **LIVE CAMERA**, camera index **1**, and **SVC + rapid V tap** next to Contact Status. Press **Start**, release all rods, and choose **Capture unloaded baseline**. The active tile identifies a rod with a confirmed optical response. A lit rod can flash brighter or go dark as a hand presses it. Watch its signed brightness rate in the footer.

To reopen the guided **R7 / R8 / R9 light check**, double-click **run_baurods_light_check.bat** in the project root. The blue **Start light check** button records two cued rounds after the unloaded baseline. Choose **Yes · open normal demo** if you completed the cues, or **Timing uncertain · open demo** if the timing was off. Both finish saving the recording, release the camera and open the regular GUI. You can also return early with **End check · open normal demo**. In the normal GUI, press **Start** and capture a fresh unloaded baseline. Each check has its own folder under **output/baurods_demo/diagnostics**.

## Defense checklist

1. Connect the IMX179 and secure the underside camera and lighting. Choose **LIVE CAMERA**, select its camera index and press **Start**. Confirm that the nine numbered rectangles cover their rods. The trained input is 640 × 480 landscape. Advanced shows the actual driver readbacks.
2. Release all nine taxels and press **Capture unloaded baseline**. Keep the array unloaded through the three-second camera warm-up and baseline collection. Collection needs at least three seconds and 20 valid frames. Wait for a ready baseline in diagnostics, then check the unloaded contact status.
3. On a new or moved mount, choose **Check mapping…** during an unrecorded live run. Press the marked physical position on the top side. Read the numbered region in the camera, release, and confirm the observed ROI. Repeat for all nine positions and save. Restart and capture a fresh baseline when prompted. The grid caption changes to **Physical top view**.
4. Press and release each taxel individually. Check the **CONTACT DETECTED** label, the displayed R label and its physical grid cell. Check that the highlight clears on release. In V-change modes the grid labels the optical ROI and the footer shows the raw classifier results. Recheck lighting, registration and baseline if the unloaded state or position is wrong.
5. For a saved run, select **Record session** before Start. Enter full screen. Keep the bundled press and unloaded replays available for rehearsal.

## Windows installation and launch

This workspace has a dedicated **.venv-demo** environment. The launcher prefers it. Offline inference uses local files throughout.

On another **64-bit Windows** laptop, install **64-bit CPython 3.12** and extract the entire **BAURods_Live_Demo_Windows_x64.zip** to a local folder. From the extracted project root, run these PowerShell commands. The included wheelhouse supports installation without a network connection.

```powershell
Set-Location .\calibration_gui
py -3.12 -m venv .venv-demo
.\.venv-demo\Scripts\python.exe -m pip install --no-index --find-links ..\wheelhouse -r requirements-demo.txt
.\.venv-demo\Scripts\python.exe -m pip check
.\.venv-demo\Scripts\python.exe -m baurods_demo
```

For a fresh source checkout with internet access, use the same commands and omit `--no-index --find-links ..\wheelhouse`. The demo requirements use the project’s analysis version constraints. XGBoost is an import dependency of the original tuning helpers. PyArrow supports the independent verification command.

From **calibration_gui**, either rehearsal command starts playback directly.

```powershell
.\.venv-demo\Scripts\python.exe -m baurods_demo --replay --fullscreen
.\.venv-demo\Scripts\python.exe -m baurods_demo --replay .\assets\baurods_demo_replay\unloaded\session_video.mp4
```

## Fitted models and timing

The October characterization report selects the RBF SVC and logistic-regression **families** from the six held-out TEST-group comparisons. The September tuning run identifies the final configuration for each family using all 15 development-group pair splits. Its default localization export is an ensemble. The demo reads **Tuned Logistic regression** from the final family selections and loads its matching fitted member. Both deployed files already existed. Integration required no model or scaler fit. The original splits, result tables and model artifacts remain the reference evidence. [Characterization report, section 9](../outputs/global_characterization/Global_Sensor_Characterization_Report.md) · [Family comparison](analysis_outputs/live_sensor_manual_only/model_runs/tuning_20260909/model_comparison.csv) · [Final selections](analysis_outputs/live_sensor_manual_only/model_runs/tuning_20260909/final_selections.json)

| Task | Fitted artifact in the tuning run’s models folder | Pipeline |
| --- | --- | --- |
| Contact | contact_con_022.joblib | Saved StandardScaler, 90-column shape pack, RBF SVC with C = 1 and gamma = 1/90, classes 0 and 1. Balanced threshold 0.32685983180999756. |
| Localization | localization_loc_036.joblib | Saved StandardScaler, 117-column invariant pack, multinomial logistic regression with C = 0.03. The fitted class order is 1 through 9. |

The loader checks the final selection, manifest, task specifications, member digests, classifier and scaler widths, and actual class order before publishing predictions. The full artifact paths and SHA-256 values appear in **Advanced → Acquisition & model details** and the session manifest. [Fitted bundle manifest](analysis_outputs/live_sensor_manual_only/model_runs/tuning_20260909/models/manifest.json)

**Image path.** Raw BGR frames are rotated 90° clockwise and then mirrored horizontally to 480 × 640. Portrait acquisition videos have already received that transform. The project applies its nine fixed rectangles in ROI 1–9 order with no resize or additional crop. It converts BGR to OpenCV HSV and subtracts the unloaded per-pixel median V using signed integer arithmetic. The same extraction code supplies signed statistics, positive clipped sums, fractions above the active threshold (ΔV ≥ 10), centroids and raw V statistics. The fitted per-ROI noise floors, area normalization, spatial contrasts and missing-centroid treatment come from the tuned pipeline. Camera overlays are drawn separately. [Frozen geometry](assets/live_sensor/roi_layout.json) · [Optical extractor](processing/feature_extraction.py) · [Feature packs](scripts/tune_manual_models.py)

**Decision path.** Each classifier uses the current optical feature pack plus its original causal output averaging with a 1.0 s time constant. The SVC decision score is the training pipeline’s sigmoid of its margin, followed by that average and the saved float32 precision step. The threshold applies to this uncalibrated score. Logistic class probabilities receive the same causal averaging before taking the winning class. **Trained models** shows the winning logistic class during positive SVC contact. Smoothing can delay both onset and release.

The streaming predictor uses capture-time intervals and resets on session boundaries or gaps above 300 ms. It also resets when the demo replaces a baseline. The 300 ms force-alignment field in the tuning metadata was used to form training targets. Live inference needs only optical frames, their order and their times. It requires no future frames, completed press, manual event marks, reference force or labels. [Stateful predictor](scripts/predict_tuned_manual.py)

## Local V change during a press

The optional optical rules provide a separate experimental display. The SVC must still report contact. The displayed ROI comes from the camera’s **mean HSV V** measurements. The footer and CSV retain the raw logistic label even when the two locations disagree. **NO CONFIRMED CONTACT** clears the grid when the SVC is positive and the optical rule sees no press.

**SVC + rapid V tap** adds a time-based check to the rod response rule below. It compares the current mean V of each rod with its median 0.20–0.60 seconds earlier and divides by the elapsed capture time. An isolated bright pulse can trigger immediately. A rod too faint for the ordinary darkening rule can also trigger if its V falls rapidly relative to its neighbors, falls by at least 0.45 digital levels in Automatic, and stays nearly dark for 0.20 seconds. Competing dark tips and shared lighting changes can leave the grid clear. Recovery clears the tile. The footer and the recording column **optical_v_per_s** give the highlighted rod’s current signed rate in mean HSV V levels per second. This rate can approach zero while a rod is held. [Tap rate implementation](baurods_demo/tap_rate.py)

**SVC + rod response** supports flashes, slower local increases and near-complete extinction in one setup. A quiet rod can trigger on an isolated fast rise or a sustained increase above its unloaded level. An increase shared across the array is rejected. On this mount, a hand can also shade several neighbors before the pressed rod goes out. The rule looks for a previously lit ROI retaining at most 6% of its unloaded brightness, accounts for scene dimming and requires a consistent location for 200 ms. A dark region must recover before it can start another press. Bright events are disarmed during a shadow to avoid reporting the release flash as a new contact. A fresh unloaded capture saves the median ROI levels and a noise floor based on median absolute deviation. The grid can stay active during a measured hold and clears on optical recovery, loss of SVC confirmation, stale input or Stop. [Rod response implementation](baurods_demo/rod_response.py)

The two single-direction modes remain available for reproducing earlier sessions. They compare mean HSV V to the preceding 450 ms. The optical strip shows all nine measured V means.

- **Rise** detects a localized bright flash. The actual rise and its component above the array-wide change must exceed the threshold. The ROI must also rise relative to the unloaded spatial pattern. A winning edge at least 1.35 times the runner-up can be confirmed on a single frame.
- **Drop** handles the strong darkening observed when pressing this mount. A new local fall of at least half the configured threshold opens a 650 ms observation window for that ROI. To be reported, the ROI must lose at least the full threshold, retain at most 15% of its unloaded brightness after accounting for scene-wide dimming, and stay the leading eligible ROI for 140 ms. Its local loss must exceed the next eligible ROI’s loss by 25%. This lets a brief shadow pass over a neighbor before the grid commits to a position. When 40% of the expected brightness returns, the highlight clears. A weak or ambiguous drop leaves the grid blank.

**Advanced → Minimum optical step** sets the floor in digital levels averaged over a whole ROI. Automatic uses 0.6 for brightening and 2.0 for darkening. For the single-direction modes, a fresh calibration also measures twice the observed 95th percentile of absolute local changes. Their indication clears on recovery below the larger of 40% of threshold and 30% of peak change, on loss of SVC contact, or after four seconds. Gaps, stale input, a new baseline and Stop clear active output. [Single-direction detector](baurods_demo/optical_change.py)

Clean installations start with the thesis models. A live selection is saved per setup. Opening a demo recording restores its display rule, sensitivity and baseline noise profile. Older recordings and the bundled study clips open in the original mode. Select **SVC + local V rise** before starting a study clip to compare its optical display.

## Inputs, orientation and recording

- **Live camera.** The project’s camera service tries DirectShow then Media Foundation and reads the driver-selected stream. The study camera reported manual exposure −2 and gain 0 in the bundled recordings. Advanced can request manual exposure and gain on the next Start and checks the driver’s readback. Align the physical mount to the frozen rectangles. Until a mapping is verified for the selected device and layout, the grid explicitly shows **trained ROI order**. The nine-position check changes only the physical display order. Recheck it after moving the camera, changing USB devices or moving the sensor.
- **Recorded video replay.** Use the original unannotated **session_video.mp4** with its baseline summary, arrays and capture timestamps. The two supplied examples include the optical clock columns separately. An original acquisition folder can instead supply **master_synchronized.csv**. The replay reader takes only the frame ID, time and wall-clock timestamp from that file. For an unaccompanied video the GUI labels timing as estimated from nominal FPS. Capture an unloaded baseline during a known unloaded interval before interpreting that video.
- **Session files.** Opt-in recording creates a new directory under **output/baurods_demo/sessions**. It contains unannotated, lossless FFV1 **session_video.avi**, **timestamps.csv**, **predictions.csv**, **roi_layout.json**, **session.json**, and a folder for each baseline used. Open that AVI in replay to use the original capture times, baseline changes and history boundaries. The AVI container’s placeholder FPS is superseded by its sidecar clock.
- **CSV.** Each frame has ID, source time, available capture UTC, log UTC, status, validity, raw contact, contact decision score, raw taxel, nine localization scores, displayed contact, displayed taxel and grid position, processing time, freshness and measured rates. V-change rows also record the display mode, optical ROI, local change magnitude in the selected direction, threshold and optical state. A positive raw SVC decision can appear alongside a zero displayed contact. Invalid rows have empty predictions. Terminal and stale transitions have separate event rows.
- **Setup.** Defaults are in **config/baurods_demo.json**. **output/baurods_demo/setup.json** stores the selected index, camera overrides, artifact/layout paths and verified orientation. **last_acquisition.json** stores the actual driver settings, active model identities and complete ROI geometry. New baseline metadata and arrays are saved under **calibrations**. Each live connection starts with a fresh unloaded calibration.
- **Freshness.** Acquisition and inference have separate workers. Qt polls the latest display every 50 ms. Live acquisition preserves frame order with a six-frame maximum queue and reports overload if the worker falls behind. Replay applies backpressure while retaining the original source times. A 500 ms freshness timeout suppresses active output. Stop, disconnect, baseline replacement, processing failure and replay completion also clear the grid.

## Verification

The video comparison decoded each original MP4, used its archived per-pixel baseline and capture times, and compared against independently stored per-session Parquet rows. The batch reference uses the frozen tuning source snapshot, the selected fitted scalers and estimators, and its original causal averaging and precision. The reference read uses only optical columns, frame identity and time.

| Original recording | Frames | Optical columns compared | Maximum absolute difference in optical inputs, model packs and scores | Matching raw labels |
| --- | ---: | ---: | ---: | --- |
| R5 TEST7 center press, replay-only | 160 | 153 | 0 | 160/160 for each model |
| R5 NOCONTACT unloaded control | 130 | 153 | 0 | 130/130 for each model |

In original model mode, the center clip produced 79 gated detections. R5 appeared on 57 frames and R9 on 22. In local V rise mode, 15 frames highlighted R5 and none highlighted R9. Both modes cleared the unloaded clip throughout. Across the nine TEST7 recording feature streams, the rise rule showed at least one frame of the designated taxel in every clip. Its highlights were sparse, ranging from one to 15 frames per clip. It showed zero detections in 1,352 archived NOCONTACT frames. These are playback observations. The thesis accuracy and F1 scores apply to the original evaluation procedure.

The acceptance tests exercise all nine positions, mapping, calibration reset, invalid input, stale and disconnected sources, GUI responsiveness, full screen, and recording/replay. Additional checks cover static glare, common lighting changes, ambiguous ROIs, both signal directions, release, timeout, and the distinction between raw and displayed predictions.

```powershell
.\.venv-demo\Scripts\python.exe -m unittest discover -s tests -p test_baurods_demo.py -v
.\.venv-demo\Scripts\python.exe -m scripts.verify_baurods_demo
.\.venv-demo\Scripts\python.exe -m scripts.verify_baurods_optical
```

The transfer kit includes the two independent verification Parquets. In the full project, verification uses the manual-only feature store or its thesis-appendix mirror. An alternate original Parquet directory can be supplied with `--feature-store`. The two clips can be re-extracted from the known manual archive with `python -m scripts.prepare_baurods_replay --archive "PATH\Manual Calibration (2).zip"`.

**IMX179 check, 2 November 2026.** The camera streamed 640 × 480 frames at about 15 Hz on DirectShow index 1. On 141 explicitly unloaded frames the raw SVC was positive and the raw logistic label was R8 throughout, using either the operator’s prior baseline or a fresh baseline. The local-drop rule cleared all 141 frames. In a second operator-confirmed trace with three R5 press/release cues, the raw models reported contact at R9 throughout 278 post-calibration frames. The local-drop rule produced three R5 events and cleared on each release. The rule was developed using these traces. This is an optical check on this mount, where shadows and changes in lighting can affect the signal. Repeat the nine-position physical check after moving the mount. Numeric traces are saved under **output/baurods_demo/diagnostics** on this laptop. Pass a captured **fresh.csv** or **trial.csv** from the cued center test to `scripts.verify_baurods_optical --trace` to reproduce its comparison.

**Corner check.** In the native GUI, the first optical rule briefly selected neighboring R9 during an R8 press and missed the R9 press. The trace showed that the pressed ROI settled close to black after the approach shadow moved. Replaying those same 215 measured frames with the revised sustained-drop rule gave one R8 event and one R9 event, each clearing in the corresponding release period. The corner result is a retrospective check on the two operator-confirmed cues. A fresh nine-taxel run is still needed to establish how consistently the rule transfers across positions and lighting. All 11 software acceptance tests passed.

The exact numeric checks from this workspace can be reproduced from **calibration_gui** with the following command. The corner trace uses the corresponding saved baseline summary under **calibrations**.

```powershell
.\.venv-demo\Scripts\python.exe -m scripts.verify_baurods_optical --trace output/baurods_demo/diagnostics/idle_20261102T131324Z/fresh.csv --trace output/baurods_demo/diagnostics/center_20261102T131742Z/trial.csv --trace output/baurods_demo/diagnostics/corners_20261102T133236Z/trial.csv
```

**Bottom-row light check, 2–3 November 2026.** The operator completed two R7, R8, R9 rounds on DirectShow index 1. The original rise-only display missed the first R7 and R8 presses and showed R8 during the first R9 cue. The camera showed that the contacted rod lost almost all its light under load. Its light returned during release. The SVC was positive throughout the valid portion of this recording. A calibration transient also raised the original R9 rise threshold to 7.93 mean V levels.

The first round informed the combined rule. On lossless replay it highlighted R7, R8 and R9 in order in both rounds, cleared in each of the six release periods, and reproduced the recorded raw classifier outputs for all 461 valid frames. The second round was kept separate during development. The previous 141-frame unloaded hardware trace produced no displayed contact. These are checks on these recordings. A fresh live run is available through the light-check launcher. [Numerical results on this laptop](output/baurods_demo/diagnostics/bright_row_20261102T155338Z/verification.json)

For actual brightening, the R7, R8 and R9 TEST7 study clips highlighted their designated rods for 69, 74 and 75 frames respectively with **SVC + rod response**. The previous rise-only rule showed 7, 11 and 9 frames. All 1,352 archived unloaded frames remained clear. These counts describe the duration of displayed optical responses. The updated application passed 15 software acceptance checks. [Archived replay counts](output/baurods_demo/diagnostics/bright_row_20261102T155338Z/archive_evidence.json)

```powershell
.\.venv-demo\Scripts\python.exe -m scripts.verify_baurods_optical --mode rod_response --guided-check output/baurods_demo/diagnostics/bright_row_20261102T155338Z
```

**Rapid V check, 3 November 2026.** In the later confirmed bottom-row run, the unloaded R7, R8 and R9 means were about 1.4, 1.3 and 0.5 V levels. The previous display missed all six presses. Selecting the single fastest-changing rod over each press cue, after subtracting the array’s median signed frame-to-frame rate, matched two of the six. The largest change during release often exceeded the press signal.

On replay of that dim run, **SVC + rapid V tap** selected R7, R8 and R9 in the first round and R8 and R9 in the second. It stayed blank during the second R7 press as multiple tips dimmed. All five indications cleared during their corresponding release cues. It also reproduced all six presses in the earlier bottom-row recording, the three cued R5 presses and the separate R8/R9 pair. The 141-frame unloaded camera trace and 1,352 archived unloaded frames stayed clear. These are retrospective checks on recorded frames and operator cue windows. [Per-cue results and model parity](output/baurods_demo/diagnostics/bright_row_20261102T162813Z_01233c/rapid_tap_verification.json) · [Archived clips](output/baurods_demo/diagnostics/bright_row_20261102T162813Z_01233c/rapid_tap_archive.json)

```powershell
.\.venv-demo\Scripts\python.exe -m scripts.verify_baurods_optical --mode rapid_tap --guided-check output/baurods_demo/diagnostics/bright_row_20261102T155338Z --guided-check output/baurods_demo/diagnostics/bright_row_20261102T162813Z_01233c
```
