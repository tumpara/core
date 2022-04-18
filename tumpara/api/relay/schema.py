from typing import Annotated, Optional

import strawberry

from ..utils import InfoType
from .base import Node, resolve_node


@strawberry.type
class Query:
    @strawberry.field(description="Resolve a node by its ID.")
    def node(
        self,
        info: InfoType,
        node_id: Annotated[
            strawberry.ID,
            strawberry.argument(name="id", description="The global ID to resolve."),
        ],
    ) -> Optional[Node]:
        return resolve_node(info, str(node_id))
