import pytest

from tumpara.gallery.models import GalleryRecord
from tumpara.libraries.models import Library


@pytest.fixture
def records() -> list[GalleryRecord]:
    library = Library.objects.create(source=f"testing:///a", context="test_storage")
    return [
        GalleryRecord.objects.create(pk=index, library=library)
        for index in range(0, 10)
    ]


@pytest.mark.django_db
def test_stacking(records: list[GalleryRecord]) -> None:
    # Stack the first half of the records together and make sure they all have the
    # same key.
    assert GalleryRecord.objects.filter(pk__lt=5).stack() == 5
    records[0].refresh_from_db()
    first_stack_key = records[0].stack_key
    for record in records[1:5]:
        record.refresh_from_db()
        assert record.stack_key == first_stack_key
    first_representatives = [
        record for record in records[0:5] if record.stack_representative
    ]
    assert len(first_representatives) == 1

    # Stack some from the other half together. They should get a different key.
    assert GalleryRecord.objects.filter(pk__gte=5, pk__lt=9).stack() == 4
    records[5].refresh_from_db()
    second_stack_key = records[5].stack_key
    assert second_stack_key != first_stack_key
    for record in records[6:9]:
        record.refresh_from_db()
        assert record.stack_key == second_stack_key
    second_representatives = [
        record for record in records[5:9] if record.stack_representative
    ]
    assert len(second_representatives) == 1

    records[9].refresh_from_db()
    assert records[9].stack_key is None

    # Now stack everything together. This should lead to the two stacks joining.
    assert GalleryRecord.objects.filter(pk__in=[4, 5, 9]).stack() == 10
    for record in records:
        record.refresh_from_db()
        assert record.stack_key == first_stack_key
    end_representatives = [
        record for record in records[5:9] if record.stack_representative
    ]
    assert len(end_representatives) == 1
    assert end_representatives[0].pk == 5


@pytest.mark.django_db
def test_stacking_representatives(records: list[GalleryRecord]) -> None:
    """Stacking records together chooses an appropriate representative."""

    def refresh_all() -> None:
        for record in records:
            record.refresh_from_db()

    assert GalleryRecord.objects.filter(pk__in=[0, 1]).stack() == 2
    # When unsure, the representative falls to the smallest index.
    refresh_all()
    assert records[0].stack_representative
    assert not records[1].stack_representative

    assert GalleryRecord.objects.filter(pk__in=[0, 2]).stack() == 3
    # Since the record with index 0 was already a representative, that one should have
    # been picked.
    refresh_all()
    assert records[0].stack_representative
    assert not records[1].stack_representative
    assert not records[2].stack_representative

    assert GalleryRecord.objects.filter(pk__in=[1, 3]).stack() == 4
    # The representative should still be the record with index 0 because that one was
    # a representative before and we want to keep that status, if possible.
    assert records[0].stack_representative
    assert not records[1].stack_representative
    assert not records[2].stack_representative
    assert not records[3].stack_representative

    assert GalleryRecord.objects.filter(pk__in=[4, 5]).stack() == 2
    # This is the first case again.
    refresh_all()
    assert records[4].stack_representative
    assert not records[5].stack_representative

    assert GalleryRecord.objects.filter(pk__in=[3, 4]).stack() == 6
    # Since 4 was already a representative but 3 was not, the representative of our
    # stack should be moved from 0 to 4.
    refresh_all()
    records = records  # This is to please MyPy.
    assert not records[0].stack_representative
    assert not records[1].stack_representative
    assert not records[2].stack_representative
    assert not records[3].stack_representative
    assert records[4].stack_representative
    assert not records[5].stack_representative

    assert GalleryRecord.objects.filter(pk__in=[6, 7]).stack() == 2
    assert GalleryRecord.objects.filter(pk__in=[1, 7]).stack() == 8
    # This is the second case again.
    refresh_all()
    assert not records[0].stack_representative
    assert not records[1].stack_representative
    assert not records[2].stack_representative
    assert not records[3].stack_representative
    assert records[4].stack_representative
    assert not records[5].stack_representative
    assert not records[6].stack_representative
    assert not records[7].stack_representative


@pytest.mark.django_db
def test_unstacking(records: list[GalleryRecord]) -> None:
    GalleryRecord.objects.filter(pk__lt=5).stack()
    GalleryRecord.objects.filter(pk__gte=5).stack()
    assert GalleryRecord.objects.filter(pk__in=[3, 5]).unstack() == 10
    for record in records:
        record.refresh_from_db()
        assert record.stack_key is None
        assert record.stack_representative is False


@pytest.mark.django_db
def test_representative_setting(records: list[GalleryRecord]) -> None:
    """Records can explicitly set as representative."""

    def refresh_all() -> None:
        for record in records:
            record.refresh_from_db()

    GalleryRecord.objects.filter(pk__lt=4).stack()
    refresh_all()
    assert records[0].stack_representative
    assert not records[1].stack_representative
    assert not records[2].stack_representative
    assert not records[3].stack_representative

    records[2].represent_stack()
    # records[2] is tested twice because we want to make sure the flag is set before
    # refreshing as well.
    records = records  # This is to please MyPy.
    assert records[2].stack_representative
    refresh_all()
    assert not records[0].stack_representative
    assert not records[1].stack_representative
    assert records[2].stack_representative
    assert not records[3].stack_representative

    records[3].represent_stack()
    records = records
    assert records[3].stack_representative
    refresh_all()
    assert not records[0].stack_representative
    assert not records[1].stack_representative
    assert not records[2].stack_representative
    assert records[3].stack_representative
