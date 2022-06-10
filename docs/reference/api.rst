API
===

File downloads
--------------

Some fields in the API schema return URLs where clients can download files from Tumpara.
This is used both for serving unaltered files from storage backends as well as for modified versions (for example thumbnails).
Download requests do not need to include an API key.
Instead, the URLs returned from GraphQL are signed using Django's `signing framework`_ to block unauthorized access.

.. _signing framework: https://docs.djangoproject.com/en/4.0/topics/signing/

That means that when a user requests to download -- for example -- the thumbnail of a :class:`~tumpara.photos.models.Photo`, they get a link that encodes which photo they meant together with a cryptographic signature verifying that they indeed have sufficient permissions to view it.
Other than that, nothing happens yet.
Only once this link is actually accessed will the thumbnail be generated, cached and served.

For the last step, we provide a helper method that serves the file as efficiently as possible:

.. autofunction:: tumpara.api.views.serve_file

This approach using signed requests has the benefit that clients don't need to add special headers or cookies in order to authenticate themselves when requesting files.
Especially for browsers, this means that images can placed directly into an ``<img>`` tag without needing to worry about authentication.
It further allows the browser cache to be leveraged.
