import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description="BAURods Live Demo · camera-only single-taxel inference")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--replay", nargs="?", const="sample", metavar="VIDEO",
                        help="start the bundled center press, or play a specific quantitative video")
    inputs.add_argument("--light-check", action="store_true", help="open the guided live R7 / R8 / R9 check")
    parser.add_argument("--fullscreen", action="store_true", help="start in presentation mode (Esc to exit)")
    args = parser.parse_args()
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
    if args.light_check:
        from .light_check import LightCheckWindow
        window = LightCheckWindow()
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
