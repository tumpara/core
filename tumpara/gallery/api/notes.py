from collections.abc import Sequence
from typing import Optional

import strawberry
from django import forms

from tumpara import api
from tumpara.libraries.api import AssetVisibility

from ..models import GalleryAssetModel, Note
from .gallery_assets import (
    GalleryAssetFilter,
    GalleryAssetNode,
    register_gallery_asset_filter,
)


@register_gallery_asset_filter
class NoteGalleryAssetFilter(GalleryAssetFilter):
    include_notes: bool = strawberry.field(
        default=True, description="Whether to include note results."
    )

    def get_instance_types(self) -> Sequence[type[GalleryAssetModel]]:
        return [*super().get_instance_types(), Note]


@api.remove_duplicate_node_interface
@strawberry.type(name="Note", description="A user-created note asset.")
class NoteNode(GalleryAssetNode, api.DjangoNode, fields=["content"]):
    obj: strawberry.Private[Note]


class NoteForm(forms.ModelForm[Note]):
    class Meta:
        model = Note
        fields = ["content", "visibility", "library"]


@strawberry.input(description="Create a new note.")
class CreateNoteInput(
    api.CreateFormInput[NoteForm, NoteNode],
):
    visibility: AssetVisibility


@strawberry.input(description="Edit and existing note.")
class UpdateNoteInput(
    api.UpdateFormInput[NoteForm, NoteNode],
):
    visibility: Optional[AssetVisibility]


NoteMutationResult = strawberry.union(
    "NoteMutationResult", (NoteNode, api.FormError, api.NodeError)
)


@api.schema.mutation
class Mutation:
    @strawberry.field(
        description=CreateNoteInput._type_definition.description,  # type: ignore
    )
    def create_note(
        self, info: api.InfoType, input: CreateNoteInput
    ) -> Optional[NoteMutationResult]:
        return input.resolve(info)

    @strawberry.field(
        description=UpdateNoteInput._type_definition.description,  # type: ignore
    )
    def update_note(
        self, info: api.InfoType, input: UpdateNoteInput
    ) -> Optional[NoteMutationResult]:
        return input.resolve(info)
