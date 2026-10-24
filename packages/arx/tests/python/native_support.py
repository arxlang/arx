"""
title: Session-local reuse of native objects in compiled Arx tests.
"""

import hashlib
import os
import shutil
import subprocess
import tempfile

from collections.abc import Callable
from pathlib import Path

from irx.builder.runtime import linking
from irx.native import NativeArtifact
from public import private


@private
class NativeObjectCache:
    """
    title: Reuse immutable runtime objects within one test process.
    summary: >-
      Only sources under source_root with simple runtime flags are cached. Each
      lookup preprocesses all headers and keys the result by compiler identity,
      flags, working directory and environment. The installed toolchain must
      remain unchanged during a session. Unusual flags and preprocessing
      failures take the original compiler path. Fresh build directories prevent
      failed or concurrent builds from publishing partial objects; no entries
      survive into another test session.
    attributes:
      directory:
        type: Path
      source_root:
        type: Path
      compile_source:
        type: Callable[[NativeArtifact, Path, str], Path]
      objects:
        type: dict[str, Path]
    """

    def __init__(self, directory: Path, source_root: Path) -> None:
        """
        title: Capture the original compiler and an isolated cache directory.
        parameters:
          directory:
            type: Path
          source_root:
            type: Path
        """
        self.directory: Path = directory
        self.source_root: Path = source_root.resolve()
        self.compile_source: Callable[[NativeArtifact, Path, str], Path] = (
            linking._compile_native_source
        )
        self.objects: dict[str, Path] = {}

    def compile(
        self, artifact: NativeArtifact, build_dir: Path, compiler_binary: str
    ) -> Path:
        """
        title: Compile once for each complete preprocessed runtime input.
        parameters:
          artifact:
            type: NativeArtifact
          build_dir:
            type: Path
          compiler_binary:
            type: str
        returns:
          type: Path
        """
        compiler = shutil.which(compiler_binary)
        if (
            compiler is None
            or not artifact.path.resolve().is_relative_to(self.source_root)
            or any(
                flag != "-fPIC" and not flag.startswith(("-std=", "-D", "-O"))
                for flag in artifact.compile_flags
            )
        ):
            return self.compile_source(artifact, build_dir, compiler_binary)

        command = [compiler, "-E", str(artifact.path), "-fPIC"]
        for include_dir in artifact.include_dirs:
            command.extend(["-I", str(include_dir)])
        command.extend(artifact.compile_flags)
        try:
            preprocessed = subprocess.run(
                command, capture_output=True, check=False
            )
        except OSError:
            return self.compile_source(artifact, build_dir, compiler_binary)
        if preprocessed.returncode:
            # Preserve the compiler's structured diagnostic on the real path.
            return self.compile_source(artifact, build_dir, compiler_binary)

        environment = sorted(
            (key, value)
            for key, value in os.environ.items()
            if key != "PYTEST_CURRENT_TEST"
        )
        compiler_stat = Path(compiler).stat()
        identity = (
            artifact,
            compiler,
            (
                compiler_stat.st_dev,
                compiler_stat.st_ino,
                compiler_stat.st_size,
                compiler_stat.st_mtime_ns,
                compiler_stat.st_ctime_ns,
            ),
            Path.cwd(),
            environment,
        )
        digest = hashlib.sha256(repr(identity).encode())
        digest.update(preprocessed.stdout)
        key = digest.hexdigest()
        if key not in self.objects:
            directory = Path(tempfile.mkdtemp(dir=self.directory))
            self.objects[key] = self.compile_source(
                artifact, directory, compiler_binary
            )
        return self.objects[key]
