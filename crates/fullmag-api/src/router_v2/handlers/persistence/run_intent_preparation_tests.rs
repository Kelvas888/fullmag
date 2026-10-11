use super::*;
use axum::http::StatusCode;
use fullmag_application::{ProjectEnvelope, RunIntent};
use serde_json::Value;

fn request() -> (ProjectId, ProjectRunIntentRequest) {
    // Structural identity fixture, not qualification of a physical scene.
    let fixture: Value = serde_json::from_str(include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/fixtures/runtime/accepted-fem-preparation-run-v2.json"
    )))
    .unwrap();
    let original: RunIntent = serde_json::from_value(fixture["run_intent"].clone()).unwrap();
    let authored = RunIntentAuthoring {
        run_id: original.specification.run_id,
        idempotency_key: original.idempotency_key,
        parameters: original.specification.parameters,
        seeds: original.specification.seeds,
        dependencies: original.specification.dependencies,
        scheduling_priority: original.specification.scheduling_priority,
        requested_execution: original.specification.requested_execution,
    };
    let project_id = ProjectId::parse("project-submit").unwrap();
    let envelope = ProjectEnvelope::blank(project_id.clone(), "Fixture").unwrap();
    let archive = FileProjectRepository::new()
        .encode_archive(&envelope)
        .unwrap();
    (
        project_id,
        ProjectRunIntentRequest {
            archive_base64: STANDARD.encode(archive),
            expected_revision: envelope.definition.revision,
            run_authoring: serde_json::from_value(serde_json::to_value(authored).unwrap()).unwrap(),
            study_plan: serde_json::from_value(fixture["study_plan"].clone()).unwrap(),
            study_problem_catalog: serde_json::from_value(fixture["study_problem_catalog"].clone())
                .unwrap(),
            asset_paths: Default::default(),
        },
    )
}

#[test]
fn preparation_replays_the_same_identity_without_a_store_or_session() {
    let (project_id, request) = request();
    let expected_id = request.run_authoring["run_id"].clone();
    let expected_key = request.run_authoring["idempotency_key"].clone();
    let first = prepare_identity(project_id.clone(), request.clone()).unwrap();
    let second = prepare_identity(project_id, request).unwrap();
    assert_eq!(first.run_intent, second.run_intent);
    assert_eq!(first.payload_fingerprint, second.payload_fingerprint);
    let intent: RunIntent =
        serde_json::from_value(serde_json::to_value(first.run_intent).unwrap()).unwrap();
    assert_eq!(
        serde_json::to_value(&intent.specification.run_id).unwrap(),
        expected_id
    );
    assert_eq!(
        serde_json::to_value(&intent.idempotency_key).unwrap(),
        expected_key
    );
    assert_eq!(
        first.payload_fingerprint,
        intent.payload_fingerprint().unwrap()
    );
}

#[test]
fn preparation_rejects_archived_identity_and_revision_conflicts() {
    let (project_id, mut request) = request();
    let wrong_id = ProjectId::parse("another-project").unwrap();
    assert_eq!(
        prepare_identity(wrong_id, request.clone())
            .unwrap_err()
            .status,
        StatusCode::CONFLICT
    );
    request.expected_revision += 1;
    assert_eq!(
        prepare_identity(project_id, request).unwrap_err().status,
        StatusCode::CONFLICT
    );
}

#[test]
fn preparation_rejects_invalid_archive_and_missing_asset_binding() {
    let (project_id, mut request) = request();
    let mut invalid = request.clone();
    invalid.archive_base64 = "not base64".into();
    assert_eq!(
        prepare_identity(project_id.clone(), invalid)
            .unwrap_err()
            .status,
        StatusCode::BAD_REQUEST
    );
    request
        .asset_paths
        .insert("missing".into(), "project/assets/missing.bin".into());
    assert_eq!(
        prepare_identity(project_id, request).unwrap_err().status,
        StatusCode::BAD_REQUEST
    );
}

#[test]
fn preparation_rejects_unknown_authoring_fields_and_execution_conflicts() {
    let (project_id, mut request) = request();
    let mut unknown = request.clone();
    unknown
        .run_authoring
        .insert("session_id".into(), Value::String("live".into()));
    assert_eq!(
        prepare_identity(project_id.clone(), unknown)
            .unwrap_err()
            .status,
        StatusCode::BAD_REQUEST
    );
    request
        .run_authoring
        .get_mut("requested_execution")
        .unwrap()["backend"] = Value::String("fdm".into());
    assert_eq!(
        prepare_identity(project_id, request).unwrap_err().status,
        StatusCode::BAD_REQUEST
    );
}
