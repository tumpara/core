import os.path
import pathlib
import shutil
from collections.abc import Sequence
from typing import Any

import hypothesis
import pytest

from tumpara.libraries.models import Library
from tumpara.photos.models import Photo
from tumpara.testing import strategies as st

from .dataset import index

dataset_root = pathlib.Path(__file__).parent / "dataset"


def check_expected_metadata(library: Library, filename: str) -> None:
    expected_metadata = index[filename]
    photo = Photo.objects.get(file__path=filename)
    assert photo.width == expected_metadata.width
    assert photo.height == expected_metadata.height
    assert photo.aperture_size == expected_metadata.aperture_size
    assert photo.exposure_time_fraction == expected_metadata.exposure_time
    assert photo.focal_length == pytest.approx(expected_metadata.focal_length, rel=1e-1)
    assert photo.iso_value == expected_metadata.iso_value
    assert photo.camera_make == expected_metadata.camera_make
    assert photo.camera_model == expected_metadata.camera_model
    assert photo.blurhash is not None


def check_matched_files(library: Library, filename: str) -> None:
    expected_metadata = index[filename]
    if not expected_metadata.matched_files:
        return
    photo = Photo.objects.get(file__path=filename)
    # Make sure all the files are matched to the asset.
    assert {
        path
        for (path,) in photo.files.filter(availability__isnull=False).values_list(
            "path"
        )
    } == {filename, *expected_metadata.matched_files}


# This is slow test because the dataset is not yet public.
# TODO Remove the slow mark once the dataset is freely downloadable.
@pytest.mark.slow
@pytest.mark.django_db
def test_photo_scanning(patch_exception_handling: None) -> None:
    library = Library.objects.create(context="gallery", source=f"file://{dataset_root}")
    library.scan()

    assert Photo.objects.count() == len(index)
    for filename in index.keys():
        check_expected_metadata(library, filename)
        check_matched_files(library, filename)


@pytest.mark.slow
@hypothesis.settings(deadline=None)
@hypothesis.given(
    st.temporary_directories(),
    st.sampled_from(
        [
            (main_filename, expected_metadata.matched_files)
            for main_filename, expected_metadata in index.items()
            if expected_metadata.matched_files
        ]
    ),
    st.data(),
)
def test_incremental_photo_scanning(
    django_executor: Any,
    patch_exception_handling: None,
    root_directory: str,
    path_info: tuple[str, Sequence[str]],
    data: st.DataObject,
) -> None:
    """Photo scanning works even when files are found in different orders."""
    main_filename, other_filenames = path_info
    library = Library.objects.create(
        context="gallery", source=f"file://{root_directory}"
    )

    ordered_filenames = data.draw(st.permutations([main_filename, *other_filenames]))
    for filename in ordered_filenames:
        shutil.copy(
            os.path.join(dataset_root, filename),
            os.path.join(root_directory, filename),
        )
        library.scan()

    photo = Photo.objects.get()
    assert photo.main_path == main_filename
    check_expected_metadata(library, main_filename)
    check_matched_files(library, main_filename)
