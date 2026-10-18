"""
title: External native package configuration, origins, linking, and lifetimes.
"""

from __future__ import annotations

import shutil
import subprocess

from pathlib import Path

import pytest

from arx.native_packages import package_path
from arx.settings import (
    ArxProjectError,
    dump_settings,
    load_settings,
    load_settings_from_text,
)
from arxpy import ArtifactKind, CompileError, Compiler
from irx.builder.runtime.registry import get_default_runtime_feature_registry
from irx.diagnostics import DiagnosticCodes
from llvmlite import binding as llvm

FIXTURE = Path(__file__).parents[1] / "fixtures" / "native-package"
DOC = "```\ntitle: Native dependency consumer\n```\n"
BODY = """import Resource from native_fixture.owned
import native_fixture.bridge as bridge
fn exercise() -> i32:
  var resource: Resource = Resource(size=2)
  var alias: Resource = resource
  assert alias.note(label="Unicode π", value=cast(2, f64)) == 0
  assert resource.write(path="result.jpg") == 0
  assert resource.write(kind=1, path="result.bin") == 0
  assert resource.write(kind=2, path="invalid") == 2
  assert bridge.fixture_alive() == 1
  return 0
fn main() -> i32:
  assert bridge.fixture_create(size=0) == 0
  assert exercise() == 0
  assert bridge.fixture_alive() == 0
  assert bridge.fixture_releases() == 1
  var token: i64 = bridge.fixture_create(size=1)
  assert bridge.fixture_release(token=token) == 0
  assert bridge.fixture_release(token=token) == 1
  var replacement: i64 = bridge.fixture_create(size=1)
  assert replacement != token
  assert bridge.fixture_write(kind=0, path="stale.jpg", token=token) == 1
  assert bridge.fixture_release(token=replacement) == 0
  return 0
"""


def project(tmp_path: Path) -> Path:
    """
    title: Create an external package's local development tree.
    parameters:
      tmp_path:
        type: Path
    returns:
      type: Path
    """
    root = tmp_path / "package with spaces"
    shutil.copytree(FIXTURE, root)
    source = root / "src" / "main.x"
    source.write_text(DOC + BODY, encoding="utf-8")
    return source


def execute(source: Path, work: Path) -> None:
    """
    title: Check, verify LLVM, build, and run the same imported native graph.
    parameters:
      source:
        type: Path
      work:
        type: Path
    """
    if shutil.which("clang") is None:
        pytest.skip("native package execution requires clang")
    compiler = Compiler()
    checked = compiler.check(compiler.parse_file(source))
    emitted = compiler.compile(checked, kind=ArtifactKind.LLVM_IR)
    assert emitted.llvm_ir is not None
    llvm.parse_assembly(emitted.llvm_ir).verify()
    program = compiler.compile(checked, output=work / "program")
    result = compiler.run(program, cwd=work, timeout=10)
    assert result.exit_code == 0, result.stderr
    assert (work / "result.jpg").read_bytes() == (
        FIXTURE / "native" / "expected.jpg"
    ).read_bytes()
    assert (work / "result.bin").read_bytes() == bytes([0, 255, 128, 10, 13])
    assert not (work / "stale.jpg").exists()
    assert not any(
        name.startswith("package:")
        for name in get_default_runtime_feature_registry().names()
    )
    compiler.compile(
        compiler.parse_string(DOC + "fn main() -> i32:\n  return 0\n"),
        kind=ArtifactKind.LLVM_IR,
    )


def test_native_package_local_development(tmp_path: Path) -> None:
    """
    title: >-
      Local native metadata reaches analysis, kwargs, linking, and cleanup.
    parameters:
      tmp_path:
        type: Path
    """
    execute(project(tmp_path), tmp_path)


