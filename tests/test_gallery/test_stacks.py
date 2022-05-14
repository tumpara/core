import pytest

from tumpara.gallery.models import GalleryAsset
from tumpara.libraries.models import Library


@pytest.fixture
def assets() -> list[GalleryAsset]:
    library = Library.objects.create(source=f"testing:///a", context="test_storage")
    return [
        GalleryAsset.objects.create(pk=index, library=library) for index in range(0, 10)
    ]


@pytest.mark.django_db
def test_stacking(assets: list[GalleryAsset]) -> None:
    # Stack the first half of the assets together and make sure they all have the
    # same key.
    assert GalleryAsset.objects.filter(pk__lt=5).stack() == 5
    assets[0].refresh_from_db()
    first_stack_key = assets[0].stack_key
    for asset in assets[1:5]:
        asset.refresh_from_db()
        assert asset.stack_key == first_stack_key
    first_representatives = [
        asset for asset in assets[0:5] if asset.stack_representative
    ]
    assert len(first_representatives) == 1

    # Stack some from the other half together. They should get a different key.
    assert GalleryAsset.objects.filter(pk__gte=5, pk__lt=9).stack() == 4
    assets[5].refresh_from_db()
    second_stack_key = assets[5].stack_key
    assert second_stack_key != first_stack_key
    for asset in assets[6:9]:
        asset.refresh_from_db()
        assert asset.stack_key == second_stack_key
    second_representatives = [
        asset for asset in assets[5:9] if asset.stack_representative
    ]
    assert len(second_representatives) == 1

    assets[9].refresh_from_db()
    assert assets[9].stack_key is None

    # Now stack everything together. This should lead to the two stacks joining.
    assert GalleryAsset.objects.filter(pk__in=[4, 5, 9]).stack() == 10
    for asset in assets:
        asset.refresh_from_db()
        assert asset.stack_key == first_stack_key
    end_representatives = [asset for asset in assets[5:9] if asset.stack_representative]
    assert len(end_representatives) == 1
    assert end_representatives[0].pk == 5


@pytest.mark.django_db
def test_stacking_representatives(assets: list[GalleryAsset]) -> None:
    """Stacking assets together chooses an appropriate representative."""

    def refresh_all() -> None:
        for asset in assets:
            asset.refresh_from_db()

    assert GalleryAsset.objects.filter(pk__in=[0, 1]).stack() == 2
    # When unsure, the representative falls to the smallest index.
    refresh_all()
    assert assets[0].stack_representative
    assert not assets[1].stack_representative

    assert GalleryAsset.objects.filter(pk__in=[0, 2]).stack() == 3
    # Since the asset with index 0 was already a representative, that one should have
    # been picked.
    refresh_all()
    assert assets[0].stack_representative
    assert not assets[1].stack_representative
    assert not assets[2].stack_representative

    assert GalleryAsset.objects.filter(pk__in=[1, 3]).stack() == 4
    # The representative should still be the asset with index 0 because that one was
    # a representative before and we want to keep that status, if possible.
    assert assets[0].stack_representative
    assert not assets[1].stack_representative
    assert not assets[2].stack_representative
    assert not assets[3].stack_representative

    assert GalleryAsset.objects.filter(pk__in=[4, 5]).stack() == 2
    # This is the first case again.
    refresh_all()
    assert assets[4].stack_representative
    assert not assets[5].stack_representative

    assert GalleryAsset.objects.filter(pk__in=[3, 4]).stack() == 6
    # Since 4 was already a representative but 3 was not, the representative of our
    # stack should be moved from 0 to 4.
    refresh_all()
    assets = assets  # This is to please MyPy.
    assert not assets[0].stack_representative
    assert not assets[1].stack_representative
    assert not assets[2].stack_representative
    assert not assets[3].stack_representative
    assert assets[4].stack_representative
    assert not assets[5].stack_representative

    assert GalleryAsset.objects.filter(pk__in=[6, 7]).stack() == 2
    assert GalleryAsset.objects.filter(pk__in=[1, 7]).stack() == 8
    # This is the second case again.
    refresh_all()
    assert not assets[0].stack_representative
    assert not assets[1].stack_representative
    assert not assets[2].stack_representative
    assert not assets[3].stack_representative
    assert assets[4].stack_representative
    assert not assets[5].stack_representative
    assert not assets[6].stack_representative
    assert not assets[7].stack_representative


@pytest.mark.django_db
def test_unstacking(assets: list[GalleryAsset]) -> None:
    GalleryAsset.objects.filter(pk__lt=5).stack()
    GalleryAsset.objects.filter(pk__gte=5).stack()
    assert GalleryAsset.objects.filter(pk__in=[3, 5]).unstack() == 10
    for asset in assets:
        asset.refresh_from_db()
        assert asset.stack_key is None
        assert asset.stack_representative is False


@pytest.mark.django_db
def test_representative_setting(assets: list[GalleryAsset]) -> None:
    """Assets can explicitly be set as the representative of a stack."""

    def refresh_all() -> None:
        for asset in assets:
            asset.refresh_from_db()

    GalleryAsset.objects.filter(pk__lt=4).stack()
    refresh_all()
    assert assets[0].stack_representative
    assert not assets[1].stack_representative
    assert not assets[2].stack_representative
    assert not assets[3].stack_representative

    assets[2].represent_stack()
    # assets[2] is tested twice because we want to make sure the flag is set before
    # refreshing as well.
    assets = assets  # This is to please MyPy.
    assert assets[2].stack_representative
    refresh_all()
    assert not assets[0].stack_representative
    assert not assets[1].stack_representative
    assert assets[2].stack_representative
    assert not assets[3].stack_representative

    assets[3].represent_stack()
    assets = assets
    assert assets[3].stack_representative
    refresh_all()
    assert not assets[0].stack_representative
    assert not assets[1].stack_representative
    assert not assets[2].stack_representative
    assert assets[3].stack_representative
