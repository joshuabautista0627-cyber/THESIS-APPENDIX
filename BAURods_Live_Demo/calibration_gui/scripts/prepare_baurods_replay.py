"""Extract the two rehearsal clips and only their optical acquisition metadata."""
import argparse
import csv
import io
import json
from pathlib import Path
import shutil
import zipfile

from scripts.live_sensor_common import PROJECT_ROOT, atomic_write_json, sha256_file

CLIPS = {"center_press": "2026-08-08_170958_044598_1_R5_TEST7",
         "unloaded": "2026-08-08_170226_232257_1_R5_NOCONTACT"}


def main():
    config = json.loads((PROJECT_ROOT / "config/live_sensor_manual_only.json").read_text())["sources"]["manual"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path(config["archive_path"]))
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "assets/baurods_demo_replay")
    args = parser.parse_args()
    if sha256_file(args.archive) != config["expected_sha256"]:
        raise ValueError("Manual source archive checksum mismatch")
    with zipfile.ZipFile(args.archive) as z:
        for name, session in CLIPS.items():
            folder = args.output / name
            folder.mkdir(parents=True, exist_ok=True)
            root, = [m[: -len("session_video.mp4")] for m in z.namelist() if m.endswith(f"/{session}/session_video.mp4")]
            for member in ["session_video.mp4", "baseline_summary.json", "baseline_data.npz", "roi_layout.json"]:
                with z.open(root + member) as src, (folder / member).open("wb") as dest:
                    shutil.copyfileobj(src, dest)
            camera = json.loads(z.read(root + "camera_settings.json"))
            atomic_write_json(folder / "camera_settings.json", {k: camera[k] for k in
                              ("camera_model", "camera_orientation", "actual", "controls")})
            with z.open(root + "master_synchronized.csv") as stream, (folder / "timestamps.csv").open(
                    "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["frame_id", "source_time_s", "wall_clock_iso"])
                for row in csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig")):
                    writer.writerow([row["capture_frame_id"], row["elapsed_time_s"], row["wall_clock_iso"]])
            atomic_write_json(folder / "source.json", dict(archive=args.archive.name, archive_sha256=config["expected_sha256"],
                              member=root + "session_video.mp4", session_id=session,
                              video_sha256=sha256_file(folder / "session_video.mp4")))
            print(name, session, folder)


if __name__ == "__main__":
    main()
