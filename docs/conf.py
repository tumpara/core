# Documentation config file, built with sphinx-quickstart.
#
# See here for a complete reference:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import inspect
import sys
from os import environ
from pathlib import Path

import django
import django.db.models
from django.utils.encoding import force_str
from django.utils.html import strip_tags
from pygments_graphql import GraphqlLexer

# Make sure we are documenting the actual code and not some other potentially installed
# version of the app.
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup the Django app so that we can document models.
environ.setdefault("DJANGO_SETTINGS_MODULE", "tumpara.settings.development")
django.setup()


# -- Project information ---------------------------------------------------------------

project = "Tumpara"
copyright = "2022, Yannik Rödel"
author = "Yannik Rödel"

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]


# -- Other Sphinx configuration --------------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
]

html_theme = "furo"

# sphinx.ext.autodoc
# https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html#configuration
autodoc_default_options = {
    "ember-order": "bysource",
    "special-members": "__init__",
    "exclude-members": "__weakref__, DoesNotExist, MultipleObjectsReturned",
}

# sphinx.ext.intersphinx
# https://www.sphinx-doc.org/en/master/usage/extensions/intersphinx.html#configuration
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "django": (
        "http://docs.djangoproject.com/en/4.0/",
        "http://docs.djangoproject.com/en/4.0/_objects/",
    ),
}


# -- Compile hooks ---------------------------------------------------------------------


def process_docstring(app, what, name, obj, options, lines):
    # Add a parameter docstring for every Django field. This is taken (in part) from
    # here: https://djangosnippets.org/snippets/2533/
    if inspect.isclass(obj) and issubclass(obj, django.db.models.Model):
        for field in obj._meta.fields:
            help_text = strip_tags(force_str(field.help_text))
            verbose_name = force_str(field.verbose_name).capitalize()

            # Add the model field to the end of the docstring so that it is documented.
            # This will use either the help text or the verbose name.
            lines.append(
                f":param {field.attname}: {help_text or verbose_name}"
            )

            # Document the type as well. If the field is available through the
            # django.db.models module then that is used (because then Intersphinx can
            # link to the documentation). In all other cases, we fall back to the
            # referring the actual field class.
            field_type = type(field)
            try:
                assert getattr(django.db.models, field_type.__name__) is field_type
                lines.append(
                    f":type {field.attname}: ~django.db.models.{field_type.__name__}"
                )
            except (AttributeError, AssertionError):
                lines.append(
                    f":type {field.attname}: "
                    f"~{field_type.__module__}.{field_type.__name__}"
                )

    return lines


def setup(app):
    app.add_lexer("graphql", GraphqlLexer)
    app.connect("autodoc-process-docstring", process_docstring)
