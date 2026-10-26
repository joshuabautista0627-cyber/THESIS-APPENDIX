import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.models import CameraConfig
from services.camera_service import OpenCVCameraService


service = OpenCVCameraService()
try:
    service.connect(
        CameraConfig(
            device_index=0,
            backend_preference=("DirectShow",),
            requested_width=640,
            requested_height=480,
            requested_fps=30.0,
            warmup_seconds=0.0,
            baseline_drift_mean_v=5.0,
            property_readback_tolerance=0.05,
        )
    )
    print("CONNECTED", flush=True)
    print(f"DIALOG_RESULT={service.open_native_properties()}", flush=True)
    time.sleep(60.0)
    frames = sum(service.read_frame() is not None for _ in range(20))
    print(f"FRAMES_AFTER_DIALOG={frames}", flush=True)
finally:
    service.disconnect()
