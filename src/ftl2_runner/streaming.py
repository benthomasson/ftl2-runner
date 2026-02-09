"""Streaming protocol for ansible-runner compatibility.

The Worker receives data from Receptor via stdin:
1. {"kwargs": {...}} - job parameters
2. {"zipfile": N} + base64 encoded zip data - private_data_dir contents
3. {"eof": true} - end of input

The Worker writes events to stdout:
1. {"status": "starting", ...} - status events
2. {"event": "runner_on_ok", ...} - job events
3. {"zipfile": N} + base64 encoded zip data - artifacts
4. {"eof": true} - end of output
"""

import base64
import io
import json
import os
import stat
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, BinaryIO


class Base64Reader:
    """Read base64 encoded data from a stream."""

    def __init__(self, stream: BinaryIO):
        self._stream = stream
        self._buffer = b""

    def read(self, size: int) -> bytes:
        """Read decoded bytes from base64 stream."""
        # Read base64 encoded data (4 bytes encode 3 decoded bytes)
        encoded_size = ((size + 2) // 3) * 4

        while len(self._buffer) < size:
            encoded = self._stream.read(encoded_size)
            if not encoded:
                break
            # Strip whitespace and decode
            encoded = encoded.replace(b"\n", b"").replace(b"\r", b"")
            self._buffer += base64.b64decode(encoded)

        result = self._buffer[:size]
        self._buffer = self._buffer[size:]
        return result


class Base64Writer:
    """Write base64 encoded data to a stream."""

    def __init__(self, stream: BinaryIO):
        self._stream = stream

    def write(self, data: bytes) -> int:
        """Write bytes as base64 encoded data."""
        encoded = base64.b64encode(data)
        self._stream.write(encoded)
        return len(data)

    def flush(self) -> None:
        """Flush the stream."""
        self._stream.flush()


def unstream_dir(stream: BinaryIO, length: int, target_directory: str) -> None:
    """Unpack a streamed zip file to target directory.

    Args:
        stream: Input stream with base64 encoded zip data
        length: Size of the zip file in bytes
        target_directory: Directory to extract to
    """
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name
        try:
            # Read base64 encoded data and decode to temp file
            reader = Base64Reader(stream)
            remaining = length
            chunk_size = 1024 * 1000  # 1 MB

            while remaining > 0:
                to_read = min(chunk_size, remaining)
                data = reader.read(to_read)
                if not data:
                    break
                tmp.write(data)
                remaining -= len(data)

            tmp.flush()

            # Extract zip to target directory
            with zipfile.ZipFile(tmp_path, "r") as archive:
                for info in archive.infolist():
                    out_path = os.path.join(target_directory, info.filename)

                    # Get permissions
                    perms = info.external_attr >> 16
                    if perms:
                        mode = stat.filemode(perms)
                        is_symlink = mode[:1] == "l"
                    else:
                        is_symlink = False

                    # Handle existing files
                    if os.path.exists(out_path):
                        if is_symlink:
                            os.remove(out_path)
                        elif os.path.isdir(out_path):
                            continue

                    archive.extract(info.filename, path=target_directory)

                    # Preserve modification times
                    date_time = time.mktime(info.date_time + (0, 0, -1))
                    os.utime(out_path, times=(date_time, date_time))

                    # Handle symlinks and permissions
                    if is_symlink:
                        with open(out_path) as fd:
                            link = fd.read()
                        os.remove(out_path)
                        os.symlink(link, out_path)
                    elif perms:
                        os.chmod(out_path, perms)

        finally:
            os.unlink(tmp_path)


def stream_dir(source_directory: str, stream: BinaryIO) -> None:
    """Stream a directory as a zip file.

    Args:
        source_directory: Directory to zip and stream
        stream: Output stream
    """
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Create zip file
        with zipfile.ZipFile(
            tmp_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
        ) as archive:
            if source_directory and os.path.exists(source_directory):
                for dirpath, dirs, files in os.walk(source_directory):
                    relpath = os.path.relpath(dirpath, source_directory)
                    if relpath == ".":
                        relpath = ""

                    for fname in files + dirs:
                        full_path = os.path.join(dirpath, fname)

                        # Skip pipes
                        if os.path.exists(full_path) and stat.S_ISFIFO(
                            os.stat(full_path).st_mode
                        ):
                            continue

                        # Handle symlinks
                        if os.path.islink(full_path):
                            file_relative_path = os.path.join(relpath, fname)
                            zip_info = zipfile.ZipInfo(file_relative_path)
                            zip_info.create_system = 3
                            permissions = 0o777 | 0xA000
                            zip_info.external_attr = permissions << 16
                            archive.writestr(zip_info, os.readlink(full_path))
                        else:
                            archive.write(full_path, arcname=os.path.join(relpath, fname))

        # Get zip size and stream it
        zip_size = Path(tmp_path).stat().st_size

        # Write size header
        stream.write(json.dumps({"zipfile": zip_size}).encode("utf-8") + b"\n")
        stream.flush()

        # Stream base64 encoded content
        writer = Base64Writer(stream)
        with open(tmp_path, "rb") as source:
            while chunk := source.read(1024 * 1000):
                writer.write(chunk)
        stream.flush()

    finally:
        os.unlink(tmp_path)


def read_input_stream(
    stream: BinaryIO, private_data_dir: str
) -> dict[str, Any]:
    """Read input stream and unpack to private_data_dir.

    Args:
        stream: Input stream (stdin)
        private_data_dir: Directory to unpack to

    Returns:
        Job kwargs dict from stream
    """
    kwargs: dict[str, Any] = {}

    while True:
        line = stream.readline()
        if not line:
            break

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        if "kwargs" in data:
            kwargs = data["kwargs"]
        elif "zipfile" in data:
            unstream_dir(stream, data["zipfile"], private_data_dir)
        elif "eof" in data:
            break

    return kwargs


def write_event(stream: BinaryIO, event: dict[str, Any]) -> None:
    """Write an event to the output stream.

    Args:
        stream: Output stream (stdout)
        event: Event dict to write
    """
    stream.write(json.dumps(event, default=str).encode("utf-8") + b"\n")
    stream.flush()


def write_status(stream: BinaryIO, status: str, **extra: Any) -> None:
    """Write a status event to the output stream.

    Args:
        stream: Output stream (stdout)
        status: Status string
        **extra: Additional fields
    """
    event = {"status": status, **extra}
    write_event(stream, event)


def write_eof(stream: BinaryIO) -> None:
    """Write EOF marker to output stream.

    Args:
        stream: Output stream (stdout)
    """
    stream.write(json.dumps({"eof": True}).encode("utf-8") + b"\n")
    stream.flush()
