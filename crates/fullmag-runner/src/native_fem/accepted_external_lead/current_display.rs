//! Transport-only binding of native cell samples; no RT0 reconstruction or solve.

use super::AcceptedExternalLeadBundle;
use crate::native_fem::accepted_terminal_charge::record::Reader;
use crate::types::RunError;
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};

const CELL_STRIDE_BYTES: usize = 1501;
pub(super) const SCHEMA: &str = "accepted_external_lead_current_display.ordered.v1";
pub(super) const OPERATOR: &str = "fem_accepted_external_lead_current_display.v1";
const HEADER: [(&str, &str); 10] = [
    ("schema", SCHEMA),
    ("operator_version", OPERATOR),
    ("current_evaluator_version", "fem_generic_affine_rt0.v1"),
    ("sampling_policy", "cell_center_and_cell_local_vertices.v1"),
    ("center_policy", "vertex_quarter_sum.long_double.v1"),
    ("field_scope", "external_electrode_truncation"),
    ("status", "inspection_only"),
    ("normalization", "raw_authored_current"),
    ("coordinate_unit", "m"),
    ("current_density_unit", "A/m^2"),
];

#[derive(Debug)]
pub(crate) struct AcceptedExternalLeadCurrentDisplayCell {
    pub source_element_index: u64,
    pub vertex_ids: [u64; 4],
    pub vertex_xyz_m: [[f64; 3]; 4],
    pub vertex_j_apm2: [[f64; 3]; 4],
    pub center_xyz_m: [f64; 3],
    pub center_j_apm2: [f64; 3],
}

#[derive(Debug)]
pub(crate) struct AcceptedExternalLeadCurrentDisplay {
    pub canonical_payload: Vec<u8>,
    pub content_sha256: String,
    pub cells: Vec<AcceptedExternalLeadCurrentDisplayCell>,
}

fn fail(message: impl std::fmt::Display) -> RunError {
    RunError {
        message: format!("accepted external lead current display: {message}"),
    }
}

fn require(condition: bool, message: &str) -> Result<(), RunError> {
    if condition {
        Ok(())
    } else {
        Err(fail(message))
    }
}

fn vector(reader: &mut Reader<'_>, name: &str) -> Result<[f64; 3], RunError> {
    Ok([reader.real(name)?, reader.real(name)?, reader.real(name)?])
}

