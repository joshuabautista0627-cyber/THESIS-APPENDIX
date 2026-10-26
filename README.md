# SPARE thesis appendix

Source and supporting evidence snapshot prepared on **19 October 2026**, published to this repository on **26 October 2026**.

## Complete electronic appendix

The original ZIP contains 8,847 payload files and is 35,111,754,320 bytes (35.1 GB). Download **all numbered ZIP parts** and `reassemble_appendix.py` from the [appendix release](https://github.com/joshuabautista0627-cyber/THESIS-APPENDIX/releases/tag/appendix-2026-10-19). Put them in the same folder, then run:

```powershell
python reassemble_appendix.py
```

The script verifies each part, joins the original ZIP, and verifies its SHA-256. Parts are raw consecutive segments and cannot be extracted individually. Allow approximately 71 GB of free space for the downloaded parts plus the reconstructed ZIP, and additional space if extracting it. GitHub's automatic **Source code (zip)** download contains the repository tree only; it is not the complete electronic appendix.

## Browse the implementation

- [SPARE application and setup instructions](SOFTWARE_CALIBRATION/calibration_gui/README.md)
- [Force and localization model artifacts](SOFTWARE_CALIBRATION/calibration_gui/models/)
- [Application processing code](SOFTWARE_CALIBRATION/calibration_gui/processing/)
- [Arduino firmware](SOFTWARE_CALIBRATION/calibration_gui/arduino/)
- [Processed dataset documentation](SOFTWARE_CALIBRATION/DATASETS.md)
- [Analysis and evidence reports](SOFTWARE_CALIBRATION/reports/)
- [BAURods quality analysis](SOFTWARE_CALIBRATION/baurods_quality/README.md)
- [Full archive file manifest](FILE_MANIFEST.csv)

The repository contains the project files from the original appendix. Raw data archives and bundled Arduino development tools are provided in the complete release package; their paths are listed in `RELEASE_ONLY_FILES.json`. Dependencies are described in the project's requirements and lock files.

## Provenance and limitations

The snapshot includes accessible working files and **577 files recovered from Git commit `5f1c73c15b1aa9f53acaa5551e360d3b30aefbf1`** because their workspace folders were inaccessible. Their equality to the inaccessible current files was not verified. Three inaccessible temporary directories were omitted. See [packaging notes](PACKAGING_NOTES.json) and [appendix README](README_THESIS_APPENDIX.md) for exact details. No experiments, hardware checks, or model training were rerun during packaging or publication.

The original archive passed entry CRC and payload SHA-256 checks when created. Its SHA-256 is:

```text
7707f15a4c60ef4e9901362870437db25670edcab8d04b79ee4a52f86221bbe2
```

For the thesis, cite the release URL and archive checksum as electronic supplementary material. Existing source and third-party licensing notices are retained, including [LICENSE.txt](SOFTWARE_CALIBRATION/LICENSE.txt).
