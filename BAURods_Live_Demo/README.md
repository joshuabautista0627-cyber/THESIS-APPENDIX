# BAURods Live Demo

This Windows GUI shows the underside camera, the mean brightness of nine rod tips and the contact location on a 3 × 3 grid. It includes the trained RBF SVC contact detector, logistic regression localization model, the **SVC + rapid V tap** display rule, session recording and two rehearsal videos.

## Install on Windows

Install 64-bit Python 3.12. Download and extract the complete Windows package, then open PowerShell in the folder containing `run_baurods_demo.bat`. [Download the offline Windows x64 package](https://github.com/joshuabautista0627-cyber/THESIS-APPENDIX/releases/download/baurods-live-gui-2026-11-03/BAURods_Live_Demo_Windows_x64.zip)

```powershell
py -3.12 -m venv .\calibration_gui\.venv-demo
.\calibration_gui\.venv-demo\Scripts\python.exe -m pip install --no-index --find-links .\wheelhouse -r .\calibration_gui\requirements-demo.txt
.\calibration_gui\.venv-demo\Scripts\python.exe -m pip check
.\run_baurods_demo.bat
```

For a Git checkout with internet access, open PowerShell in `BAURods_Live_Demo` and use the same commands with `--no-index --find-links .\wheelhouse` removed.

## Run the demo

- **Live camera.** Choose **LIVE CAMERA**, select the Arducam camera index (1 on the demonstration laptop) and choose **SVC + rapid V tap** beside Contact Status. Click **Start**, leave all rods unloaded and click **Capture unloaded baseline**. The green tile shows the optically confirmed rod while the SVC reports contact. The footer shows the raw classifier outputs.
- **Replay.** Run `.\run_baurods_demo.bat --replay` to rehearse the center press without a camera. The GUI also includes a separate unloaded recording.
- **Guided R7 / R8 / R9 check.** Run `.\run_baurods_light_check.bat` for two cued rounds. The finish buttons save the check and return to the normal GUI.

The guide covers ROI mapping, calibration, recording, the fitted models and the results of the tap tests. The latest dim recording produced five correct indications in six bottom-row presses. The second R7 press remained unconfirmed. [Operator guide and verification](calibration_gui/BAURods_Live_Demo.md)

## Verify the installation

From this folder, run the GUI acceptance tests and compare the optical features and classifier scores against the supplied reference data.

```powershell
Set-Location .\calibration_gui
.\.venv-demo\Scripts\python.exe -m unittest discover -s tests -p test_baurods_demo.py -v
.\.venv-demo\Scripts\python.exe -m scripts.verify_baurods_demo
```