/// `bundle` must already have passed the complete owned-bundle decoder.
pub(crate) fn decode_current_display(
    payload: Vec<u8>,
    expected_sha: &str,
    bundle: &AcceptedExternalLeadBundle,
) -> Result<AcceptedExternalLeadCurrentDisplay, RunError> {
    require(
        !payload.is_empty()
            && payload.len() <= super::MAX_PAYLOAD_BYTES
            && expected_sha.len() == 64
            && expected_sha
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            && format!("{:x}", Sha256::digest(&payload)) == expected_sha,
        "canonical hash or payload bound mismatch",
    )?;
    let mut reader = Reader::new(&payload);
    for (name, value) in HEADER {
        require(
            reader.text(name)? == value,
            "schema, operator, sampling, scope or SI mismatch",
        )?;
    }
    for (name, value) in [
        ("bundle_content_sha256", &bundle.content_sha256),
        ("charge_content_sha256", &bundle.charge.content_sha256),
        ("source_content_sha256", &bundle.source_content_sha256),
        (
            "stable_vertex_id_version",
            &bundle.charge.stable_vertex_version,
        ),
    ] {
        require(
            reader.text(name)? == *value,
            "retained bundle pin or vertex issuer mismatch",
        )?;
    }
    let count = usize::try_from(reader.integer("cell_count")?).map_err(fail)?;
    let bytes = count
        .checked_mul(CELL_STRIDE_BYTES)
        .ok_or_else(|| fail("cell byte count overflows"))?;
    require(
        count > 0
            && count <= bundle.charge.elements.len()
            && bytes == payload.len() - reader.position(),
        "cell count or exact framing mismatch",
    )?;

    let vertices = &bundle.charge.vertices;
    require(
        !vertices.is_empty()
            && !bundle.source.device_vertex_ids.is_empty()
            && !bundle.source.lead_vertex_ids.is_empty()
            && bundle
                .source
                .device_vertex_ids
                .len()
                .checked_add(bundle.source.lead_vertex_ids.len())
                == Some(vertices.len()),
        "retained device/lead partition cardinality mismatch",
    )?;
    let mut xyz = HashMap::new();
    xyz.try_reserve(vertices.len()).map_err(fail)?;
    for vertex in vertices {
        require(
            vertex.id != 0 && xyz.insert(vertex.id, vertex.xyz_m).is_none(),
            "retained vertex identity is zero or repeated",
        )?;
    }
    let mut device = HashSet::new();
    device
        .try_reserve(bundle.source.device_vertex_ids.len())
        .map_err(fail)?;
    for id in &bundle.source.device_vertex_ids {
        require(
            xyz.contains_key(id) && device.insert(*id),
            "device vertex is repeated or foreign",
        )?;
    }
    let mut lead = HashSet::new();
    lead.try_reserve(bundle.source.lead_vertex_ids.len())
        .map_err(fail)?;
    for id in &bundle.source.lead_vertex_ids {
        require(
            xyz.contains_key(id) && !device.contains(id) && lead.insert(*id),
            "lead vertex is repeated, foreign or device-owned",
        )?;
    }
    let mut expected_count = 0usize;
    for element in &bundle.charge.elements {
        if element.vertex_ids.iter().all(|id| device.contains(id)) {
            expected_count += 1;
        } else {
            require(
                element.vertex_ids.iter().all(|id| lead.contains(id)),
                "retained tetrahedron has mixed or foreign ownership",
            )?;
        }
    }
    require(count == expected_count, "device cell coverage mismatch")?;
    let mut cells = Vec::new();
    cells.try_reserve_exact(count).map_err(fail)?;
    for (index, element) in bundle.charge.elements.iter().enumerate() {
        if !device.contains(&element.vertex_ids[0]) {
            continue;
        }
        let source_element_index = reader.integer("source_element_index")?;
        require(
            source_element_index == index as u64,
            "whole-mesh device index or order mismatch",
        )?;
        let mut vertex_xyz_m = [[0.; 3]; 4];
        let mut vertex_j_apm2 = [[0.; 3]; 4];
        for local in 0..4 {
            let id = reader.integer("vertex_id")?;
            require(
                id == element.vertex_ids[local],
                "cell-local vertex identity or order mismatch",
            )?;
            vertex_xyz_m[local] = vector(&mut reader, "vertex_coordinate_m")?;
            require(
                vertex_xyz_m[local].map(f64::to_bits) == xyz[&id].map(f64::to_bits),
                "cell-local coordinates differ from retained charge geometry",
            )?;
            vertex_j_apm2[local] = vector(&mut reader, "vertex_current_apm2")?;
        }
        // Preserve native long-double center evaluation; do not recompute it in Rust.
        let center_xyz_m = vector(&mut reader, "center_coordinate_m")?;
        let center_j_apm2 = vector(&mut reader, "center_current_apm2")?;
        cells.push(AcceptedExternalLeadCurrentDisplayCell {
            source_element_index,
            vertex_ids: element.vertex_ids,
            vertex_xyz_m,
            vertex_j_apm2,
            center_xyz_m,
            center_j_apm2,
        });
    }
    reader.finish()?;
    Ok(AcceptedExternalLeadCurrentDisplay {
        canonical_payload: payload,
        content_sha256: expected_sha.into(),
        cells,
    })
}

#[cfg(all(test, any(feature = "fem-native", feature = "fem-gpu")))]
mod tests {
    use super::*;

