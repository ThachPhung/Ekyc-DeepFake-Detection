from typing import Literal, Optional

from pydantic import BaseModel

VerdictType = Literal["real", "fake", "uncertain"]


class LipSyncResponse(BaseModel):
    verdict: VerdictType
    is_real: bool
    is_fake: bool
    confidence: float
    manipulation_probability: float
    av_offset_frames: Optional[int] = None
    min_distance: Optional[float] = None
    sync_confidence: Optional[float] = None
    face_detected: Optional[bool] = None
    detail: Optional[str] = None
    engine: str = "syncnet_hf"
