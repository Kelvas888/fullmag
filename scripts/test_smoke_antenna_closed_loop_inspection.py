"""Synthetic metadata fixtures; no native or scientific qualification."""
import unittest

from smoke_antenna_closed_loop_inspection import validate_resource
from smoke_antenna_external_lead_inspection import SmokeError


def resource(sample_cells=24, target_count=14, source_cells=1867):
    digest = "sha256:" + "b" * 64
    source = {
        "digest_encoding": "canonical_named_fields_be_bits.v2",
        "periodic_operator_version": "fem_charge_h1_periodic_jump.v2",
        "closure_operator_version": "fem_closed_current_geometry.v2",
        "conservative_current_operator_version": "fem_conservative_current_rt0_view.v1",
        "weak_reaction_ledger_version": "original_k_paired_vertex_reactions.v2",
        "sampling_policy": "cell_center_and_cell_local_vertices.v1",
        "source_current_orientation": "authored_minus_outward.v1",
        **{key: "a" * 64 for key in (
            "prepared_execution_digest", "accepted_charge_field_digest",
            "accepted_source_state_digest", "view_identity_digest",
            "current_balance_certificate_digest")},
        "source_current_a": 0.1, "source_absolute_flux_a": 0.1,
        "potential_jump_v": 0.25, "measured_potential_jump_v": 0.25,
        "gauge_mean_v": 0.0, "charge_relative_residual": 1e-15,
        "max_paired_weak_flux_mismatch_a": 0.0,
        "terminal_observation_currents": {},
    }
    n, c, t, h, f, w = 678, source_cells, target_count, sample_cells, 4 * source_cells, 2
    specs = {
        "stable_vertex_ids": ("node_u64_le", "1", n * 8),
        "vertex_xyz": ("node_xyz_f64_le", "m", n * 24),
        "sample_xyz": ("sample_xyz_f64_le", "m", t * 24),
        "sample_cells": ("sample_tet4_u32_le", "1", h * 16),
        "conductivity": ("cell_f64_le", "S/m", c * 8),
        "v_raw": ("node_f64_le", "V", n * 8),
        "v_per_a": ("node_f64_le", "V/A", n * 8),
        "j_center_raw": ("cell_xyz_f64_le", "A/m^2", c * 24),
        "j_center_per_a": ("cell_xyz_f64_le", "1/m^2", c * 24),
        "j_local_raw": ("cell_local4_xyz_f64_le", "A/m^2", c * 96),
        "j_local_per_a": ("cell_local4_xyz_f64_le", "1/m^2", c * 96),
        "h_raw": ("sample_xyz_f64_le", "A/m", t * 24),
        "h_per_a": ("sample_xyz_f64_le", "1/m", t * 24),
        "cells": ("closed_loop_cell280_le", "SI", c * 280),
        "faces": ("face_u64x3_f64_le", "A", f * 32),
        "weak": ("paired_u64x2_f64x2_le", "A", w * 32),
        **{key: ("canonical_named_fields_be_bits.v2", "1", 1) for key in (
            "prepared_preimage", "charge_preimage", "source_preimage")},
        "certificate": ("canonical_balance_certificate.v1", "1", 1),
        "authoring_receipt": ("utf8_json_input.v1", "1", 1),
        "direct_evidence": ("fem_direct_oersted_evidence.v2", "SI", 296 + t * 96),
    }
    manifest = {
        "schema_version": "antenna_field_solution.v2", "status": "inspection_only",
        "validation_scope": "full_cold_bundle", "qualification": "NOT VERIFIED",
        "field_scope": "full_closed_loop.inspection_only.v2",
        "content_digest": digest, "solution_id": "output", "stage_id": "inspect_loop",
        "port_mode_id": "port", "source_object_id": "antenna",
        "current_transport_id": "transport", "sample_carrier": {},
        "requested_intent": {}, "resolved_execution": {}, "source": source,
        "signed_normalization_a": 0.1, "scale_per_a": 10.0,
        "vertex_count": n, "cell_count": c, "target_count": t,
        "sample_cell_count": h, "face_count": f, "weak_reaction_count": w,
        "payloads": {
            key: {"path": f"antenna/field_solutions/output/{key}.bin",
                  "sha256": "c" * 64, "byte_length": size, "layout": layout, "unit": unit}
            for key, (layout, unit, size) in specs.items()
        },
    }
    return {
        "runtime_stage_id": "runtime-stage",
        "resource_id": "data/antenna/stages/runtime-stage/external-lead-inspection",
        **{key: "owner" for key in (
            "session_id", "session_epoch", "request_scope_epoch", "run_id")},
        "stage_id": "inspect_loop", "output_id": "output", "port_mode_id": "port",
        "source_object_id": "antenna", "stage_revision": 1,
        "record_content_digest": "sha256:" + "d" * 64,
        "schema_version": "antenna_closed_loop_stage_output.v2",
        "stage_kind": "antenna_field_solve", "resolved_action": "closed_loop_inspection",
        "status": "inspection_only", "qualification": "NOT VERIFIED",
        "field_scope": "full_closed_loop.inspection_only.v2",
        "closed_loop_manifest": manifest,
        "outputs": [{
            "inspection_ref": {"stage_id": "inspect_loop", "output_id": "output",
                               "content_digest": digest},
            "content_digest": digest, "kind": "antenna_closed_loop_inspection",
            "manifest_ref": "antenna/field_solutions/output/manifest.v2.json",
            "payload_units": {"V_electric": "V", "J_charge": "A/m^2", "H_ant": "A/m",
                              "H_ant_per_a": "1/m", "positions": "m"},
            "source": source,
        }],
    }


