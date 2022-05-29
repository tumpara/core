from typing import Mapping, Protocol

from django.db import models

from ..utils import InfoType


class GenericFilter(Protocol):
    def build_query(
        self, info: InfoType, field_name: str
    ) -> models.Q | tuple[models.Q, Mapping[str, models.Expression | models.F]]:
        """Build the database lookup for this filter.

        :param info: Resolve information for the current API request.
        :param field_name: Name of the field or related field lookup the filter should
            be applied on. For example, if you want to query a name field, this should
            be set to ``name``. If you want to query the name field of a related
            collection object, this should be ``collections__name``. When building a
            lookup for the top-level queryset of the correct type, set this to an empty
            string.
        :return: A Django :class:`models.Q` object. Alternatively, a tuple consisting of
            the :class:`models.Q` object and a dictionary of aliases may also be
            returned. In the latter case the aliases will be applied using
            :meth:`models.QuerySet.alias` before filtering.
        """
