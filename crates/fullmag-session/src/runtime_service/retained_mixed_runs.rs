//! Explicit v4 recovery of complete terminal and never-released manual history.
//! The caller holds the host writer before the SessionStore writer through
//! owner publication. No run lifecycle, start grant, lease or result is changed.
use std::collections::{BTreeMap, BTreeSet};

use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};

use crate::host_resource_ledger::HostResourceLedger;
use crate::repository_path::validate_store_id;
use crate::store::SessionStore;
use super::retained_cancelled_runs::{
    validate_retained_run_inputs_with_budget, RetainedCancelledRunPin,
    MAX_RETAINED_CANCELLED_RUN_PINS,
};
use super::retained_terminal_runs::{self, RetainedTerminalRunPin};

// A v4 inventory can contain the existing history, not merely the latest run.
// Keep legacy v1-v3 at 128 MiB. The observed 43-run input references exceed it.
const MAX_MIXED_OBSERVED_FILE_BYTES: u64 = 256 * 1024 * 1024;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RetainedHeldManualRunPin {
    pub run_id: String,
    pub run_intent_sha256: String,
    pub run_catalog_sha256: String,
    pub held_evidence_sha256: String,
}

pub(crate) fn validate_pins(
    terminal: &[RetainedTerminalRunPin],
    held: &[RetainedHeldManualRunPin],
) -> Result<()> {
    retained_terminal_runs::validate_pins(terminal)?;
    if held.is_empty() || terminal.len().saturating_add(held.len()) > MAX_RETAINED_CANCELLED_RUN_PINS {
        bail!("v4 mixed history requires nonempty terminal and held inventories within the run limit");
    }
    let mut seen = terminal.iter().map(|pin| pin.run_id.as_str()).collect::<BTreeSet<_>>();
    for pin in held {
        validate_store_id(&pin.run_id)?;
        if !seen.insert(&pin.run_id) {
            bail!("v4 mixed history repeats a terminal or held run id");
        }
        for digest in [&pin.run_intent_sha256, &pin.run_catalog_sha256, &pin.held_evidence_sha256] {
            if digest.len() != 64 || !digest.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) {
                bail!("v4 held-manual pins require lowercase SHA-256");
            }
        }
    }
    Ok(())
}