def installed_package(site: Path) -> None:
    """
    title: Install source resources and standard distribution metadata locally.
    parameters:
      site:
        type: Path
    """
    root = site / "native_resource"
    shutil.copytree(FIXTURE, root)
    metadata = site / "arx_native_fixture-0.0.0.dist-info"
    metadata.mkdir(parents=True)
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: arx-native-fixture\nVersion: 0.0.0\n"
    )
    (metadata / "RECORD").write_text(
        "\n".join(
            f"{path.relative_to(site).as_posix()},,"
            for path in site.rglob("*")
            if path.is_file()
        )
        + "\n"
    )


@pytest.mark.parametrize("transitive", [False, True])
def test_installed_native_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transitive: bool
) -> None:
    """
    title: An independent installed source distribution supplies native assets.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
      transitive:
        type: bool
    """
    site = tmp_path / "site"
    installed_package(site)
    dependency = "arx-native-fixture"
    if transitive:
        dependency = "fixture-parent"
        metadata = site / "fixture_parent-0.0.0.dist-info"
        metadata.mkdir()
        (metadata / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: fixture-parent\nVersion: 0.0.0\n"
            "Requires-Dist: arx-native-fixture\n"
        )
        (metadata / "RECORD").write_text("")
    monkeypatch.syspath_prepend(str(site))
    app = tmp_path / "app"
    app.mkdir()
    (app / ".arxproject.toml").write_text(
        f'[project]\nname="app"\nversion="0"\ndependencies=["{dependency}"]\n'
    )
    source = app / "main.x"
    source.write_text(DOC + BODY, encoding="utf-8")
    execute(source, tmp_path)


def test_native_manifest_roundtrip(tmp_path: Path) -> None:
    """
    title: Native records survive canonical settings serialization.
    parameters:
      tmp_path:
        type: Path
    """
    source = project(tmp_path)
    settings = load_settings(source.parents[1] / ".arxproject.toml")
    assert settings.native is not None
    text = dump_settings(settings)
    assert load_settings_from_text(text).native == settings.native
    assert dump_settings(load_settings_from_text(text)) == text


def test_native_library_names_reject_trailing_newline() -> None:
    """
    title: Regex end anchors must not admit newline-suffixed linker inputs.
    """
    text = (FIXTURE / ".arxproject.toml").read_text()
    text = text.replace(
        "[native.features.backend]",
        '[native.features.backend]\nlibraries=["m\\n"]',
    )
    with pytest.raises(ArxProjectError):
        load_settings_from_text(text)


def test_native_manifest_roundtrip_non_bmp_paths() -> None:
    """
    title: Native TOML paths preserve non-BMP Unicode.
    """
    text = (FIXTURE / ".arxproject.toml").read_text()
    text = text.replace("native/fixture.c", "native/📈.c")
    text = text.replace('["native"]', '["native/🎨"]')
    settings = load_settings_from_text(text)
    assert settings.native is not None
    restored = load_settings_from_text(dump_settings(settings))
    assert restored.native == settings.native
    assert dump_settings(restored) == dump_settings(settings)


@pytest.mark.parametrize(
    "replacement",
    [
        ("version = 1", "version = 2"),
        ('kind = "c_source"', 'kind = "shared_library"'),
        ('features = ["backend"]', 'features = ["unknown"]'),
        ('features = ["backend"]', 'features = ["backend", 2]'),
        ('include_dirs = ["native"]', 'include_dirs = ["native", 2]'),
        (
            "[native.features.backend]",
            '[native.features.backend]\nlibraries=["-bad"]',
        ),
        (
            "[native.features.backend]",
            '[native.features.backend]\nhook="unsafe"',
        ),
    ],
)
def test_native_invalid_configuration(replacement: tuple[str, str]) -> None:
    """
    title: Invalid native metadata fails at configuration validation.
    parameters:
      replacement:
        type: tuple[str, str]
    """
    text = (FIXTURE / ".arxproject.toml").read_text()
    with pytest.raises(ArxProjectError):
        load_settings_from_text(text.replace(*replacement))


