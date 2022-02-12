import os.path
import shutil
import tempfile
from typing import Any, Collection

import hypothesis.control
from hypothesis import assume
from hypothesis import strategies as st


@st.composite
def temporary_directories(draw: st.DrawFn) -> str:
    """Hypothesis strategy that creates temporary directories."""
    directory = tempfile.mkdtemp()

    @hypothesis.control.cleanup  # type: ignore
    def teardown_temporary_directory() -> None:
        shutil.rmtree(directory)

    return directory


@st.composite
def directory_names(draw: st.DrawFn, *, exclude: Collection[str] = ()) -> str:
    """Hypothesis strategy that generates valid directory names, optionally excluding
    a list of already generated names.

    :param exclude: Optional set of names which should be excluded. Any output that is
        already present in this parameter will be discarded.
    """
    result = draw(st.from_regex(r"[a-zA-Z][a-zA-Z\ \-_\.0-9]*", fullmatch=True))
    assume(result not in exclude)
    return result


@st.composite
def filenames(
    draw: st.DrawFn, *, exclude: Collection[str] = (), suffix: str = ""
) -> str:
    """Hypothesis strategy that generates valid filenames with an extension, optionally
    excluding a list of already generated names.

    :param exclude: Optional set of filenames (or paths from which the filenames will
        be extracted) which should be excluded. Any output that is already present in
        this parameter will be discarded.
    :param suffix: Optional suffix that will be appended to all generated filenames.
    """
    result = draw(
        st.from_regex(r"[a-zA-Z0-9][a-zA-Z\ \-_0-9]*\.[a-z0-9]{1,4}", fullmatch=True)
    )
    result += suffix
    assume(result not in {os.path.basename(item) for item in exclude})
    return result


@st.composite
def directory_trees(
    draw: st.DrawFn,
) -> tuple[list[str], list[str], list[Any]]:
    """Hypothesis strategy that generates a random directory tree.

    The tree returned consists of a list of folders, a list of files and a list of
    file contents. Files are distributed among the folders randomly. This strategy
    only yields the structure of the resulting filesystem - no files are actually
    created.
    """
    folders = [""]
    # Create up to 20 additional directories, each underneath one of the existing
    # directories.
    for _ in range(draw(st.integers(1, 4))):
        base = draw(st.sampled_from(folders))
        name = draw(directory_names())
        path = os.path.join(base, name)
        assume(path not in folders)
        folders.append(path)

    file_paths = []
    file_contents = []
    # Create a random number of files in those folders and populate them with random
    # text.
    for _ in range(draw(st.integers(2, 15))):
        directory = draw(st.sampled_from(folders))
        name = draw(filenames())
        path = os.path.join(directory, name)
        assume(path not in file_paths)
        file_paths.append(path)
        file_contents.append(draw(st.text(min_size=1)))

    return folders, file_paths, file_contents
