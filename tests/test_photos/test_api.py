import io
from collections.abc import Sequence
from typing import Any, ClassVar, Optional

import hypothesis
import PIL.Image
import pytest
from django.http import StreamingHttpResponse
from django.test import Client
from hypothesis.extra.django import TestCase
from parameterized import parameterized

from tumpara import api
from tumpara.libraries.models import Library, Visibility
from tumpara.testing import strategies as st

from .dataset import index
from .test_scanning import dataset_root


# Use a Django test case here so that we don't need to re-scan the library for every
# test.
class PhotoApiTestCase(TestCase):
    asset_node_ids: ClassVar[dict[str, str]]

    @classmethod
    def setUpTestData(cls) -> None:
        library = Library.objects.create(
            context="gallery",
            source=f"file://{dataset_root}",
            default_visibility=Visibility.PUBLIC,
        )
        library.scan()

        cls.asset_node_ids = {}
        cls._get_asset_node_ids()

    @classmethod
    def _get_asset_node_ids(cls) -> None:
        all_paths = set(index.keys())
        result = api.execute_sync(
            """query AllPhotos {
                assets(first: 100) {
                    nodes {
                        __typename
                        id
                        files(first: 10) {
                            nodes {
                                path
                            }
                        }
                    }
                }
            }"""
        )
        assert result.errors is None
        assert result.data is not None
        for node in result.data["assets"]["nodes"]:
            assert isinstance(node["id"], str)
            for file_node in node["files"]["nodes"]:
                if file_node["path"] in all_paths:
                    cls.asset_node_ids[file_node["path"]] = node["id"]

    @parameterized.expand(
        [
            ({"Width": {"minimum": 6000}}, ["IMG_3452.jpg", "IMG_3452.CR2"]),
            (
                {"Megapixels": {"minimum": 24}},
                ["IMG_3452.jpg", "IMG_3452.CR2", "DSC00372.jpg", "DSC00372.arw"],
            ),
            (
                {"AspectRatio": {"minimum": 1.6}},
                ["mwhklqGVzck.jpg"],
            ),
        ],
    )
    def test_filtering(
        self, photo_filter: dict[Any, Any], expected_paths: Sequence[str]
    ) -> None:
        """Photo filtering returns the correct subset."""
        result = api.execute_sync(
            """query FilterPhotos($filter: AssetFilter!) {
                assets(first: 10, filter: $filter) {
                    nodes {
                        __typename
                        files(first: 10) {
                            nodes {
                                path
                            }
                        }
                    }
                }
            }
            """,
            filter={f"photo{key}": value for key, value in photo_filter.items()},
        )
        assert result.errors is None
        assert result.data is not None
        received_paths = list[str]()
        for node in result.data["assets"]["nodes"]:
            assert node["__typename"] == "Photo"
            for file_node in node["files"]["nodes"]:
                assert isinstance(file_node["path"], str)
                received_paths.append(file_node["path"])
        # Using lists instead of sets here makes sure that we don't have any duplicate
        # paths.
        assert sorted(received_paths) == sorted(expected_paths)

    @hypothesis.settings(max_examples=50, deadline=None)
    @hypothesis.given(
        st.sampled_from(list(index.keys())),
        st.one_of(st.none(), st.integers(0, 2000)),
        st.one_of(st.none(), st.integers(0, 2000)),
    )
    def test_thumbnails(
        self, path: str, max_width: Optional[int], max_height: Optional[int]
    ) -> None:
        node_id = self.asset_node_ids[path]
        result = api.execute_sync(
            """query AllPhotos($id: ID!, $width: Int, $height: Int) {
                node(id: $id) {
                    ... on Photo {
                        thumbnailUrl(width: $width, height: $height)
                    }
                }
            }""",
            id=node_id,
            width=max_width,
            height=max_height,
        )
        assert result.errors is None
        assert result.data is not None
        assert isinstance(thumbnail_url := result.data["node"]["thumbnailUrl"], str)

        client = Client()
        response = client.get(thumbnail_url, headers={"Accept": "image/webp"})
        assert response.status_code == 200
        assert response.headers.get("Content-Type") == "image/webp"
        assert isinstance(response, StreamingHttpResponse)

        image = PIL.Image.open(io.BytesIO(b"".join(response.streaming_content)))
        if max_width:
            assert image.width <= max_width
        if max_height:
            assert image.height <= max_height
