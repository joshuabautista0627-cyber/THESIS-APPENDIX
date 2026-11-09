# BAURods Live Demo

This Windows GUI shows the underside camera, the brightness of nine rod tips and their detected locations on a 3 × 3 grid. It includes the original fitted SVC contact detector and logistic regression localizer, editable optical ROIs, experimental multi-press and sliding modes, session recording and two rehearsal videos.

## Install on Windows

Install 64-bit Python 3.12. [Download the complete offline Windows x64 package](https://github.com/joshuabautista0627-cyber/THESIS-APPENDIX/releases/download/baurods-live-gui-2026-11-09/BAURods_Live_Demo_Windows_x64.zip), extract it, then open PowerShell in the folder containing `run_baurods_demo.bat`.

```powershell
py -3.12 -m venv .\calibration_gui\.venv-demo
.\calibration_gui\.venv-demo\Scripts\python.exe -m pip install --no-index --find-links .\wheelhouse -r .\calibration_gui\requirements-demo.txt
.\calibration_gui\.venv-demo\Scripts\python.exe -m pip check
.\run_baurods_demo.bat
```

For a Git checkout with internet access, open PowerShell in `BAURods_Live_Demo` and use the same commands with `--no-index --find-links .\wheelhouse` removed. Offline dependency wheels are included in the release download.

## Run and adjust the demo

1. Choose **LIVE CAMERA**, select the Arducam camera index (1 on the demonstration laptop) and click **Start**.
2. Click **Edit ROIs…** to move, resize or redraw the nine rectangles around the rod tips and their lateral travel. Click **Save**, then **Start** again.
3. Choose **SVC + multi V rise (experimental)** for independent brightening, **SVC + multi bright spots (experimental)** for small luminous areas, or **SVC + sliding / held light (experimental)** for lateral motion with sustained light. Mode changes require stopping acquisition first.
4. Release all rods and click **Capture unloaded baseline**. Keep them unloaded until calibration finishes. Recalibrate after adjusting the ROIs, camera or lighting.
5. For physical pressing-side labels, use **Check mapping…** to verify all nine positions. Camera ROI numbers can be reversed relative to the pressing side.

The new optical modes support up to four simultaneous responses while retaining the overall SVC contact gate. Sliding mode holds an indication at constant light above the unloaded baseline. Residual glow can keep an indication active after mechanical release; illumination changes can also produce false responses. These modes remain experimental. The original trained-model and rapid-tap modes are still selectable, and the raw classifiers retain their original ROI geometry.

## Replay and guided live checks

Run these commands from the folder containing the launcher. Each guided check waits for its blue Start button, records an unloaded baseline and provides press/release cues. Confirm which cues you completed at the end to return to the normal GUI. Follow the numbered **camera rectangles** during guided checks.

```powershell
.\run_baurods_demo.bat --replay
.\run_baurods_light_check.bat
.\run_baurods_demo.bat --multi-check --check-rois 7 9 --check-mode multi_v_rise
.\run_baurods_sliding_check.bat --check-rois 1 3
```

## Verification

The 9 November update passed 36 software checks. All original optical features and classifier scores matched the reference data exactly across 290 study frames; 586 frames from the sliding recording also reproduced the raw classifier outputs exactly. Live sliding checks detected both top ROIs, but release errors remained, so these results do not establish general multi-press accuracy. See the [operator guide and detailed evidence](calibration_gui/BAURods_Live_Demo.md) and [current validation summary](calibration_gui/output/baurods_demo/roi_sliding_validation.json).

From this folder:

```powershell
Set-Location .\calibration_gui
.\.venv-demo\Scripts\python.exe -m unittest discover -s tests -p "test_baurods*.py" -v
.\.venv-demo\Scripts\python.exe -m scripts.verify_baurods_demo
```

Local camera settings, calibrations and newly recorded live sessions are saved under `calibration_gui/output/baurods_demo` on the operator's computer.