@pytest.mark.parametrize(
    "path", ["../escape", "/absolute", "missing", "C:\\out"]
)
def test_native_paths_are_contained(tmp_path: Path, path: str) -> None:
    """
    title: Native package assets cannot escape their declaring root.
    parameters:
      tmp_path:
        type: Path
      path:
        type: str
    """
    with pytest.raises(ArxProjectError):
        package_path(tmp_path, path)


def test_native_symlink_escape(tmp_path: Path) -> None:
    """
    title: Symlink targets are checked after canonical path resolution.
    parameters:
      tmp_path:
        type: Path
    """
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.c"
    outside.write_text("/* no code */\n")
    (root / "escape.c").symlink_to(outside)
    with pytest.raises(ArxProjectError, match="escapes"):
        package_path(root, "escape.c")


def test_native_missing_artifact_is_actionable(tmp_path: Path) -> None:
    """
    title: Missing packaged assets are not silently omitted from a build.
    parameters:
      tmp_path:
        type: Path
    """
    source = project(tmp_path)
    (source.parents[1] / "native" / "fixture.c").unlink()
    with pytest.raises(CompileError) as error:
        Compiler().check(Compiler().parse_file(source))
    assert any(
        "native package input" in d.message for d in error.value.diagnostics
    )


def test_jpeg_fixture_is_decodable(tmp_path: Path) -> None:
    """
    title: Verify the fixed JPEG payload with an independent installed decoder.
    parameters:
      tmp_path:
        type: Path
    """
    decoder = shutil.which("djpeg")
    if decoder is None:
        pytest.skip(
            "optional independent JPEG fixture verification needs djpeg"
        )
    output = tmp_path / "decoded.ppm"
    subprocess.run(
        [
            decoder,
            "-outfile",
            str(output),
            str(FIXTURE / "native" / "expected.jpg"),
        ],
        check=True,
    )
    assert b"2 1" in output.read_bytes()[:40]


@pytest.mark.parametrize("kind", ["cxx_source", "object", "static_library"])
def test_native_artifact_kinds(tmp_path: Path, kind: str) -> None:
    """
    title: >-
      C++ sources and prebuilt object/archive inputs use registered linking.
    parameters:
      tmp_path:
        type: Path
      kind:
        type: str
    """
    source = project(tmp_path)
    root = source.parents[1]
    native = root / "native"
    if kind == "cxx_source":
        if shutil.which("c++") is None:
            pytest.skip("C++ native fixtures require a C++ compiler")
        target = native / "fixture.cpp"
        (native / "fixture.c").rename(target)
    else:
        compiler = shutil.which("clang")
        if compiler is None:
            pytest.skip("native fixtures require clang")
        target = native / "fixture.o"
        subprocess.run(
            [
                compiler,
                "-c",
                "-fPIC",
                str(native / "fixture.c"),
                "-o",
                str(target),
            ],
            check=True,
        )
        if kind == "static_library":
            archiver = shutil.which("ar")
            if archiver is None:
                pytest.skip("archive fixtures require ar")
            archive = native / "libfixture.a"
            subprocess.run(
                [archiver, "rcs", str(archive), str(target)], check=True
            )
            target = archive
    manifest = root / ".arxproject.toml"
    manifest.write_text(
        manifest.read_text()
        .replace('kind = "c_source"', f'kind = "{kind}"')
        .replace('path = "native/fixture.c"', f'path = "native/{target.name}"')
    )
    execute(source, tmp_path)


def test_native_root_configuration_error_is_structured(tmp_path: Path) -> None:
    """
    title: Root-module native metadata errors cross the public facade cleanly.
    parameters:
      tmp_path:
        type: Path
    """
    source = project(tmp_path)
    manifest = source.parents[1] / ".arxproject.toml"
    manifest.write_text(
        manifest.read_text().replace("version = 1", "version = 2")
    )
    compiler = Compiler()
    with pytest.raises(CompileError) as error:
        compiler.check(compiler.parse_file(source))
    assert error.value.diagnostics[0].code == "ARX-PACKAGE-NATIVE-001"


