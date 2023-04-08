Libraries and Assets
====================

Almost everything in Tumpara is sorted into *libraries*.
A Library is a collection of *Assets*.
There are different types of assets—some are user-created and some are scanned automatically from files.

In order to see a library's content, you must be a member of that library.
Membership comes in two levels:

- *Regular members* have read-only access and can view assets (including their metadata), sort them into collections and download the corresponding files. You may not, however, edit an asset.
- *Owners* are privileged members that can also edit assets in the library, where it is supported. Owners can also manage the library itself by adding / removing members or changing its settings.

Creating a library
------------------

When creating a library, you will primarily need to specify two options:

- A *source*: this is an URI that denotes where to find files to put in the library. This may be a local folder or some remote (online) data source.
- A *context*: this tells Tumpara what type of content to expect. Depending on the context of library, files found in the source will be handled differently.

See the following sections for details on these two options.

Sources
-------

A source URI looks something like this:

.. code-block::

  backend://something

The important stuff here is the part before ``://``.
It determines which type of backend will be used.
Everything after the two slashes is backend-specific and allows you to provide configuration options specific to the backend.
These are currently supported:

Filesystem
~~~~~~~~~~

This backend uses a directory in the local filesystem.

.. code-block::

  file://<path>

**Parameters**:

- ``path`` – full path to the local directory. Note the leading slash required for *nix-based systems. For example, the source URI ``file:///mnt/storage`` corresponds to the local directory ``/mnt/storage``.

Contexts
--------

Currently the only supported context value is ``gallery``.
