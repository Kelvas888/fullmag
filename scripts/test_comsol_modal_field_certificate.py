#!/usr/bin/env python3
"""Tests for the independent COMSOL modal field certificate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "comsol_modal_field_certificate.py"


def load_module():
    spec = importlib.util.spec_from_file_location("comsol_modal_field_certificate", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def encode_vectors(vectors: list[tuple[complex, complex, complex]]) -> bytes:
    values: list[float] = []
    for vector in vectors:
        for component in vector:
            values.extend((component.real, component.imag))
    return struct.pack(f"<{len(values)}d", *values)


def write_case(
    root: Path,
    *,
    vectors: list[tuple[complex, complex, complex]],
    raw_mode_index: int = 7,
    boundary_pairs: list[dict] | None = None,
    payload_override: bytes | None = None,
) -> tuple[Path, Path]:
    case_dir = root / "case"
    vector_path = case_dir / "eigen" / "mode_fields" / "sample_0000" / f"mode_{raw_mode_index:04d}" / "vector.bin"
    mode_path = case_dir / "eigen" / "modes" / "sample_0000" / f"mode_{raw_mode_index:04d}.json"
    vector_path.parent.mkdir(parents=True)
    mode_path.parent.mkdir(parents=True)

    data = encode_vectors(vectors) if payload_override is None else payload_override
    vector_path.write_bytes(data)
    digest = f"sha256:{hashlib.sha256(data).hexdigest()}"

    if boundary_pairs is None:
        boundary_pairs = [
            {"pair_id": "x_faces", "translation": [1.0, 0.0, 0.0]},
        ]
    backend_plan = {
        "mesh": {
            "nodes": [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [1.0, 1.0, 0.0],
            ],
            "periodic_node_pairs": [
                {"pair_id": "x_faces", "node_a": 0, "node_b": 1},
                {"pair_id": "x_faces", "node_a": 2, "node_b": 3},
            ],
            "periodic_boundary_pairs": boundary_pairs,
        },
        "spin_wave_bc": {"kind": "floquet", "pair_ids": ["x_faces"]},
        "k_sampling": {
            "kind": "single",
            "vector_rad_per_m": [math.pi / 2.0, 0.0, 0.0],
        },
    }
    (case_dir / "metadata.json").write_text(
        json.dumps({"execution_plan": {"backend_plan": backend_plan}}),
        encoding="utf-8",
    )
    mode = {
        "schema_version": "eigen_mode.v2",
        "sample_index": 0,
        "raw_mode_index": raw_mode_index,
        "k_vector": [math.pi / 2.0, 0.0, 0.0],
        "source_mesh_identity": {
            "indexing": "full_domain_node_order",
            "node_count": len(vectors),
        },
        "mode_field_sample_count": len(vectors),
        "complex_pair_count": len(vectors) * 3,
        "payload_value_count": len(vectors) * 6,
        "payload_sha256": digest,
        "payload_encoding": "f64_interleaved_real_imag_xyz",
        "binary_layout": "complex_f64_pairs_little_endian",
        "component_basis": "global_xyz",
        "value_kind": "complex_spatial_vector",
        "component_count": 3,
        "compatibility_binary_payload_path": (
            f"eigen/mode_fields/sample_0000/mode_{raw_mode_index:04d}/vector.bin"
        ),
    }
    mode_path.write_text(json.dumps(mode), encoding="utf-8")
    return case_dir, vector_path


def write_full_potential(case_dir: Path, values: list[complex], *, k=None) -> tuple[Path, Path]:
    mode_path = case_dir / "eigen/modes/sample_0000/mode_0007.json"
    mode = json.loads(mode_path.read_text(encoding="utf-8"))
    if k is not None:
        mode["k_vector"] = list(k)
        metadata_path = case_dir / "metadata.json"
        native = json.loads(metadata_path.read_text(encoding="utf-8"))
        native["execution_plan"]["backend_plan"]["k_sampling"]["vector_rad_per_m"] = list(k)
        metadata_path.write_text(json.dumps(native), encoding="utf-8")
    source_identity = {
        "source_mesh_topology_sha256": "sha256:" + "1" * 64,
        "operator_input_signature_sha256": "sha256:" + "2" * 64,
        "phase_constraint_sha256": "sha256:" + "3" * 64,
    }
    mode.update(
        {
            **source_identity,
            "potential_representation": "complex_coefficients",
            "floquet_gauge_policy_satisfied": True,
            "floquet_full_descriptor_certified": True,
            "floquet_full_potential_relative_residual": 0.0,
            "gauge_constraint_backward_error": 0.0,
        }
    )
    mode_path.write_text(json.dumps(mode), encoding="utf-8")

    relative = "eigen/mode_fields/sample_0000/mode_0007/potential_full.bin"
    payload_path = case_dir / relative
    scalars = [part for value in values for part in (value.real, value.imag)]
    data = struct.pack(f"<{len(scalars)}d", *scalars)
    payload_path.write_bytes(data)
    manifest = {
        "schema_version": "fem_modal_physical_potential.v1",
        "sample_index": 0,
        "mode_index": 7,
        "representation": "full_physical_phasor",
        "phasor_convention": "exp(+i*omega*t)",
        "reconstruction": "phi_full[node] = C_phi[node,class] * phi_reduced[class]",
        "normalization": "same_complex_scale_as_published_magnetization_mode",
        **source_identity,
        "potential": {
            "path": relative,
            "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
            "dtype": "float64",
            "byte_order": "little",
            "layout": "node_major_real_imag",
            "association": "source_mesh_nodes",
            "count": len(values),
            "unit": "A",
        },
    }
    manifest_path = payload_path.parent / "physical_potential.v1.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, payload_path


def good_potential_values(k=(math.pi / 2.0, 0.0, 0.0)) -> list[complex]:
    coordinates = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (1.0, 1.0, 0.0),
    ]
    amplitude = 2.0 + 0.5j
    return [
        amplitude * complex(
            math.cos(-sum(a * b for a, b in zip(k, point))),
            math.sin(-sum(a * b for a, b in zip(k, point))),
        )
        for point in coordinates
    ]


def good_vectors() -> list[tuple[complex, complex, complex]]:
    phase = complex(0.0, -1.0)
    first = (1.0 + 2.0j, 2.0 - 1.0j, 3.0 + 0.5j)
    second = (2.0 + 0.5j, -1.0 + 1.0j, 0.25 - 2.0j)
    return [first, tuple(phase * value for value in first), second, tuple(phase * value for value in second)]


def test_good_selected_raw_mode_is_certified_and_hashes_real_files(tmp_path: Path) -> None:
    module = load_module()
    case_dir, vector_path = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)

    report = module.validate_modal_field_certificate(
        case_dir,
        mode_selections=[(0, 7)],
    )

    assert report["status"] == "pass"
    assert report["qualification"] == "QUALIFIED"
    assert report["selection_policy"] == "explicit"
    assert report["requested_modes"] == [{"sample_index": 0, "raw_mode_index": 7}]
    assert report["validated_mode_count"] == 1
    assert len(report["modes"][0]["phase_checks"]) == 2
    hashes = {item["path"]: item["sha256"] for item in report["file_hashes"]}
    assert "metadata.json" in hashes
    assert hashes["eigen/mode_fields/sample_0000/mode_0007/vector.bin"] == (
        f"sha256:{hashlib.sha256(vector_path.read_bytes()).hexdigest()}"
    )


def test_full_physical_potential_replays_phase_but_does_not_claim_gauge(tmp_path: Path) -> None:
    module = load_module()
    case_dir, _ = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)
    manifest_path, payload_path = write_full_potential(case_dir, good_potential_values())

    report = module.validate_modal_potential_phase_certificate(
        case_dir,
        mode_selections=[(0, 7)],
    )

    assert report["phase_status"] == "pass"
    assert report["gauge_status"] == "not_verified"
    assert report["status"] == "not_verified"
    assert any("gauge" in reason for reason in report["reasons"])
    hashes = {item["path"]: item["sha256"] for item in report["file_hashes"]}
    assert hashes[manifest_path.relative_to(case_dir).as_posix()] == (
        "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    )
    assert hashes[payload_path.relative_to(case_dir).as_posix()] == (
        "sha256:" + hashlib.sha256(payload_path.read_bytes()).hexdigest()
    )
    assert report["modes"][0]["phase_checks"][0]["relative_residual"] < 1.0e-8


def test_identically_zero_full_potential_is_uninformative_not_a_physics_failure(tmp_path: Path) -> None:
    module = load_module()
    case_dir, _ = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)
    write_full_potential(case_dir, [0j] * 4)

    report = module.validate_modal_potential_phase_certificate(
        case_dir,
        mode_selections=[(0, 7)],
    )

    assert report["phase_status"] == "not_verified"
    assert report["status"] == "not_verified"
    assert report["gauge_status"] == "not_verified"
    mode = report["modes"][0]
    assert mode["status"] == "not_verified"
    assert mode["phase_evidence_status"] == "uninformative"
    assert all(item["status"] == "not_verified" for item in mode["phase_checks"])
    assert any("physically possible but provides no phase evidence" in reason for reason in report["reasons"])
    assert not any("phase residual" in reason for reason in report["reasons"])


def test_zero_periodic_trace_with_nonzero_interior_is_unverified(tmp_path: Path) -> None:
    module = load_module()
    case_dir, _ = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)
    interior = 2.0 + 0.5j
    values = [0j, 0j, interior, complex(0.0, -1.0) * interior]
    write_full_potential(case_dir, values)

    report = module.validate_modal_potential_phase_certificate(
        case_dir,
        mode_selections=[(0, 7)],
    )

    assert report["phase_status"] == "not_verified"
    assert report["status"] == "not_verified"
    mode = report["modes"][0]
    assert mode["status"] == "not_verified"
    assert mode["informative_pair_count"] == 1
    assert [item["phase_validation"] for item in mode["phase_checks"]] == [
        "vacuous_zero_trace",
        "checked",
    ]
    assert mode["phase_checks"][0]["status"] == "not_verified"
    assert mode["phase_checks"][1]["status"] == "pass"
    assert any("zero periodic trace" in reason and "uninformative" in reason for reason in report["reasons"])
    assert not any("potential phase residual" in reason for reason in report["reasons"])


def test_rehashed_wrong_full_potential_phase_is_rejected(tmp_path: Path) -> None:
    module = load_module()
    case_dir, _ = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)
    values = good_potential_values()
    values[1] += 0.1
    write_full_potential(case_dir, values)

    report = module.validate_modal_potential_phase_certificate(
        case_dir,
        mode_selections=[(0, 7)],
    )

    assert report["phase_status"] == "fail"
    assert report["status"] == "fail"
    assert any("potential phase residual" in reason for reason in report["reasons"])


@pytest.mark.parametrize(
    "identity_key",
    (
        "source_mesh_topology_sha256",
        "operator_input_signature_sha256",
        "phase_constraint_sha256",
    ),
)
def test_full_potential_manifest_identities_must_match_selected_mode(
    tmp_path: Path, identity_key: str
) -> None:
    module = load_module()
    case_dir, _ = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)
    manifest_path, _ = write_full_potential(case_dir, good_potential_values())
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[identity_key] = "sha256:" + "4" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = module.validate_modal_potential_phase_certificate(
        case_dir,
        mode_selections=[(0, 7)],
    )

    assert report["phase_status"] == "fail"
    assert report["status"] == "fail"
    assert any(identity_key in reason and "differs" in reason for reason in report["reasons"])


def test_full_potential_manifest_sample_and_mode_must_match_selection(tmp_path: Path) -> None:
    module = load_module()
    case_dir, _ = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)
    manifest_path, _ = write_full_potential(case_dir, good_potential_values())
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["mode_index"] = 8
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = module.validate_modal_potential_phase_certificate(
        case_dir,
        mode_selections=[(0, 7)],
    )

    assert report["status"] == "fail"
    assert any("sample/mode identity" in reason for reason in report["reasons"])


def test_full_potential_bytes_require_exact_size_and_manifest_hash(tmp_path: Path) -> None:
    module = load_module()
    case_dir, _ = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)
    _, payload_path = write_full_potential(case_dir, good_potential_values())
    payload_path.write_bytes(payload_path.read_bytes() + b"\x00")

    report = module.validate_modal_potential_phase_certificate(
        case_dir,
        mode_selections=[(0, 7)],
    )

    assert report["status"] == "fail"
    assert any("length" in reason and "expected" in reason for reason in report["reasons"])
    assert any("SHA-256 does not match" in reason for reason in report["reasons"])


def test_nonfinite_derived_potential_magnitude_cannot_pass_phase(tmp_path: Path) -> None:
    module = load_module()
    case_dir, _ = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)
    write_full_potential(
        case_dir,
        [complex(1.7e308, 1.7e308)] * 4,
    )

    report = module.validate_modal_potential_phase_certificate(
        case_dir,
        mode_selections=[(0, 7)],
    )

    assert report["phase_status"] == "fail"
    assert report["status"] == "fail"
    assert any("non-finite derived magnitude" in reason for reason in report["reasons"])


def test_gamma_constant_potential_and_true_native_flags_do_not_prove_gauge(tmp_path: Path) -> None:
    module = load_module()
    case_dir, _ = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)
    write_full_potential(
        case_dir,
        [3.0 + 2.0j] * 4,
        k=(0.0, 0.0, 0.0),
    )

    report = module.validate_modal_potential_phase_certificate(
        case_dir,
        mode_selections=[(0, 7)],
    )

    assert report["phase_status"] == "pass"
    assert report["gauge_status"] == "not_verified"
    assert report["status"] == "not_verified"
    assert any("gauge" in reason for reason in report["reasons"])


def test_full_potential_requires_complete_shared_domain_pair_coverage(tmp_path: Path) -> None:
    module = load_module()
    case_dir, _ = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)
    metadata_path = case_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    mesh = metadata["execution_plan"]["backend_plan"]["mesh"]
    mesh["periodic_node_pairs"].extend(
        [
            {"pair_id": "y_faces", "node_a": 0, "node_b": 2},
            {"pair_id": "y_faces", "node_a": 1, "node_b": 3},
        ]
    )
    mesh["periodic_boundary_pairs"].append(
        {"pair_id": "y_faces", "translation": [0.0, 1.0, 0.0]}
    )
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    write_full_potential(case_dir, good_potential_values())

    report = module.validate_modal_potential_phase_certificate(
        case_dir,
        mode_selections=[(0, 7)],
    )

    assert report["status"] == "fail"
    assert any("requires every periodic node-pair ID" in reason for reason in report["reasons"])


def test_full_potential_replays_every_shared_domain_pair(tmp_path: Path) -> None:
    module = load_module()
    case_dir, _ = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)
    metadata_path = case_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    backend_plan = metadata["execution_plan"]["backend_plan"]
    mesh = backend_plan["mesh"]
    mesh["periodic_node_pairs"].extend(
        [
            {"pair_id": "y_faces", "node_a": 0, "node_b": 2},
            {"pair_id": "y_faces", "node_a": 1, "node_b": 3},
        ]
    )
    mesh["periodic_boundary_pairs"].append(
        {"pair_id": "y_faces", "translation": [0.0, 1.0, 0.0]}
    )
    backend_plan["spin_wave_bc"]["pair_ids"] = ["x_faces", "y_faces"]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    k = (math.pi / 2.0, math.pi / 3.0, 0.0)
    write_full_potential(case_dir, good_potential_values(k), k=k)

    report = module.validate_modal_potential_phase_certificate(
        case_dir,
        mode_selections=[(0, 7)],
    )

    assert report["phase_status"] == "pass"
    assert len(report["modes"][0]["phase_checks"]) == 4
    assert {item["pair_id"] for item in report["modes"][0]["phase_checks"]} == {
        "x_faces",
        "y_faces",
    }


def test_wrong_phase_on_second_shared_domain_pair_is_rejected(tmp_path: Path) -> None:
    module = load_module()
    case_dir, _ = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)
    metadata_path = case_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    backend_plan = metadata["execution_plan"]["backend_plan"]
    mesh = backend_plan["mesh"]
    mesh["periodic_node_pairs"].extend(
        [
            {"pair_id": "y_faces", "node_a": 0, "node_b": 2},
            {"pair_id": "y_faces", "node_a": 1, "node_b": 3},
        ]
    )
    mesh["periodic_boundary_pairs"].append(
        {"pair_id": "y_faces", "translation": [0.0, 1.0, 0.0]}
    )
    backend_plan["spin_wave_bc"]["pair_ids"] = ["x_faces", "y_faces"]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    k = (math.pi / 2.0, math.pi / 3.0, 0.0)
    values = good_potential_values(k)
    values[2] += 0.1
    values[3] = complex(0.0, -1.0) * values[2]
    write_full_potential(case_dir, values, k=k)

    report = module.validate_modal_potential_phase_certificate(
        case_dir,
        mode_selections=[(0, 7)],
    )

    assert report["phase_status"] == "fail"
    assert any("potential phase residual for pair y_faces" in reason for reason in report["reasons"])
    assert not any("potential phase residual for pair x_faces" in reason for reason in report["reasons"])


def test_real_split_coefficients_do_not_substitute_for_full_physical_potential(tmp_path: Path) -> None:
    module = load_module()
    case_dir, _ = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)
    split_path = case_dir / "eigen/mode_fields/sample_0000/mode_0007/potential_real_split.bin"
    split_path.write_bytes(b"coefficient payload is not a full nodal field")
    mode_path = case_dir / "eigen/modes/sample_0000/mode_0007.json"
    mode = json.loads(mode_path.read_text(encoding="utf-8"))
    mode.update(
        potential_representation="doubled_real_split_complex_coefficients",
        potential_payload_path=split_path.relative_to(case_dir).as_posix(),
    )
    mode_path.write_text(json.dumps(mode), encoding="utf-8")

    report = module.validate_modal_potential_phase_certificate(
        case_dir,
        mode_selections=[(0, 7)],
    )

    assert report["status"] == "not_verified"
    assert report["phase_status"] == "not_verified"
    assert any("physical potential manifest" in reason for reason in report["reasons"])


def test_zero_endpoint_pair_is_vacuous_when_group_has_informative_pair(tmp_path: Path) -> None:
    module = load_module()
    vectors = good_vectors()
    vectors[2] = (0j, 0j, 0j)
    vectors[3] = (0j, 0j, 0j)
    case_dir, _ = write_case(tmp_path, vectors=vectors)

    report = module.validate_modal_field_certificate(case_dir, mode_selections=[(0, 7)])

    assert report["status"] == "pass"
    assert report["modes"][0]["phase_checks"][1]["phase_validation"] == "vacuous_zero_field"
    assert report["modes"][0]["pair_group_status"] == {
        "x_faces": "qualified_informative_field"
    }


def test_wrong_phase_is_rejected_from_vector_bytes(tmp_path: Path) -> None:
    module = load_module()
    vectors = good_vectors()
    vectors[1] = (vectors[1][0] + 0.1, vectors[1][1], vectors[1][2])
    case_dir, _ = write_case(tmp_path, vectors=vectors)

    report = module.validate_modal_field_certificate(case_dir, mode_selections=[(0, 7)])

    assert report["status"] == "fail"
    assert any("phase residual" in reason for reason in report["reasons"])


def test_missing_boundary_pair_id_fails_closed(tmp_path: Path) -> None:
    module = load_module()
    case_dir, _ = write_case(tmp_path, vectors=good_vectors(), boundary_pairs=[])

    report = module.validate_modal_field_certificate(case_dir, mode_selections=[(0, 7)])

    assert report["status"] == "fail"
    assert "x_faces" in report["pair_contract"]["missing_pair_ids"]
    assert any("absent from periodic_boundary_pairs" in reason for reason in report["reasons"])


def test_identically_zero_field_is_not_a_certificate(tmp_path: Path) -> None:
    module = load_module()
    zero = [(0j, 0j, 0j) for _ in range(4)]
    case_dir, _ = write_case(tmp_path, vectors=zero)

    report = module.validate_modal_field_certificate(case_dir, mode_selections=[(0, 7)])

    assert report["status"] == "fail"
    assert any("identically zero" in reason for reason in report["reasons"])


def test_nonfinite_field_is_rejected(tmp_path: Path) -> None:
    module = load_module()
    vectors = good_vectors()
    vectors[0] = (complex(float("nan"), 0.0), vectors[0][1], vectors[0][2])
    case_dir, _ = write_case(tmp_path, vectors=vectors)

    report = module.validate_modal_field_certificate(case_dir, mode_selections=[(0, 7)])

    assert report["status"] == "fail"
    assert any("non-finite" in reason for reason in report["reasons"])


def test_wrong_payload_length_is_rejected(tmp_path: Path) -> None:
    module = load_module()
    data = encode_vectors(good_vectors())[:-8]
    case_dir, _ = write_case(tmp_path, vectors=good_vectors(), payload_override=data)

    report = module.validate_modal_field_certificate(case_dir, mode_selections=[(0, 7)])

    assert report["status"] == "fail"
    assert any("length" in reason for reason in report["reasons"])


def test_missing_explicit_mode_selection_does_not_scan_another_raw_mode(tmp_path: Path) -> None:
    module = load_module()
    case_dir, _ = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)

    report = module.validate_modal_field_certificate(case_dir, mode_selections=[(0, 99)])

    assert report["status"] == "fail"
    assert report["mode_count"] == 0
    assert any("selected mode (0, 99) metadata is missing" in reason for reason in report["reasons"])



@pytest.mark.parametrize("trace_amplitude", [0.0, 1e-100])
def test_nonzero_interior_mode_with_zero_or_roundoff_sized_trace_is_valid(tmp_path, trace_amplitude):
    module = load_module()
    vectors = [(complex(trace_amplitude), 0j, 0j)] * 4 + [(1+0j, 0j, 0j)]
    case_dir, _ = write_case(tmp_path, vectors=vectors)
    path = case_dir / "metadata.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["execution_plan"]["backend_plan"]["mesh"]["nodes"].append([0.5, 0.5, 0.0])
    path.write_text(json.dumps(metadata), encoding="utf-8")
    report = module.validate_modal_field_certificate(case_dir, mode_selections=[(0, 7)])
    assert report["status"] == "pass", report["reasons"]
    assert report["modes"][0]["phase_checks"][0]["relative_residual"] < 1e-8


@pytest.mark.parametrize("pair_ids", [[], None, "x_faces", [""]])
def test_explicit_invalid_pair_ids_cannot_select_all_mesh_pairs(tmp_path, pair_ids):
    root, _ = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)
    path = root / "metadata.json"
    metadata = json.loads(path.read_text())
    contract = metadata["execution_plan"]["backend_plan"]["spin_wave_bc"]
    contract["pair_ids"] = pair_ids
    contract["boundary_pair_id"] = "x_faces"
    path.write_text(json.dumps(metadata))
    report = load_module().validate_modal_field_certificate(root, mode_selections=[(0, 7)])
    assert report["status"] == "fail"
    assert report["pair_contract"]["requested_pair_ids"] == []
    assert any("pair_ids" in reason for reason in report["reasons"])


@pytest.mark.parametrize("other_path", [
    "eigen/mode_fields/sample_0000/mode_0008/vector.bin",
    "eigen/mode_fields/sample_0001/mode_0007/vector.bin",
])
def test_payload_cannot_be_borrowed_from_another_mode(tmp_path, other_path):
    root, payload = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)
    borrowed = root / other_path
    borrowed.parent.mkdir(parents=True, exist_ok=True)
    borrowed.write_bytes(payload.read_bytes())
    path = root / "eigen/modes/sample_0000/mode_0007.json"
    metadata = json.loads(path.read_text())
    metadata["compatibility_binary_payload_path"] = other_path
    path.write_text(json.dumps(metadata))
    report = load_module().validate_modal_field_certificate(root, mode_selections=[(0, 7)])
    assert report["status"] == "fail"
    assert any("payload path does not match" in reason for reason in report["reasons"])


@pytest.mark.parametrize("relative_escape", [False, True])
def test_external_native_metadata_cannot_certify_a_case(tmp_path, relative_escape):
    root, _ = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)
    external = tmp_path / "borrowed-metadata.json"
    external.write_bytes((root / "metadata.json").read_bytes())
    selected = root / ".." / external.name if relative_escape else external
    report = load_module().validate_modal_field_certificate(
        root, mode_selections=[(0, 7)], metadata_path=selected
    )
    assert report["status"] == "fail"
    assert report["qualification"] == "NOT VERIFIED"
    assert report["file_hashes"] == []
    assert any("native metadata.json" in reason for reason in report["reasons"])


def test_explicit_in_case_native_metadata_remains_accepted(tmp_path):
    root, _ = write_case(tmp_path, vectors=good_vectors(), raw_mode_index=7)
    report = load_module().validate_modal_field_certificate(
        root, mode_selections=[(0, 7)], metadata_path=root / "metadata.json"
    )
    assert report["status"] == "pass", report["reasons"]
    assert "metadata.json" in {record["path"] for record in report["file_hashes"]}
