import PIL.Image
from django.conf import settings
from django.core import signing
from django.http import Http404, HttpRequest, HttpResponseBadRequest
from django.http.response import HttpResponseBase

from tumpara.api.views import serve_file

from .models import Photo
from .utils import load_image

AVIF_SUPPORTED: bool
try:
    import pillow_avif.AvifImagePlugin  # type: ignore[import]

    AVIF_SUPPORTED = pillow_avif.AvifImagePlugin.SUPPORTED
except ImportError:
    AVIF_SUPPORTED = False


def render_thumbnail(request: HttpRequest, description: str) -> HttpResponseBase:
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
        ValueError,
        signing.BadSignature,
        signing.SignatureExpired,
    ):
        raise Http404()

    # There are still some formats that we would like to support in the long term.
    # Mainly AVIF, which is blocked by this issue:
    # https://github.com/python-pillow/Pillow/pull/5201
    if AVIF_SUPPORTED and request.accepts("image/avif"):
        format_name = "avif"
    elif request.accepts("image/webp"):
        format_name = "webp"
    elif request.accepts("image/jpeg"):
        format_name = "jpeg"
    else:
        return HttpResponseBadRequest("Bad Accept header")

    filename = f"{photo_pk}_{requested_width}x{requested_height}.{format_name}"

    if not settings.THUMBNAIL_STORAGE.exists(filename):
        try:
            photo = Photo.objects.select_related("library").get(pk=photo_pk)
        except Photo.DoesNotExist:
            raise Http404()
        try:
            image, _ = load_image(photo.library, photo.main_path)
        except IsADirectoryError as error:
            raise

        image.thumbnail(
            (
                # This means that both None and 0 evaluate to the original dimensions.
                # An empty API call to thumbnailUrl() will therefore render the image
                # as-is.
                requested_width or image.width,
                requested_height or image.height,
            ),
            PIL.Image.BICUBIC,
        )

        with settings.THUMBNAIL_STORAGE.open(filename, "wb") as file_io:
            image.save(file_io, format=format_name.upper())

    return serve_file(request, settings.THUMBNAIL_STORAGE, filename)
