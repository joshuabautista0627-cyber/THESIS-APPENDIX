# Complete THESIS DATA download

Snapshot: **27 October 2026 (Asia/Manila)**. The complete download contains every file and directory in the supplied THESIS DATA folder: **8,589 files totaling 69,613,874,782 uncompressed source bytes (69.6 GB)**. No source files were excluded, renamed, or modified during packaging. Original archives and extracted copies are both included.

## Download and reconstruct

Open the [THESIS DATA release](https://github.com/joshuabautista0627-cyber/THESIS-APPENDIX/releases/tag/thesis-data-2026-10-27). Download all numbered `THESIS_DATA_2026-10-27.zip.partNNN` files, `thesis_data_parts.json`, and `reassemble_thesis_data.py` into one new directory. Python 3.8 or later is required to run the recovery script.

With GitHub CLI, the equivalent steps are:

```powershell
gh release download thesis-data-2026-10-27 --repo joshuabautista0627-cyber/THESIS-APPENDIX --dir THESIS-DATA-Download
cd THESIS-DATA-Download
python reassemble_thesis_data.py
```

The script verifies the SHA-256 of every numbered part and the assembled archive. It creates `THESIS_DATA_2026-10-27.zip` only after verification succeeds. The numbered parts are consecutive segments of one ZIP; they cannot be extracted separately. Existing ZIP outputs are never overwritten.

Extract the reconstructed ZIP into a new directory. Its top level contains these four original folders:

- `ANSYS FOR HOLLOW RODS`
- `CHEMICAL CHARACTERIZATION`
- `Data Collection`
- `UTM Characterization`

Allow approximately **210 GB of free disk space** if keeping the downloaded parts, reconstructed ZIP, and extracted files together. The precise ZIP size is recorded in `thesis_data_parts.json`. To write the reconstructed ZIP to another existing directory or drive:

```powershell
python reassemble_thesis_data.py --output-dir D:\ThesisArchive
```

To verify downloaded parts without creating the ZIP:

```powershell
python reassemble_thesis_data.py --verify-only
```

## File inventory and verification

- `THESIS_DATA_MANIFEST.json` lists all original paths, byte sizes, modification timestamps, SHA-256 checksums, and directory paths. Its `git_browsable` field identifies the 7,551 files also available directly in the repository.
- `thesis_data_parts.json` lists the ordered download parts, exact sizes, and SHA-256 values, plus the complete ZIP size and SHA-256.
- `THESIS_DATA_VERIFICATION.json` records the publication checks.

The complete release contains all 1,038 files absent from the browsable subset, including ZIP archives, videos, and six large ANSYS result files. This avoids GitHub's regular-file size limits and does not use Git LFS.

The supplied research content is preserved as received. Packaging does not rerun experiments or alter measurements. The earlier SPARE software appendix and its release remain separate.
