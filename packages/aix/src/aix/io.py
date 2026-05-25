"""
title: AIX compiler input buffer helpers.
"""

from __future__ import annotations

import os
import sys
import tempfile


class AixBuffer:
    """
    title: Shared source buffer used by lexer and CLI flows.
    attributes:
      buffer:
        type: str
      position:
        type: int
    """

    buffer: str
    position: int

    def __init__(self) -> None:
        """
        title: Initialize the buffer.
        """
        self.clean()

    def clean(self) -> None:
        """
        title: Reset buffer content and cursor.
        """
        self.buffer = ""
        self.position = 0

    def write(self, text: str) -> None:
        """
        title: Replace buffer content.
        parameters:
          text:
            type: str
        """
        self.buffer = text
        self.position = 0

    def read(self) -> str:
        """
        title: Return the next buffered character or EOF marker.
        returns:
          type: str
        """
        if self.position >= len(self.buffer):
            return ""
        char = self.buffer[self.position]
        self.position += 1
        return char


class AixIO:
    """
    title: AIX input loading facade.
    attributes:
      INPUT_FROM_STDIN:
        type: bool
      INPUT_FILE:
        type: str
      EOF:
        type: int
      buffer:
        type: AixBuffer
    """

    INPUT_FROM_STDIN: bool = False
    INPUT_FILE: str = ""
    EOF: int = sys.maxunicode + 1
    buffer: AixBuffer = AixBuffer()

    @classmethod
    def get_char(cls) -> str:
        """
        title: Return one character from stdin or the shared buffer.
        returns:
          type: str
        """
        if cls.INPUT_FROM_STDIN:
            return sys.stdin.read(1)
        return cls.buffer.read()

    @classmethod
    def file_to_buffer(cls, filename: str) -> None:
        """
        title: Load one source file into the shared buffer.
        parameters:
          filename:
            type: str
        """
        with open(filename, encoding="utf-8") as aix_file:
            cls.buffer.clean()
            cls.buffer.write(aix_file.read())

    @classmethod
    def string_to_buffer(cls, value: str) -> None:
        """
        title: Load one source string into the shared buffer.
        parameters:
          value:
            type: str
        """
        cls.buffer.clean()
        cls.buffer.write(value)

    @classmethod
    def load_input_to_buffer(cls) -> None:
        """
        title: Load configured file or stdin into the shared buffer.
        """
        if cls.INPUT_FILE:
            input_file_path = os.path.abspath(cls.INPUT_FILE)
            cls.file_to_buffer(input_file_path)
            return

        file_content = sys.stdin.read().strip()
        if file_content:
            cls.string_to_buffer(file_content)


class AixFile:
    """
    title: Temporary file helpers used by backend flows.
    """

    @staticmethod
    def create_tmp_file(content: str) -> str:
        """
        title: Create a temporary C++ file with given content.
        parameters:
          content:
            type: str
        returns:
          type: str
        """
        with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
            tmpfile.write(content.encode())

        filename = tmpfile.name
        filename_ext = filename + ".cpp"
        os.rename(filename, filename_ext)
        return filename_ext

    @staticmethod
    def delete_file(filename: str) -> int:
        """
        title: Delete one file if present.
        parameters:
          filename:
            type: str
        returns:
          type: int
        """
        try:
            os.remove(filename)
            return 0
        except OSError:
            return -1


ArxBuffer = AixBuffer
ArxIO = AixIO
ArxFile = AixFile