pub(crate) fn validate_retained_mixed_runs(
    store: &SessionStore,
    ledger: &HostResourceLedger,
    terminal: &[RetainedTerminalRunPin],
    held: &[RetainedHeldManualRunPin],
) -> Result<()> {
    validate_pins(terminal, held)?;
    let terminal_by_id = terminal.iter().map(|pin| (pin.run_id.as_str(), pin))
        .collect::<BTreeMap<_, _>>();
    let held_by_id = held.iter().map(|pin| (pin.run_id.as_str(), pin))
        .collect::<BTreeMap<_, _>>();
    let inputs = terminal.iter().map(|pin| RetainedCancelledRunPin {
        run_id: pin.run_id.clone(), run_intent_sha256: pin.run_intent_sha256.clone(),
        run_catalog_sha256: pin.run_catalog_sha256.clone(),
    }).chain(held.iter().map(|pin| RetainedCancelledRunPin {
        run_id: pin.run_id.clone(), run_intent_sha256: pin.run_intent_sha256.clone(),
        run_catalog_sha256: pin.run_catalog_sha256.clone(),
    })).collect::<Vec<_>>();
    // Reuse exact whole-store inventory, immutable intent/catalog and CAS
    // validation. No unlisted historical run can be omitted from recovery.
    validate_retained_run_inputs_with_budget(store, &inputs, Some(&|run_id| {
        if let Some(pin) = terminal_by_id.get(run_id) {
            if ledger.terminal_run_evidence_sha256_locked(store, run_id)? != pin.terminal_evidence_sha256 {
                bail!("v4 retained terminal-run evidence changed");
            }
        } else {
            let pin = held_by_id.get(run_id).context("v4 run lacks an explicit history pin")?;
            if ledger.held_manual_run_evidence_sha256_locked(store, run_id)? != pin.held_evidence_sha256 {
                bail!("v4 retained held-manual evidence changed");
            }
        }
        Ok(())
    }), MAX_MIXED_OBSERVED_FILE_BYTES)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn terminal() -> RetainedTerminalRunPin {
        RetainedTerminalRunPin { run_id: "run-terminal".into(), run_intent_sha256: "a".repeat(64),
            run_catalog_sha256: "b".repeat(64), terminal_evidence_sha256: "c".repeat(64) }
    }
    fn held() -> RetainedHeldManualRunPin {
        RetainedHeldManualRunPin { run_id: "run-held".into(), run_intent_sha256: "d".repeat(64),
            run_catalog_sha256: "e".repeat(64), held_evidence_sha256: "f".repeat(64) }
    }
    #[test]
    fn mixed_pins_require_disjoint_nonempty_bounded_inventories() {
        assert!(validate_pins(&[terminal()], &[held()]).is_ok());
        assert!(validate_pins(&[], &[held()]).is_err());
        assert!(validate_pins(&[terminal()], &[]).is_err());
        assert!(validate_pins(&[terminal()], &[held(), held()]).is_err());
        let mut overlap = held(); overlap.run_id = terminal().run_id;
        assert!(validate_pins(&[terminal()], &[overlap]).is_err());
        let overflow = (0..128).map(|index| { let mut pin = held();
            pin.run_id = format!("run-held-{index}"); pin }).collect::<Vec<_>>();
        assert!(validate_pins(&[terminal()], &overflow).is_err());
    }
    #[test]
    fn held_evidence_is_an_exact_digest_not_an_optional_status() {
        for invalid in ["".into(), "A".repeat(64), "0".repeat(63)] {
            let mut pin = held(); pin.held_evidence_sha256 = invalid;
            assert!(validate_pins(&[terminal()], &[pin]).is_err());
        }
    }

    fn held_store() -> (tempfile::TempDir, SessionStore, crate::FmsRunIntent) {
        use crate::{FmsRunCatalog, FmsRunIntent, FmsTaskCatalogEntry,
            FmsTaskLifecycle, FmsTaskReadiness, FMS_RUN_CATALOG_SCHEMA};
        let directory = tempfile::tempdir().unwrap();
        let store = SessionStore::open(directory.path()).unwrap();
        let intent = FmsRunIntent::new("run-held", "submit-held", serde_json::json!({
            "run_id": "run-held", "parameters": {"fullmag.accepted_run_start": {
                "schema_version": "accepted_run_start_policy.v1", "mode": "manual"
            }}
        }));
        store.commit_run_intent(&intent).unwrap();
        store.commit_run_catalog(&FmsRunCatalog {
            schema_version: FMS_RUN_CATALOG_SCHEMA.into(), run_id: "run-held".into(),
            revision: 1, updated_at: chrono::Utc::now(), tasks: vec![FmsTaskCatalogEntry {
                task_id: "task-held".into(), input_fingerprint: "a".repeat(64),
                lifecycle: FmsTaskLifecycle::Accepted,
                readiness: FmsTaskReadiness::Blocked { reason: "awaiting explicit start".into() },
                observation: None, attempt_id: None, ownership_epoch: None,
                resolved_input_fingerprint: None, artifact_ids: Vec::new(), resource_id: None,
                coordinator_watermark: None, coordinator_genesis: None,
            }],
        }).unwrap();
        (directory, store, intent)
    }

    fn held_evidence(store: &SessionStore) -> anyhow::Result<serde_json::Value> {
        let _writer = store.write_transaction()?;
        store.held_manual_run_evidence_value_locked("run-held",
            |_lease, _exit| Ok(None), |_lease, _exit| Ok(None))
    }

    #[test]
    fn held_evidence_preserves_manual_gate_and_does_not_pass_terminal_validation() {
        let (_directory, store, _intent) = held_store();
        let intent_before = std::fs::read(store.root().join("runs/run-held/run_intent.json")).unwrap();
        let catalog_before = std::fs::read(store.root().join("runs/run-held/run_catalog.json")).unwrap();
        assert!(held_evidence(&store).is_ok());
        {
            let _writer = store.write_transaction().unwrap();
            assert!(store.terminal_run_evidence_value_locked("run-held",
                |_lease, _exit| Ok(None), |_lease, _exit| Ok(None)).is_err());
        }
        assert!(!store.accepted_run_start_permitted("run-held").unwrap());
        assert!(!store.root().join("runs/run-held/start_release.json").exists());
        assert_eq!(std::fs::read(store.root().join("runs/run-held/run_intent.json")).unwrap(), intent_before);
        assert_eq!(std::fs::read(store.root().join("runs/run-held/run_catalog.json")).unwrap(), catalog_before);
    }

    #[test]
    fn held_evidence_refuses_released_or_automatic_run() {
        let (_directory, store, intent) = held_store();
        store.release_accepted_run_start("run-held", &intent.payload_sha256, "compute-held").unwrap();
        assert!(held_evidence(&store).is_err());
        let (_automatic_directory, automatic, _) = held_store();
        let path = automatic.root().join("runs/run-held/run_intent.json");
        let intent = crate::FmsRunIntent::new("run-held", "submit-held", serde_json::json!({"run_id": "run-held"}));
        std::fs::write(path, serde_json::to_vec(&intent).unwrap()).unwrap();
        assert!(held_evidence(&automatic).is_err());
    }

    #[test]
    fn whole_store_inventory_requires_all_historical_runs_not_only_three_current_runs() {
        let (_directory, store, _intent) = held_store();
        let template = store.read_run_catalog("run-held").unwrap().unwrap();
        for index in 0..42 {
            let run_id = format!("run-history-{index}");
            let intent = crate::FmsRunIntent::new(run_id.clone(), format!("submit-history-{index}"),
                serde_json::json!({"run_id": &run_id}));
            store.commit_run_intent(&intent).unwrap();
            let mut catalog = template.clone(); catalog.run_id = run_id;
            store.commit_run_catalog(&catalog).unwrap();
        }
        std::fs::create_dir_all(store.root().join("objects/pins")).unwrap();
        let mut pins = Vec::new();
        for entry in std::fs::read_dir(store.root().join("runs")).unwrap() {
            let directory = entry.unwrap().path();
            pins.push(RetainedCancelledRunPin {
                run_id: directory.file_name().unwrap().to_str().unwrap().into(),
                run_intent_sha256: crate::hex_sha256(&std::fs::read(directory.join("run_intent.json")).unwrap()),
                run_catalog_sha256: crate::hex_sha256(&std::fs::read(directory.join("run_catalog.json")).unwrap()),
            });
        }
        let _writer = store.write_transaction().unwrap();
        let full = validate_retained_run_inputs_with_budget(&store, &pins,
            Some(&|_| Ok(())), MAX_MIXED_OBSERVED_FILE_BYTES).unwrap();
        assert_eq!(full.run_count, 43);
        let incomplete = validate_retained_run_inputs_with_budget(&store, &pins[..3],
            Some(&|_| Ok(())), MAX_MIXED_OBSERVED_FILE_BYTES).unwrap_err();
        assert!(incomplete.to_string().contains("exactly match"));
    }

    #[test]
    fn held_evidence_refuses_solver_ownership_and_hidden_admission() {
        let (_directory, store, _) = held_store();
        let path = store.root().join("runs/run-held/run_catalog.json");
        let mut catalog = store.read_run_catalog("run-held").unwrap().unwrap();
        catalog.tasks[0].attempt_id = Some("attempt-held".into());
        catalog.tasks[0].ownership_epoch = Some(1);
        std::fs::write(&path, serde_json::to_vec(&catalog).unwrap()).unwrap();
        assert!(held_evidence(&store).is_err());
        catalog.tasks[0].attempt_id = None; catalog.tasks[0].ownership_epoch = None;
        std::fs::write(&path, serde_json::to_vec(&catalog).unwrap()).unwrap();
        let admissions = store.root().join("runs/run-held/task_admissions/task-held");
        std::fs::create_dir_all(&admissions).unwrap();
        std::fs::write(admissions.join("attempt-hidden.json"), b"{}").unwrap();
        assert!(held_evidence(&store).is_err());
    }
}
