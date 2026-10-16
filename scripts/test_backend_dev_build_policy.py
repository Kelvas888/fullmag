"""Exercise build policy without compiling Rust or CUDA unit tests."""
from pathlib import Path
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[1]
MACRO = "FULLMAG_FDM_GPU_TRANSPORT_BUILD_DIGEST_HEX"


def test_backend_dev_keeps_incremental_compilation_and_optimized_cpu_kernels():
    workspace = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
    profile = workspace["profile"]["backend-dev"]
    assert profile["inherits"] == "dev"
    assert profile["incremental"] is True
    assert profile["lto"] == "off"
    assert profile["opt-level"] == 1
    assert profile["package"]["fullmag-engine"]["opt-level"] == 3
    assert profile["package"]["fullmag-fdm-demag"]["opt-level"] == 3


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="The extracted Makefile recipe is a Linux-container regression",
)
def test_install_cli_dev_pins_fdm_package_to_explicit_native_root():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    start = makefile.index('\tif [ -n "$${FULLMAG_FDM_NATIVE_BUILD_ROOT:-}" ]; then')
    end = makefile.index('\tif [ "$$build_mode"', start)
    # Execute the recipe fragment itself after undoing Make's dollar escaping.
    recipe = makefile[start:end].replace("$$", "$")

    def run_fragment(case_root, configured_root=None, create_destination=True):
        (case_root / ".fullmag/local").mkdir(parents=True, exist_ok=True)
        if create_destination:
            (case_root / ".fullmag/local/lib").mkdir()
        environment = os.environ.copy()
        environment.pop("FULLMAG_FDM_NATIVE_BUILD_ROOT", None)
        if configured_root is not None:
            environment["FULLMAG_FDM_NATIVE_BUILD_ROOT"] = str(configured_root)
        script = "\n".join(
            (
                "set -eu",
                f"cargo_target_dir={shlex.quote(str(case_root / 'cargo-target'))}",
                recipe,
            )
        )
        return subprocess.run(
            ["bash", "-c", script],
            cwd=case_root,
            env=environment,
            capture_output=True,
            text=True,
        )

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        selected_case = root / "selected"
        selected = selected_case / "native/backends/fdm/libfullmag_fdm.so.1"
        selected.parent.mkdir(parents=True)
        selected.write_text("selected", encoding="utf-8")
        foreign = selected_case / "cargo-target/release/build/fullmag-fdm-sys-new/out/native-build/backends/fdm/libfullmag_fdm.so.9"
        foreign.parent.mkdir(parents=True)
        foreign.write_text("foreign", encoding="utf-8")

        result = run_fragment(selected_case, selected_case / "native")
        assert result.returncode == 0, result.stderr
        assert (selected_case / ".fullmag/local/lib/libfullmag_fdm.so.1").read_text(encoding="utf-8") == "selected"

        missing_case = root / "missing"
        missing_result = run_fragment(missing_case, missing_case / "does-not-exist")
        assert missing_result.returncode == 2
        assert "no regular libfullmag_fdm.so*" in missing_result.stderr

        relative_case = root / "relative"
        relative_result = run_fragment(relative_case, Path("relative-root"))
        assert relative_result.returncode == 2
        assert "must be absolute" in relative_result.stderr

        copy_failure_case = root / "copy-failure"
        copy_failure_selected = copy_failure_case / "native/backends/fdm/libfullmag_fdm.so.1"
        copy_failure_selected.parent.mkdir(parents=True)
        copy_failure_selected.write_text("selected", encoding="utf-8")
        (copy_failure_case / ".fullmag/local").mkdir(parents=True)
        (copy_failure_case / ".fullmag/local/lib").write_text("destination-is-not-a-directory", encoding="utf-8")
        copy_failure = run_fragment(
            copy_failure_case,
            copy_failure_case / "native",
            create_destination=False,
        )
        assert copy_failure.returncode == 2
        assert "Failed to copy FDM library" in copy_failure.stderr


@pytest.mark.skipif(not shutil.which("cmake"), reason="CMake required")
def test_cuda_source_digest_changes_only_its_consumer_compile_definition(tmp_path):
    source = (ROOT / "backends/fdm/CMakeLists.txt").read_text(encoding="utf-8")
    commands = re.findall(
        r"(?:target_compile_definitions\(fullmag_fdm PRIVATE|"
        r"set_property\(SOURCE gpu/cuda/transport/context\.cu)"
        r"[^)]*FULLMAG_FDM_GPU_TRANSPORT_BUILD_DIGEST_HEX[^)]*\)",
        source,
    )
    assert len(commands) == 1, "Expected one owning build-digest definition"
    script = tmp_path / "CMakeLists.txt"
    # A language-free configure inspects source properties without detecting
    # a compiler, CUDA toolkit, compiling, or linking any executable.
    script.write_text('''
cmake_minimum_required(VERSION 3.20)
project(FullmagBuildIdentityScope LANGUAGES NONE)
function(target_compile_definitions target)
  set_property(GLOBAL PROPERTY old_target_definitions "${ARGN}")
endfunction()
set(FDM_GPU_TRANSPORT_BUILD_DIGEST "''' + "a" * 64 + '''")
''' + commands[0] + '''
get_source_file_property(context_defs gpu/cuda/transport/context.cu COMPILE_DEFINITIONS)
get_source_file_property(exchange_defs gpu/cuda/interactions/exchange_fp64.cu COMPILE_DEFINITIONS)
get_property(target_defs GLOBAL PROPERTY old_target_definitions)
if(NOT context_defs MATCHES "''' + MACRO + '''=.*aaaaaaaa")
  message(FATAL_ERROR "Digest must be available to its context.cu consumer")
endif()
if(exchange_defs MATCHES "''' + MACRO + '''" OR target_defs MATCHES "''' + MACRO + '''")
  message(FATAL_ERROR "Digest must not invalidate unrelated translation units")
endif()
set(FDM_GPU_TRANSPORT_BUILD_DIGEST "''' + "b" * 64 + '''")
''' + commands[0] + '''
get_source_file_property(changed_defs gpu/cuda/transport/context.cu COMPILE_DEFINITIONS)
if(NOT changed_defs MATCHES "''' + MACRO + '''=.*bbbbbbbb")
  message(FATAL_ERROR "Changed source identity was not published to its consumer")
endif()
''', encoding="utf-8")
    result = subprocess.run(["cmake", "-S", str(tmp_path), "-B", str(tmp_path / "build")],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    # Adding another consumer requires updating the production owner and this
    # scope gate, rather than silently restoring a target-wide compiler flag.
    consumers = [p for p in (ROOT / "backends/fdm").rglob("*")
                 if p.suffix in (".cu", ".cpp", ".hpp", ".h")
                 and MACRO in p.read_text(encoding="utf-8")]
    assert consumers == [ROOT / "backends/fdm/gpu/cuda/transport/context.cu"]
