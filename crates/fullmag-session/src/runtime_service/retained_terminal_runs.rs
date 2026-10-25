//! Pinned completed-run history for namespace recovery. No mutation or retry.
use std::collections::BTreeMap;

use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};

use crate::host_resource_ledger::HostResourceLedger;
use crate::repository_path::validate_store_id;
use crate::store::SessionStore;
use super::retained_cancelled_runs::{
    validate_retained_run_inputs, RetainedCancelledRunPin, MAX_RETAINED_CANCELLED_RUN_PINS,
};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RetainedTerminalRunPin {
    pub run_id: String,
    pub run_intent_sha256: String,
    pub run_catalog_sha256: String,
    pub terminal_evidence_sha256: String,
}

pub(crate) fn validate_pins(pins: &[RetainedTerminalRunPin]) -> Result<()> {
    if pins.is_empty() || pins.len() > MAX_RETAINED_CANCELLED_RUN_PINS {
        bail!("retained terminal-run pin count exceeds its bounded nonempty domain");
    }
    let mut seen = std::collections::BTreeSet::new();
    for pin in pins {
        validate_store_id(&pin.run_id)?;
        if !seen.insert(&pin.run_id) {
            bail!("retained terminal-run pins repeat a run id");
        }
        for digest in [&pin.run_intent_sha256, &pin.run_catalog_sha256, &pin.terminal_evidence_sha256] {
            if digest.len() != 64 || !digest.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) {
                bail!("retained terminal-run pin requires lowercase SHA-256");
            }
        }
    }
    Ok(())
}

/// Caller holds the host writer before the SessionStore writer throughout
/// validation and any later recovery publication. This function is read-only.
pub(crate) fn validate_retained_terminal_runs(
    store: &SessionStore,
    ledger: &HostResourceLedger,
    pins: &[RetainedTerminalRunPin],
) -> Result<()> {
    validate_pins(pins)?;
    let expected = pins.iter().map(|pin| (pin.run_id.as_str(), pin.terminal_evidence_sha256.as_str()))
        .collect::<BTreeMap<_, _>>();
    let inputs = pins.iter().map(|pin| RetainedCancelledRunPin {
        run_id: pin.run_id.clone(), run_intent_sha256: pin.run_intent_sha256.clone(),
        run_catalog_sha256: pin.run_catalog_sha256.clone(),
    }).collect::<Vec<_>>();
    validate_retained_run_inputs(store, &inputs, Some(&|run_id| {
        let observed = ledger.terminal_run_evidence_sha256_locked(store, run_id)?;
        if observed != *expected.get(run_id).context("terminal run lacks an explicit evidence pin")? {
            bail!("retained terminal-run evidence changed");
        }
        Ok(())
    }))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn pin() -> RetainedTerminalRunPin {
        RetainedTerminalRunPin { run_id: "run-done".into(), run_intent_sha256: "a".repeat(64),
            run_catalog_sha256: "b".repeat(64), terminal_evidence_sha256: "c".repeat(64) }
    }
    #[test]
    fn pins_require_exact_unique_run_ids_and_all_three_digests() {
        assert!(validate_pins(&[pin()]).is_ok());
        assert!(validate_pins(&[]).is_err());
        assert!(validate_pins(&[pin(), pin()]).is_err());
        let mut invalid = pin(); invalid.terminal_evidence_sha256 = "A".repeat(64);
        assert!(validate_pins(&[invalid]).is_err());
        let mut invalid = pin(); invalid.run_intent_sha256 = "short".into();
        assert!(validate_pins(&[invalid]).is_err());
        let mut invalid = pin(); invalid.run_id = "../other".into();
        assert!(validate_pins(&[invalid]).is_err());
    }
}
