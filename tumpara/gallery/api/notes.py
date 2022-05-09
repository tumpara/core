from typing import Optional

import strawberry
from django import forms

from tumpara import api
from tumpara.libraries.api import RecordVisibility

from ..models import Note
from .base import GalleryRecordNode


@api.remove_duplicate_node_interface
@strawberry.type(name="Note", description="A user-created note record.")
class NoteNode(GalleryRecordNode, api.DjangoNode[Note], fields=["content"]):
    pass


class NoteForm(forms.ModelForm[Note]):
    class Meta:
        model = Note
        fields = ["content", "visibility", "library"]


@strawberry.input(description="Create a new note.")
class CreateNoteInput(
    api.CreateFormInput[NoteForm],
    related_permissions={"library": "libraries.change_library"},
):
    visibility: RecordVisibility


@strawberry.input(description="Edit and existing note.")
class UpdateNoteInput(
    api.UpdateFormInput[NoteForm],
    related_permissions={"library": "libraries.change_library"},
):
    visibility: Optional[RecordVisibility]  # type: ignore


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
