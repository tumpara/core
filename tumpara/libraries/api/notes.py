from collections.abc import Sequence
from typing import Optional

import strawberry
from django import forms
from django.db import models

from tumpara import api
from tumpara.libraries.api import AssetVisibility

from ..models import AssetModel, Note
from .assets import AssetFilter, AssetNode, register_asset_filter


@register_asset_filter
class NoteAssetFilter(AssetFilter):
    include_notes: bool = strawberry.field(
        default=True, description="Whether to include note results."
    )

    def build_query(
        self, info: api.InfoType, field_name: Optional[str]
    ) -> tuple[models.Q, dict[str, models.Expression | models.F]]:
        prefix = field_name + "__" if field_name else ""
        query, aliases = super().build_query(info, field_name)

        if not self.include_notes:
            query &= models.Q((f"{prefix}note_instance__isnull", True))

        return query, aliases

    def get_instance_types(self) -> Sequence[type[AssetModel]]:
        return [*super().get_instance_types(), Note]


@api.remove_duplicate_node_interface
@strawberry.type(name="Note", description="A user-created note asset.")
class NoteNode(AssetNode, api.DjangoNode, fields=["content"]):
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
