from django.conf import settings
from django.core import signing
from django.http import Http404, HttpRequest, HttpResponseBadRequest
from django.http.response import HttpResponseBase

from tumpara.api.views import serve_file

from .models import Photo
from .utils import AVIF_SUPPORTED


def thumbnail_from_description(
    request: HttpRequest, description: str
) -> HttpResponseBase:
    """Serve a thumbnailed version of a :class:`~tumpara.photos.models.Photo`.

    :param description: Information denoting which photo should be rendered and how.
        This must be a 3-tuple signed with the Django's :func:`signing.dumps`. It
        consists of the photo's primary key and the requested width and height, in that
        order.
    """
    try:
        photo_pk, requested_width, requested_height = signing.loads(
            description,
            salt="tumpara.photos.views.render_thumbnail",
            max_age=settings.API_LINK_VALIDITY_TIME,
        )
        assert isinstance(photo_pk, int)
        assert requested_width is None or (
            isinstance(requested_width, int) and requested_width >= 0
        )
        assert requested_height is None or (
            isinstance(requested_height, int) and requested_height >= 0
        )
    except (
        AssertionError,
        TypeError,
        ValueError,
        signing.BadSignature,
        signing.SignatureExpired,
    ):
        raise Http404()

    if AVIF_SUPPORTED and request.accepts("image/avif"):
        format_name = "avif"
    elif request.accepts("image/webp"):
        format_name = "webp"
    elif request.accepts("image/jpeg"):
        format_name = "jpeg"
    else:
        return HttpResponseBadRequest("Bad Accept header")

    try:
        photo = (
            Photo.objects.select_related("library")
            .only("library__source", "main_path")
            .get(pk=photo_pk)
        )
    except Photo.DoesNotExist:
        raise Http404()
    else:
        return serve_file(
            request,
            settings.THUMBNAIL_STORAGE,
            photo.render_thumbnail(format_name, requested_width, requested_height),
        )