    // Independent codec fixture, not evidence that a native current solve ran.
    fn field(bytes: &mut Vec<u8>, name: &str, tag: u8, value: &[u8]) {
        bytes.extend_from_slice(&(name.len() as u64).to_be_bytes());
        bytes.extend_from_slice(name.as_bytes());
        bytes.push(tag);
        bytes.extend_from_slice(&(value.len() as u64).to_be_bytes());
        bytes.extend_from_slice(value);
    }

    fn sha(bytes: &[u8]) -> String {
        format!("{:x}", Sha256::digest(bytes))
    }

    fn fixture() -> (AcceptedExternalLeadBundle, Vec<u8>) {
        let bytes = super::super::inspection_test_bundle();
        let bundle = super::super::decode_owned_bundle(bytes.clone(), &sha(&bytes)).unwrap();
        let device = bundle
            .source
            .device_vertex_ids
            .iter()
            .copied()
            .collect::<HashSet<_>>();
        let selected = bundle
            .charge
            .elements
            .iter()
            .enumerate()
            .filter(|(_, element)| element.vertex_ids.iter().all(|id| device.contains(id)))
            .collect::<Vec<_>>();
        let mut bytes = Vec::new();
        for (name, value) in [
            (
                "schema",
                "accepted_external_lead_current_display.ordered.v1",
            ),
            (
                "operator_version",
                "fem_accepted_external_lead_current_display.v1",
            ),
            ("current_evaluator_version", "fem_generic_affine_rt0.v1"),
            ("sampling_policy", "cell_center_and_cell_local_vertices.v1"),
            ("center_policy", "vertex_quarter_sum.long_double.v1"),
            ("field_scope", "external_electrode_truncation"),
            ("status", "inspection_only"),
            ("normalization", "raw_authored_current"),
            ("coordinate_unit", "m"),
            ("current_density_unit", "A/m^2"),
            ("bundle_content_sha256", bundle.content_sha256.as_str()),
            (
                "charge_content_sha256",
                bundle.charge.content_sha256.as_str(),
            ),
            (
                "source_content_sha256",
                bundle.source_content_sha256.as_str(),
            ),
            (
                "stable_vertex_id_version",
                bundle.charge.stable_vertex_version.as_str(),
            ),
        ] {
            field(&mut bytes, name, 1, value.as_bytes());
        }
        field(
            &mut bytes,
            "cell_count",
            2,
            &(selected.len() as u64).to_be_bytes(),
        );
        for (index, element) in selected {
            field(
                &mut bytes,
                "source_element_index",
                2,
                &(index as u64).to_be_bytes(),
            );
            for id in element.vertex_ids {
                field(&mut bytes, "vertex_id", 2, &id.to_be_bytes());
                let xyz = bundle
                    .charge
                    .vertices
                    .iter()
                    .find(|vertex| vertex.id == id)
                    .unwrap()
                    .xyz_m;
                for value in xyz {
                    field(
                        &mut bytes,
                        "vertex_coordinate_m",
                        4,
                        &value.to_bits().to_be_bytes(),
                    );
                }
                for value in [1.0f64, -2., 3.] {
                    field(
                        &mut bytes,
                        "vertex_current_apm2",
                        4,
                        &value.to_bits().to_be_bytes(),
                    );
                }
            }
            for value in [0.25f64, 0.5, 0.75] {
                field(
                    &mut bytes,
                    "center_coordinate_m",
                    4,
                    &value.to_bits().to_be_bytes(),
                );
            }
            for value in [1.0f64, -2., 3.] {
                field(
                    &mut bytes,
                    "center_current_apm2",
                    4,
                    &value.to_bits().to_be_bytes(),
                );
            }
        }
        (bundle, bytes)
    }

