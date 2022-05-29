import pathlib

import pytest

from tumpara.libraries.models import Library
from tumpara.photos.models import Photo


@pytest.mark.django_db
def test_photo_scanning():
    path = pathlib.Path(__file__).parent / "examples" / "unsplash"
    library = Library.objects.create(context="gallery", source=f"file://{path}")
    library.scan()
    assert Photo.objects.count() == 9

    from .examples.unsplash import index

    for filename, expected_metadata in index.items():
        photo = Photo.objects.get(file__path=filename)
        assert photo.width == expected_metadata.width
        assert photo.height == expected_metadata.height
        assert photo.aperture_size == expected_metadata.aperture_size
        assert photo.exposure_time_fraction == expected_metadata.exposure_time
        assert photo.focal_length == pytest.approx(
            expected_metadata.focal_length, rel=1e-1
        )
        assert photo.iso_value == expected_metadata.iso_value
        assert photo.camera_make == expected_metadata.camera_make
        assert photo.camera_model == expected_metadata.camera_model
