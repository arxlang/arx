"""
title: Module for handling the IO used by the compiler.
"""

import os
import sys
import tempfile

from arx.exceptions import SourceError

MAX_SOURCE_BYTES = 4 * 1024 * 1024


def validate_source_size(value: str) -> None:
    """
    title: Reject source text beyond the documented UTF-8 byte limit.
    parameters:
      value:
        type: str
    """
    try:
        source_size = len(value.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise SourceError(
            "Arx source must be valid UTF-8 text",
            code="ARX-SOURCE-ENCODING-001",
        ) from error
    if source_size > MAX_SOURCE_BYTES:
        raise SourceError(
            "Arx source exceeds the maximum size of "
            f"{MAX_SOURCE_BYTES} UTF-8 bytes",
            code="ARX-SOURCE-SIZE-001",
        )


class ArxBuffer:
    """
    title: ArxBuffer gathers function for handle the system buffer.
    attributes:
      buffer:
        type: str
      position:
        type: int
    """

    buffer: str = ""
    position: int = 0

    def __init__(self) -> None:
        """
        title: Initialize ArxBuffer instance.
        """
        self.clean()

    def clean(self) -> None:
        """
        title: Clean the buffer content.
        """
        self.position = 0
        self.buffer = ""

    def write(self, text: str) -> None:
        """
        title: Write the given text to the buffer.
        parameters:
          text:
            type: str
        """
        self.buffer += text
        self.position = 0

    def read(self) -> str:
        """
        title: Read the buffer content.
        returns:
          type: str
        """
        try:
            i = self.position
            self.position += 1
            return self.buffer[i]
        except IndexError:
            return ""


class ArxIO:
    """
    title: Arx class for Input and Output operations.
    attributes:
      INPUT_FROM_STDIN:
        type: bool
      INPUT_FILE:
        type: str
      EOF:
        type: int
      buffer:
        type: ArxBuffer
    """

    INPUT_FROM_STDIN: bool = False
    INPUT_FILE: str = ""
    EOF: int = sys.maxunicode + 1
    buffer: ArxBuffer = ArxBuffer()

    @classmethod
    def get_char(cls) -> str:
        """
        title: Get a char from the buffer or from the default input.
        returns:
          type: str
          description: A char from the buffer.
        """
        if cls.INPUT_FROM_STDIN:
            return sys.stdin.read(1)
        return cls.buffer.read()

    @classmethod
    def file_to_buffer(cls, filename: str) -> None:
        """
        title: Copy the file content to the buffer.
        parameters:
          filename:
            type: str
            description: The name of the file to be copied to the buffer.
        """
        try:
            if os.path.getsize(filename) > MAX_SOURCE_BYTES:
                raise SourceError(
                    "Arx source exceeds the maximum size of "
                    f"{MAX_SOURCE_BYTES} UTF-8 bytes",
                    code="ARX-SOURCE-SIZE-001",
                )
            with open(filename, "r", encoding="utf-8") as arxfile:
                cls.string_to_buffer(arxfile.read())
        except SourceError:
            raise
        except UnicodeError as error:
            raise SourceError(
                f"Arx source file is not valid UTF-8: {filename}",
                code="ARX-SOURCE-ENCODING-001",
            ) from error
        except OSError as error:
            raise SourceError(
                f"Unable to read Arx source file '{filename}': {error}",
                code="ARX-SOURCE-READ-001",
            ) from error

    @classmethod
    def string_to_buffer(cls, value: str) -> None:
        """
        title: Copy the given string to the buffer.
        parameters:
          value:
            type: str
            description: The string to be copied to the buffer.
        """
        validate_source_size(value)
        cls.buffer.clean()
        cls.buffer.write(value)

    @classmethod
    def load_input_to_buffer(cls) -> None:
        """
        title: Load the content file or the standard input to the buffer.
        """
        if cls.INPUT_FILE:
            input_file_path = os.path.abspath(cls.INPUT_FILE)
            cls.file_to_buffer(input_file_path)
            return

        file_content = sys.stdin.read().strip()
        if file_content:
            cls.string_to_buffer(file_content)


class ArxFile:
    """
    title: ArxFile gathers function to handle files.
    """

    @staticmethod
    def create_tmp_file(content: str) -> str:
        """
        title: Create a temporary file with the given content.
        parameters:
          content:
            type: str
            description: The content of the temporary file.
        returns:
          type: str
          description: The name of the created temporary file.
        """
        # Create a temporary file.
        with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
            tmpfile.write(content.encode())

        # Rename the temporary file with the .cpp extension.
        filename = tmpfile.name
        filename_ext = filename + ".cpp"
        os.rename(filename, filename_ext)

        return filename_ext

    @staticmethod
    def delete_file(filename: str) -> int:
        """
        title: Delete the specified file.
        parameters:
          filename:
            type: str
            description: The name of the file to be deleted.
        returns:
          type: int
          description: Returns 0 on success, or -1 on failure.
        """
        try:
            os.remove(filename)
            return 0
        except OSError:
            return -1