    fn replace_value(bytes: &mut [u8], name: &str, occurrence: usize, value: &[u8]) {
        let mut prefix = Vec::new();
        prefix.extend_from_slice(&(name.len() as u64).to_be_bytes());
        prefix.extend_from_slice(name.as_bytes());
        let begin = bytes
            .windows(prefix.len())
            .enumerate()
            .filter(|(_, window)| *window == prefix.as_slice())
            .nth(occurrence)
            .unwrap()
            .0
            + 17
            + name.len();
        bytes[begin..begin + value.len()].copy_from_slice(value);
    }

    #[test]
    fn retains_native_samples_and_complete_local_geometry() {
        let (bundle, bytes) = fixture();
        let digest = sha(&bytes);
        let decoded = decode_current_display(bytes.clone(), &digest, &bundle).unwrap();
        assert_eq!(decoded.canonical_payload, bytes);
        assert_eq!(decoded.content_sha256, digest);
        assert_eq!(decoded.cells.len(), 6);
        for cell in decoded.cells {
            assert_eq!(
                cell.vertex_ids,
                bundle.charge.elements[cell.source_element_index as usize].vertex_ids
            );
            assert_eq!(cell.center_xyz_m, [0.25, 0.5, 0.75]);
            assert_eq!(cell.center_j_apm2, [1., -2., 3.]);
            assert_eq!(cell.vertex_j_apm2, [[1., -2., 3.]; 4]);
        }
    }

    #[test]
    fn refuses_foreign_pins_indices_local_ids_geometry_and_noncanonical_scalars() {
        let (bundle, original) = fixture();
        for (name, _) in HEADER {
            let mut bytes = original.clone();
            replace_value(&mut bytes, name, 0, b"X");
            assert!(
                decode_current_display(bytes.clone(), &sha(&bytes), &bundle).is_err(),
                "{name}"
            );
        }
        for (name, occurrence, value) in [
            ("bundle_content_sha256", 0, b"X".to_vec()),
            ("charge_content_sha256", 0, b"X".to_vec()),
            ("source_content_sha256", 0, b"X".to_vec()),
            ("stable_vertex_id_version", 0, b"X".to_vec()),
            ("current_density_unit", 0, b"X".to_vec()),
            ("operator_version", 0, b"X".to_vec()),
            ("cell_count", 0, u64::MAX.to_be_bytes().to_vec()),
            ("source_element_index", 0, 6u64.to_be_bytes().to_vec()),
            ("source_element_index", 1, 0u64.to_be_bytes().to_vec()),
            ("vertex_id", 0, 999u64.to_be_bytes().to_vec()),
            (
                "vertex_id",
                0,
                bundle.charge.elements[0].vertex_ids[1]
                    .to_be_bytes()
                    .to_vec(),
            ),
            (
                "vertex_coordinate_m",
                0,
                0.125f64.to_bits().to_be_bytes().to_vec(),
            ),
            (
                "vertex_current_apm2",
                0,
                f64::NAN.to_bits().to_be_bytes().to_vec(),
            ),
            (
                "center_current_apm2",
                0,
                f64::INFINITY.to_bits().to_be_bytes().to_vec(),
            ),
            (
                "center_coordinate_m",
                0,
                (-0.0f64).to_bits().to_be_bytes().to_vec(),
            ),
        ] {
            let mut bytes = original.clone();
            replace_value(&mut bytes, name, occurrence, &value);
            assert!(
                decode_current_display(bytes.clone(), &sha(&bytes), &bundle).is_err(),
                "{name}"
            );
        }
    }

    #[test]
    fn refuses_incomplete_extra_bytes_bad_sha_and_missing_partition() {
        let (mut bundle, original) = fixture();
        assert!(decode_current_display(original.clone(), &"0".repeat(64), &bundle).is_err());
        for bytes in [
            original[..original.len() - 1].to_vec(),
            [original.clone(), vec![0]].concat(),
        ] {
            assert!(decode_current_display(bytes.clone(), &sha(&bytes), &bundle).is_err());
        }
        bundle.source.device_vertex_ids.pop();
        assert!(decode_current_display(original.clone(), &sha(&original), &bundle).is_err());
    }
}
