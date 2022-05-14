Library System
==============

Data Model
----------

``tumpara.libraries.models`` defines these models:

.. autoclass:: tumpara.libraries.models.Library
  :members:

.. autoclass:: tumpara.libraries.models.Asset
  :members:

.. autoclass:: tumpara.libraries.models.File
  :members:

Storage Backends
----------------

Extending
---------

Signals
~~~~~~~

The following `Signals`_ can be used to implement support for different file types in Tumpara.
These are sent when scanning a library produces some sort of change.

Some pass the library's ``context`` value as the sender –
this value is user-provided and determines what greater part of the application should handle the contents for each library.
For example, video files in a library intended for storing home video may be indexed and managed differently than video in a library intended for storing movies.

.. _Signals: https://docs.djangoproject.com/en/4.0/topics/signals

.. automodule:: tumpara.libraries.signals
   :members:
