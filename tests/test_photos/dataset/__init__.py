import dataclasses
from collections.abc import Sequence
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

    # This list contains other filenames that should be matched to this photo. Normally,
    # this will contain the corresponding RAW file (if present).
    matched_files: Sequence[str] = dataclasses.field(default_factory=list)


index = {
    #
    # Photos from Unsplash by various contributors, used according to the Unsplash
    # license: https://unsplash.com/license
    #
    # https://images.unsplash.com/photo-1414521203994-7efc0bc37d65unsp
    "-Y-XzY0HhEM.jpg": ExpectedMetadata(
        width=4608,
        height=3456,
        aperture_size=Decimal("3.1"),
        exposure_time=Fraction(1, 60),
        focal_length=4.5,
        iso_value=100,
        camera_make="Panasonic",
        camera_model="DMC-SZ1",
    ),
    # https://images.unsplash.com/photo-1436891620584-47fd0e565afb
    "2KXEb_8G5vo.jpg": ExpectedMetadata(
        width=3695,
        height=5543,
        aperture_size=Decimal("2.8"),
        exposure_time=Fraction(30),
        focal_length=16.0,
        iso_value=3200,
        camera_make="Canon",
        camera_model="EOS 5D Mark III",  # In file: "Canon EOS 5D Mark III"
    ),
    # https://images.unsplash.com/photo-1428406153609-3b81feb03c49
    "8CDzJFF10d0.jpg": ExpectedMetadata(
        width=4288,
        height=2848,
        aperture_size=Decimal("6.3"),
        exposure_time=Fraction(1, 640),
        focal_length=105.0,
        iso_value=200,
        camera_make="NIKON CORPORATION",
        camera_model="D90",  # In file: "NIKON D90"
    ),
    # https://images.unsplash.com/photo-1433621611134-008713dc0321
    "GfuxOPaitSs.jpg": ExpectedMetadata(
        width=4000,
        height=3000,
        aperture_size=Decimal("4.5"),
        exposure_time=Fraction(15),
        focal_length=13.0,
        iso_value=80,
        camera_make="Canon",
        camera_model="PowerShot SX50 HS",  # In file: "Canon PowerShot SX50 HS"
    ),
    # https://images.unsplash.com/uploads/14110413011098a987a96/025f1dd8
    "HZg0vJHFyg0.jpg": ExpectedMetadata(
        width=4928,
        height=3264,
    ),
    # https://images.unsplash.com/photo-1431519210130-9b45f03cb9fe
    "j2HQKlLFT_c.jpg": ExpectedMetadata(
        width=3264,
        height=2448,
        aperture_size=Decimal("2.2"),
        exposure_time=Fraction(1, 3300),
        focal_length=4.2,
        iso_value=32,
        camera_make="Apple",
        camera_model="iPhone 6",
    ),
    # https://images.unsplash.com/photo-1417577097439-425fb7dec05e
    "mwhklqGVzck.jpg": ExpectedMetadata(
        width=4000,
        height=2250,
        aperture_size=Decimal("7.1"),
        exposure_time=Fraction(1, 400),
        focal_length=6.1,
        iso_value=100,
        camera_make="FUJIFILM",
        camera_model="X-S1",
    ),
    # https://images.unsplash.com/photo-1415827007927-b636e96fec40
    "r3ZWnitp3zk.jpg": ExpectedMetadata(
        width=5104,
        height=3454,
        aperture_size=Decimal("5.6"),
        exposure_time=Fraction(1, 100),
        focal_length=55.0,
        iso_value=100,
        camera_make="NIKON CORPORATION",
        camera_model="D3200",  # In file: "NIKON D3200"
    ),
    # https://images.unsplash.com/photo-1441934639004-c5c9fa005c29
    "x6RO8lNSzpo.jpg": ExpectedMetadata(
        width=5472,
        height=3648,
        aperture_size=Decimal("7.1"),
        exposure_time=Fraction(1, 8000),
        focal_length=135.0,
        iso_value=100,
        camera_make="Canon",
        camera_model="EOS 70D",  # In file: "Canon EOS 70D"
    ),
    #
    # Photos by Maximilian Gutwein (@ignitedPotato).
    # Used with permission, all rights reserved.
    #
    "IMG_3452.jpg": ExpectedMetadata(
        width=6016,
        height=4010,
        aperture_size=Decimal("0.0"),
        exposure_time=Fraction(8, 5),
        focal_length=0.0,
        iso_value=200,
        camera_make="Canon",
        camera_model="EOS 77D",  # In file: "Canon EOS 77D"
        matched_files=["IMG_3452.CR2"],
    ),
    "IMG_4766.jpg": ExpectedMetadata(
        width=4722,
        height=3142,
        aperture_size=Decimal("5.6"),
        exposure_time=Fraction(1, 40),
        focal_length=55.0,
        iso_value=1600,
        camera_make="Canon",
        camera_model="EOS 500D",  # In file: "Canon EOS 500D"
        matched_files=["IMG_4766.CR2"],
    ),
    "IMG_7010.jpg": ExpectedMetadata(
        width=4722,
        height=3142,
        aperture_size=Decimal("6.3"),
        exposure_time=Fraction(1, 640),
        focal_length=17.0,
        iso_value=200,
        camera_make="Canon",
        camera_model="EOS 500D",  # In file: "Canon EOS 500D"
        matched_files=["IMG_7010.CR2"],
    ),
    "RAW_2021_07_24_13_18_09_096.jpg": ExpectedMetadata(
        width=2984,
        height=3984,
        camera_make="HMD Global",
        camera_model="Nokia 7.2",
        matched_files=["RAW_2021_07_24_13_18_09_096.dng"],
    ),
    "RAW_2021_07_24_13_23_32_774.jpg": ExpectedMetadata(
        width=3984,
        height=2984,
        camera_make="HMD Global",
        camera_model="Nokia 7.2",
        matched_files=["RAW_2021_07_24_13_23_32_774.dng"],
    ),
    #
    # Photos by Andreas Haberberger (@ahaberberger).
    # Used with permission, all rights reserved.
    #
    "AFH_0455.jpg": ExpectedMetadata(
        width=5596,
        height=3724,
        aperture_size=Decimal("3.5"),
        exposure_time=Fraction(1, 2500),
        focal_length=18.0,
        iso_value=100,
        camera_make="NIKON CORPORATION",
        camera_model="D500",  # In file: "NIKON D500"
        matched_files=["AFH_0455.nef"],
    ),
    "DSC00372.jpg": ExpectedMetadata(
        width=4024,
        height=6048,
        aperture_size=Decimal("5.0"),
        exposure_time=Fraction(1, 1000),
        focal_length=17.0,
        iso_value=100,
        camera_make="SONY",
        camera_model="ILCE-7M3",
        matched_files=["DSC00372.arw"],
    ),
    "DSCF2542.jpg": ExpectedMetadata(
        width=3296,
        height=4936,
        aperture_size=Decimal("2.8"),
        exposure_time=Fraction(1, 45),
        focal_length=18.0,
        iso_value=1600,
        camera_make="FUJIFILM",
        camera_model="X-E2S",
        matched_files=["DSCF2542.raf"],
    ),
    "IMG_0160.jpg": ExpectedMetadata(
        width=5536,
        height=3688,
        aperture_size=Decimal("11.0"),
        exposure_time=Fraction(1, 1600),
        focal_length=8.8,
        iso_value=250,
        camera_make="Canon",
        camera_model="PowerShot G7 X Mark II",  # In file: "Canon PowerShot G7 X Mark II"
        matched_files=["IMG_0160.cr2"],
    ),
    "P8245372.jpg": ExpectedMetadata(
        width=4608,
        height=3456,
        aperture_size=Decimal("3.5"),
        exposure_time=Fraction(1, 30),
        focal_length=14.0,
        iso_value=200,
        camera_make="OLYMPUS IMAGING CORP.",
        camera_model="E-PL5",
        matched_files=["P8245372.orf"],
    ),
    #
    # Photos by Yannik Rödel (@yrd).
    # All rights reserved.
    #
    "IMG_0009.JPG": ExpectedMetadata(
        width=4752,
        height=3168,
        aperture_size=Decimal("7.1"),
        exposure_time=Fraction(1, 500),
        focal_length=250.0,
        iso_value=400,
        camera_make="Canon",
        camera_model="EOS 500D",  # In file: "Canon EOS 500D"
        matched_files=["IMG_0009.CR2"],
    ),
}
