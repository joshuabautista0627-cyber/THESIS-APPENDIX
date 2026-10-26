# SPARE thesis appendix archive

Prepared 19 October 2026 (Asia/Manila). This is a source and evidence snapshot, not a new validation of scientific results or hardware operation.

## Contents
- SOFTWARE_CALIBRATION: SPARE GUI source, force/localization models, Arduino firmware, configurations, tests, dependency lists, accessible recordings, processed datasets, analysis scripts, reports, figures, notebooks, and existing handoff packages.
- Original_Data_Archives: original ZIP archives and companion files from the Data Collection directory. Existing extracted data subdirectories are not duplicated; raw data is supplied in its original archives. Historical archive versions are included.
- FILE_MANIFEST.csv: path, byte count, SHA-256, and source of each payload file.
- PACKAGING_NOTES.json: exact exclusions, inaccessible folders, and recovered file paths.

## Snapshot provenance and limitations
577 files under 30 inaccessible workspace directories were recovered from Git commit 5f1c73c15b1aa9f53acaa5551e360d3b30aefbf1. They occupy their normal project paths so model and dataset references remain usable. Their manifest source explicitly identifies Git. These are committed historical copies; their equality to the inaccessible current files could not be checked. Accessible working files include uncommitted changes. This is therefore a mixed snapshot, not a clean checkout of a single commit.

Unresolved inaccessible directories: ["calibration_gui/analysis_outputs/live_sensor_study/cache/staging/feature-store-c0ec762f1dc888a7/archive_id=automated/.2026-08-07_104339_334149_1_R9_C6.hh77_hss", "calibration_gui/analysis_outputs/live_sensor_study/feature_store/.feature-store-c0ec762f1dc888a7.4suzcxqr.tmp", "calibration_gui/analysis_outputs/live_sensor_study/feature_store/.feature-store-c0ec762f1dc888a7.g3j6bsrn.tmp"].

Installed virtual environments, dependency caches, temporary working folders, Git metadata/history, and credential filenames are excluded. The supplied dependency requirements support reinstalling packages. Existing report drafts and historical results remain intact and should not automatically be treated as the final thesis conclusions.

## Run the SPARE application
Extract the ZIP to a local folder with sufficient free space. In SOFTWARE_CALIBRATION/calibration_gui, follow README.md and setup_windows.bat. The documented environment is Windows with Python 3.11 or later. Install requirements.txt into a new virtual environment, then launch app.py --simulation for a hardware-free starting point. Hardware operation requires the wiring, calibration, and port configuration in the project README and hardware checklist.

Analysis dependencies are listed in requirements-analysis.txt and the lock files. BAURods analysis has its own README and requirements.txt. Some analysis scripts contain original absolute data paths; point their archive arguments to Original_Data_Archives after extraction. Rebuilding the report web app may require its documented Data plugin runtime.

## Appendix use
Refer to this ZIP as electronic supplementary material and identify the archive filename and its companion SHA-256 checksum in the thesis. FILE_MANIFEST.csv supports checking individual payloads. The archive documents the supplied implementation and evidence; it does not independently prove scientific accuracy or authorship. Packaging did not rerun experiments, train models, or operate hardware.
