import dataclasses
from decimal import Decimal
from fractions import Fraction
from typing import Optional


@dataclasses.dataclass
class ExpectedMetadata:
    width: Optional[int] = None
    height: Optional[int] = None
    aperture_size: Optional[Decimal] = None
    exposure_time: Optional[Fraction] = None
    focal_length: Optional[float] = None
    iso_value: Optional[int] = None
    camera_make: str = ""
    camera_model: str = ""