def test_native_module_must_belong_to_package(tmp_path: Path) -> None:
    """
    title: A package cannot map native privileges to another module namespace.
    parameters:
      tmp_path:
        type: Path
    """
    source = project(tmp_path)
    manifest = source.parents[1] / ".arxproject.toml"
    manifest.write_text(
        manifest.read_text().replace("native_fixture.bridge", "other.bridge")
    )
    compiler = Compiler()
    with pytest.raises(CompileError) as error:
        compiler.check(compiler.parse_file(source))
    assert "declaring package" in error.value.diagnostics[0].message


def test_local_shadow_does_not_inherit_native_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    title: >-
      A local module with the same spelling gains no installed capabilities.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    site = tmp_path / "site"
    installed_package(site)
    # These invalid assets would fail if installed capabilities leaked locally.
    (site / "native_resource" / "native" / "fixture.c").unlink()
    monkeypatch.syspath_prepend(str(site))
    app = tmp_path / "app"
    local = app / "native_fixture"
    local.mkdir(parents=True)
    (app / ".arxproject.toml").write_text(
        '[project]\nname="app"\nversion="0"\n'
        'dependencies=["arx-native-fixture"]\n'
    )
    (local / "__init__.x").write_text(DOC)
    (local / "bridge.x").write_text(DOC + "extern fixture_alive() -> i32\n")
    source = app / "main.x"
    source.write_text(
        DOC + "import fixture_alive from native_fixture.bridge\n"
        "fn main() -> i32:\n  return fixture_alive()\n"
    )
    compiler = Compiler()
    artifact = compiler.compile(
        compiler.parse_file(source), kind=ArtifactKind.LLVM_IR
    )
    assert artifact.llvm_ir is not None
    assert 'declare external i32 @"fixture_alive"()' in artifact.llvm_ir


def test_native_missing_system_library_is_a_link_error(tmp_path: Path) -> None:
    """
    title: >-
      Declared native libraries are linked explicitly, never auto-installed.
    parameters:
      tmp_path:
        type: Path
    """
    if shutil.which("clang") is None:
        pytest.skip("native package linking requires clang")
    source = project(tmp_path)
    manifest = source.parents[1] / ".arxproject.toml"
    manifest.write_text(
        manifest.read_text().replace(
            "[native.features.backend]",
            '[native.features.backend]\nlibraries=["arx_intentionally_missing_library"]',
        )
    )
    compiler = Compiler()
    with pytest.raises(CompileError) as error:
        compiler.compile(
            compiler.parse_file(source), output=tmp_path / "program"
        )
    assert any("link" in d.message for d in error.value.diagnostics)


def test_native_header_failure_is_structured(tmp_path: Path) -> None:
    """
    title: Native compiler failures retain their phase and diagnostic code.
    parameters:
      tmp_path:
        type: Path
    """
    if shutil.which("clang") is None:
        pytest.skip("native compilation requires clang")
    source = project(tmp_path)
    native = source.parents[1] / "native" / "fixture.c"
    native.write_text('#include "intentionally_missing_header.h"\n')
    compiler = Compiler()
    with pytest.raises(CompileError) as error:
        compiler.compile(
            compiler.parse_file(source), output=tmp_path / "program"
        )
    assert any(
        d.code == DiagnosticCodes.NATIVE_COMPILE_FAILED
        for d in error.value.diagnostics
    )


def test_native_package_cli_build_and_run(tmp_path: Path) -> None:
    """
    title: >-
      Ordinary CLI consumers can build native dependencies without patches.
    parameters:
      tmp_path:
        type: Path
    """
    command = shutil.which("arx")
    if command is None or shutil.which("clang") is None:
        pytest.skip("native CLI smoke requires arx and clang")
    source = project(tmp_path)
    result = subprocess.run(
        [
            command,
            str(source),
            "--output-file",
            str(tmp_path / "cli-program"),
            "--run",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "result.jpg").read_bytes() == (
        FIXTURE / "native" / "expected.jpg"
    ).read_bytes()
