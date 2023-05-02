import json
import logging
import os.path
import re
import select
import subprocess
from typing import Any, Optional

from django.conf import settings

_logger = logging.getLogger(__name__)

_exiftool_process: Optional[subprocess.Popen[str]] = None


class ExiftoolError(IOError):
    pass


class ExiftoolNotFound(ExiftoolError):
    pass


class ExiftoolOutputToLarge(ExiftoolError):
    pass


class ExiftoolNonzeroExitCode(ExiftoolError):
    pass


def execute_exiftool(*exiftool_arguments: str) -> list[dict[str, Any]]:
    """Run Exiftool with the specified arguments in JSON mode, parse the result and
    return it.

    This will keep an Exiftool instance running in the background to avoid creating too
    many processes. Make sure to call :meth:`close_exiftool` when you are done using it.

    This function is not threadsafe.
    """
    global _exiftool_process

    if _exiftool_process is None:
        try:
            _exiftool_process = subprocess.Popen(
                [
                    settings.EXIFTOOL_BINARY,
                    "-stay_open",
                    "True",
                    "-@",
                    "-",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={"TZ": "UTC", "LANG": "C"},
            )
        except FileNotFoundError as error:
            if not os.path.exists(settings.EXIFTOOL_BINARY):
                _logger.warning(
                    f"Could not find the specified Exiftool binary "
                    f"{settings.EXIFTOOL_BINARY!r}. Image metadata cannot be read."
                )
                raise ExiftoolNotFound() from error
            else:
                raise error
        except subprocess.CalledProcessError as error:
            raise error

    assert _exiftool_process.stdin is not None
    assert _exiftool_process.stdout is not None
    assert _exiftool_process.stderr is not None

    _exiftool_process.stdin.write(
        "\n".join((*exiftool_arguments, "-json", "-echo4", "${status}=", "-execute\n"))
    )
    _exiftool_process.stdin.flush()

    stdout_fd = _exiftool_process.stdout.fileno()
    stderr_fd = _exiftool_process.stderr.fileno()
    output = b""
    error_output = b""
    chunk_count = 0

    while not output.endswith(b"{ready}\n"):
        input_ready_fds, _, _ = select.select([stdout_fd, stderr_fd], [], [])
        for fd in input_ready_fds:
            if fd == stdout_fd:
                raw_chunk = os.read(fd, 4096)
                if chunk_count < settings.EXIFTOOL_MAX_OUTPUT_SIZE:
                    output += raw_chunk
                chunk_count += 1
            if fd == stderr_fd:
                error_output += os.read(fd, 4096)

    _exiftool_process.stdout.flush()
    _exiftool_process.stderr.flush()

    if chunk_count >= settings.EXIFTOOL_MAX_OUTPUT_SIZE:
        raise ExiftoolOutputToLarge(
            f"Exiftool returned a larger JSON output than expected ({chunk_count} 4KiB "
            f"chunks). Refusing to parse. Called with these arguments: "
            f"{exiftool_arguments!r}"
        )

    if match_object := re.search(r"(\d+)=$", error_output.decode().strip()):
        return_code = int(match_object.groups(1)[0])
        if return_code != 0:
            raise ExiftoolNonzeroExitCode(
                f"Exiftool returned the nonzero exit code {return_code}. Called "
                f"with these arguments: {exiftool_arguments!r}"
            )

    result = json.loads(output[:-8])
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, dict)
        assert all(isinstance(key, str) for key in item.keys())
    return result


def stop_exiftool() -> None:
    """Close the running Exiftool instance, if any."""
    global _exiftool_process
    if _exiftool_process is None:
        return
    if _exiftool_process.stdin is not None:
        _exiftool_process.stdin.write("-stay_open\nFalse\n")
        _exiftool_process.stdin.flush()
    _exiftool_process.wait(timeout=2)
    if _exiftool_process.poll() is None:
        _exiftool_process.kill()
    _exiftool_process = None