class ClosedLoopMetadataBoundsTests(unittest.TestCase):
    def test_accepts_legacy_and_independent_universe_carriers(self):
        for cells, targets in ((24, 14), (6487, 1154), (16384, 1154)):
            with self.subTest(sample_cells=cells):
                value = resource(sample_cells=cells, target_count=targets)
                manifest, digest = validate_resource(value, "runtime-stage")
                self.assertIs(manifest, value["closed_loop_manifest"])
                self.assertEqual(digest, manifest["content_digest"])
                self.assertEqual(len(manifest["payloads"]), 22)

    def test_rejects_invalid_sample_cell_counts(self):
        for count in (0, -1, True, 16385):
            with self.subTest(count=count):
                with self.assertRaisesRegex(SmokeError, "invalid bounded sample_cell_count"):
                    validate_resource(resource(sample_cells=count), "runtime-stage")

    def test_preserves_source_and_target_count_bounds(self):
        for key, count in (("cell_count", 4097), ("vertex_count", 16385),
                           ("target_count", 16385)):
            with self.subTest(key=key):
                value = resource()
                value["closed_loop_manifest"][key] = count
                with self.assertRaisesRegex(SmokeError, "invalid bounded " + key):
                    validate_resource(value, "runtime-stage")

    def test_rejects_sample_cells_descriptor_size_mismatch(self):
        for delta in (-16, 16):
            with self.subTest(delta=delta):
                value = resource()
                value["closed_loop_manifest"]["payloads"]["sample_cells"]["byte_length"] += delta
                with self.assertRaisesRegex(SmokeError, "sample_cells size differs"):
                    validate_resource(value, "runtime-stage")

    def test_preserves_individual_payload_byte_bound(self):
        value = resource()
        value["closed_loop_manifest"]["payloads"]["source_preimage"]["byte_length"] = (16 << 20) + 1
        with self.assertRaisesRegex(SmokeError, "invalid bounded source_preimage byte_length"):
            validate_resource(value, "runtime-stage")

    def test_preserves_aggregate_payload_byte_bound(self):
        value = resource()
        for key in ("prepared_preimage", "charge_preimage", "source_preimage", "certificate"):
            value["closed_loop_manifest"]["payloads"][key]["byte_length"] = 16 << 20
        with self.assertRaisesRegex(SmokeError, "aggregate payload bound exceeded"):
            validate_resource(value, "runtime-stage")


if __name__ == "__main__":
    unittest.main()
