import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description="BAURods Live Demo · camera contact and localization")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--replay", nargs="?", const="sample", metavar="VIDEO",
                        help="start the bundled center press, or play a specific quantitative video")
    inputs.add_argument("--light-check", action="store_true", help="open the guided live R7 / R8 / R9 check")
    inputs.add_argument("--multi-check", action="store_true", help="open a guided R7 + R9 multi-press check")
    inputs.add_argument("--sliding-check", action="store_true", help="open a guided R1 + R3 lateral-motion check")
    parser.add_argument("--check-rois", nargs=2, type=int, choices=range(1, 10), metavar=("FIRST", "SECOND"),
                        help="choose the two rods for a multi-press or sliding check")
    parser.add_argument("--check-mode", choices=["multi_press", "multi_v_rise", "multi_spot", "multi_slide"], default="multi_v_rise")
    parser.add_argument("--fullscreen", action="store_true", help="start in presentation mode (Esc to exit)")
    args = parser.parse_args()
    if args.check_rois and (len(set(args.check_rois)) != 2 or not (args.multi_check or args.sliding_check)):
        parser.error("--check-rois requires a multi/sliding check and two distinct rods")
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from .setup import SAMPLE
        from .window import Window
    except (ImportError, OSError) as exc:
        print(f"BAURods runtime could not load: {exc}\nInstall requirements-demo.txt in a local Python 3.12 x64 environment.",
              file=sys.stderr)
        return 1
    app = QApplication([sys.argv[0]])
    app.setApplicationName("BAURods Live Demo")
    replay = SAMPLE / "center_press/session_video.mp4" if args.replay == "sample" else args.replay
    if args.light_check or args.multi_check or args.sliding_check:
        from .light_check import LightCheckWindow
        window = LightCheckWindow(multi=args.multi_check, sliding=args.sliding_check,
                                  rois=args.check_rois, check_mode=args.check_mode)
    else:
        window = Window(replay=Path(replay).resolve() if replay else None)
    window.show()
    if args.fullscreen:
        window.fullscreen()
    if replay:
        QTimer.singleShot(0, window.start)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
