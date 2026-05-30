from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MetalAvailability:
    available: bool
    reason: str


def detect_metal_availability() -> MetalAvailability:
    try:
        import Metal  # type: ignore
        import MetalKit  # type: ignore  # noqa: F401
    except Exception as error:
        return MetalAvailability(False, f"PyObjC Metal packages missing: {error}")
    try:
        device = Metal.MTLCreateSystemDefaultDevice()
        if device is None:
            return MetalAvailability(False, "MTLCreateSystemDefaultDevice() returned None.")
    except Exception as error:
        return MetalAvailability(False, f"Metal device probe failed: {error}")
    return MetalAvailability(True, "Metal available")

