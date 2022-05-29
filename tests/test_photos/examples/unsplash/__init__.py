from decimal import Decimal
from fractions import Fraction

from ..schema import ExpectedMetadata

# Photos are licensed according to the Unsplash license:
# https://unsplash.com/license

index = {
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
}
