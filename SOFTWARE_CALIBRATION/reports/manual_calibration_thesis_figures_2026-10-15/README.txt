MANUAL CALIBRATION CONFUSION MATRICES AND HEATMAPS
Created 15 October 2026 from the saved 9 September 2026 tuning experiment.

Use figures 01, 03 and 04 as the primary thesis figures. Figure 02 supplies raw localization counts; figure 05 exposes group variation. Each figure is supplied as a 300 dpi PNG and editable vector SVG. SVG files preserve text as text.

Primary procedure: Tuned selected. These are held-out outer-fold predictions from a nested selection procedure, not predictions of the final full-data fit on its own training data. Models and thresholds may differ across outer folds. The saved final fitted model has no separate untouched prospective test set.

The manual archive alone supplied these experiments. Localization: 7,154 eligible press frames from 54 recordings and nine ROIs. Contact: those positives plus 1,352 frames from 11 dedicated no-contact recordings. Press eligibility is aligned force 0.05–3 N, an exploratory interval. Replay-only recordings are excluded.

Matrix rows are actual labels; columns are predicted labels. Normalized figures give each recording equal total weight before row normalization. Raw-count figures count every frame equally. Consequently, percentages calculated from raw counts can differ from the published recording-balanced metrics; do not mix them.

Primary recording-balanced localization accuracy: 84.40437042%
Primary recording-balanced localization macro F1: 84.75379323%
Primary contact balanced accuracy: 98.50182108%
Primary contact raw counts [TN, FP; FN, TP]: [[1352, 0], [308, 6846]]

The spatial map uses the actual nine rectangular ROIs in pixel coordinates, with image y increasing downward. Colors are classification recall, not sensor intensity, force or a continuous localization estimate. Its contact panel includes positive press frames only. No-contact specificity is shown in the binary confusion matrix, not inferred for individual ROI rectangles.

Figures 06 and 07 are supplementary retrospective family comparisons: Tuned ensemble localization and Tuned RBF SVC contact. These correspond to the families selected for the final saved models but use separately trained fold models. They should not replace the primary nested-selector metrics without explaining the different comparison.

No training or data filtering was changed for this export. The zero false-positive count is limited to the 11 archived no-contact recordings. The recordings were used in prior development; these are retrospective results, not prospective validation. Force regression has continuous outputs and is not represented with a classification confusion matrix.

Source: calibration_gui/analysis_outputs/live_sensor_manual_only/model_runs/tuning_20260909/outer_predictions.parquet
Model labels and metrics were cross-checked against model_comparison.csv. Matrix cells were independently reconstructed by recording and every row-normalized matrix sums to 100%. Counts and plotting inputs are supplied in data/. Figure_Captions.txt contains thesis-ready captions. Run build_figures.py with calibration_gui/.venv/Scripts/python.exe to reproduce.
