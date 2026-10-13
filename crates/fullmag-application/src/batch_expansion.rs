//! Bounded deterministic expansion for independent batch cases.
//!
//! This is a pure application primitive. It does not accept a batch into the
//! durable session catalog, reserve OutputStorage, publish child runs, or
//! schedule work. Those responsibilities remain with the existing Submit,
//! session-store, and scheduler owners.

use crate::run_spec::canonical_json_bytes;
use crate::{RunId, RunSpecError, RunSpecification};
use fullmag_authoring::StudyPlan;
use fullmag_ir::{
    EnergyTermIR, InitialMagnetizationIR, OutputStorageIR, ProblemIR, SpinTorqueModuleIR,
};
use fullmag_plan::StudyProblemCatalog;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::path::Path;

pub const BATCH_EXPANSION_MANIFEST_SCHEMA: &str = "batch_expansion_manifest.v2";

/// The current in-memory expander rejects larger manifests so callers cannot
/// accidentally turn a preview or Submit request into an unbounded allocation.
/// Larger batches need the planned paged/content-addressed manifest owner.
pub const BATCH_EXPANSION_MAX_CASES: usize = 10_000;

const BATCH_SEED_POLICY: &str = "sha256-u64-nonzero-be-v2";

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BatchAxisValueKind {
    Boolean,
    Integer,
    Number,
    String,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BatchAxisJoin {
    Cartesian,
    Zip,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BatchRangeEndpoint {
    Exclusive,
    Inclusive,
}

/// A batch axis binds values to one typed, currently executable ProblemIR
/// input. Extending this enum requires an explicit physical unit and solver
/// binding; arbitrary JSON paths are deliberately not accepted.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum BatchAxisTarget {
    /// Global Zeeman induction B, stored in `EnergyTermIR::Zeeman` [T].
    ExternalFieldB {
        step_id: String,
        direction: [f64; 3],
    },
    /// Current-density vector for one Zhang-Li spin-torque module [A/m^2].
    ZhangLiCurrentDensity {
        step_id: String,
        module_id: String,
        direction: [f64; 3],
    },
}

/// Axis values are explicit typed scalars or a bounded decimal-step range.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum BatchAxisValues {
    List {
        values: Vec<Value>,
    },
    NumericRange {
        start: String,
        stop: String,
        step: String,
        endpoint: BatchRangeEndpoint,
    },
}

/// `join` describes how this axis combines with the cases produced by the
/// preceding axes. The first axis must use Cartesian because no prior axis
/// exists to zip against.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BatchAxis {
    /// Stable display and tuple key for this axis.
    pub name: String,
    pub target: BatchAxisTarget,
    pub value_kind: BatchAxisValueKind,
    /// Values are supplied to the expander in this canonical unit. The
    /// `external_field_b` requires `T`; `zhang_li_current_density` requires
    /// `A/m^2`.
    pub canonical_unit: String,
    /// Values are expressed in `canonical_unit`. Numeric ranges use exact
    /// decimal strings for start/stop/step and are bounded before allocation.
    pub values: BatchAxisValues,
    pub join: BatchAxisJoin,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BatchExecutionStrategy {
    Independent,
    Continuation,
    DependencyGraph,
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BatchFailurePolicy {
    /// Keep admitting independent cases after one case reaches a failed state.
    #[default]
    ContinueIndependent,
    /// Stop admitting new cases after any published case fails or is canceled.
    StopAdmission,
}

impl BatchFailurePolicy {
    fn is_continue_independent(&self) -> bool {
        *self == Self::ContinueIndependent
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BatchExpansionRequest {
    pub batch_id: String,
    pub strategy: BatchExecutionStrategy,
    /// Whether a terminal non-success case stops admission of later cases.
    #[serde(default)]
    pub failure_policy: BatchFailurePolicy,
    /// Immutable base request whose snapshot, Study reference, profile-bound
    /// catalog digest, dependencies, and resource request are copied to each
    /// child. Axis values are bound to typed Study/ProblemIR targets during
    /// case materialization, never copied to generic RunSpecification params.
    pub template: RunSpecification,
    pub axes: Vec<BatchAxis>,
    pub master_seed: u64,
    /// Named seed stream used to derive each case seed and its stochastic
    /// ProblemIR component seeds.
    pub seed_name: String,
    /// Caller-selected stricter bound, capped by the in-memory safety limit.
    pub max_cases: usize,
    pub max_parallel_cases: Option<u32>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BatchCase {
    pub case_id: String,
    pub parameter_tuple: BTreeMap<String, Value>,
    /// Deterministic logical case seed. Stochastic ProblemIR inputs receive
    /// stable derived seeds during case materialization; this value is never
    /// sent through the unsupported RunSpecification `seeds` field.
    pub case_seed: u64,
    pub specification: RunSpecification,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BatchExpansionManifest {
    pub schema_version: String,
    pub batch_id: String,
    pub strategy: BatchExecutionStrategy,
    /// Missing legacy values mean the historical continue-independent policy.
    #[serde(default, skip_serializing_if = "BatchFailurePolicy::is_continue_independent")]
    pub failure_policy: BatchFailurePolicy,
    pub source_run_sha256: String,
    pub source_study_plan_sha256: String,
    pub source_study_catalog_sha256: String,
    pub axes: Vec<BatchAxis>,
    pub master_seed: u64,
    pub seed_name: String,
    pub max_parallel_cases: Option<u32>,
    pub cases: Vec<BatchCase>,
    pub manifest_sha256: String,
}

impl BatchExpansionManifest {
    /// Verify the digest and stable case/run/seed relationships before a
    /// caller persists or publishes this manifest.
    pub fn validate_integrity(&self) -> Result<(), BatchExpansionError> {
        if self.schema_version != BATCH_EXPANSION_MANIFEST_SCHEMA {
            return Err(BatchExpansionError::invalid(format!(
                "schema_version must be {BATCH_EXPANSION_MANIFEST_SCHEMA}"
            )));
        }
        validate_identifier(&self.batch_id, "batch_id")?;
        validate_identifier(&self.seed_name, "seed_name")?;
        if self.strategy != BatchExecutionStrategy::Independent {
            return Err(BatchExpansionError::invalid(
                "only independent strategy is currently supported by the pure expander",
            ));
        }
        if self.cases.is_empty() || self.cases.len() > BATCH_EXPANSION_MAX_CASES {
            return Err(BatchExpansionError::invalid(format!(
                "manifest must contain between 1 and {BATCH_EXPANSION_MAX_CASES} cases"
            )));
        }
        if self.max_parallel_cases == Some(0) {
            return Err(BatchExpansionError::invalid(
                "max_parallel_cases must be positive when specified",
            ));
        }
        validate_sha256(&self.source_run_sha256, "source_run_sha256")?;
        validate_sha256(&self.source_study_plan_sha256, "source_study_plan_sha256")?;
        validate_sha256(
            &self.source_study_catalog_sha256,
            "source_study_catalog_sha256",
        )?;
        validate_sha256(&self.manifest_sha256, "manifest_sha256")?;
        validate_axis_bindings(&self.axes)?;

        let expected_tuples = expand_axes(&self.axes, BATCH_EXPANSION_MAX_CASES)?;
        if expected_tuples.len() != self.cases.len() {
            return Err(BatchExpansionError::invalid(
                "case count does not match the axis expansion",
            ));
        }

        let mut case_ids = BTreeSet::new();
        let mut run_ids = BTreeSet::new();
        let mut normalized_template: Option<RunSpecification> = None;
        for (expected_tuple, case) in expected_tuples.iter().zip(&self.cases) {
            if &case.parameter_tuple != expected_tuple {
                return Err(BatchExpansionError::invalid(format!(
                    "case `{}` parameter tuple does not match its axis position",
                    case.case_id
                )));
            }
            let expected_case_id = case_id_for(&self.batch_id, expected_tuple);
            if case.case_id != expected_case_id || !case_ids.insert(case.case_id.as_str()) {
                return Err(BatchExpansionError::invalid(
                    "case ID is invalid or duplicated",
                ));
            }
            let expected_run_id = run_id_for_case(&case.case_id)?;
            if case.specification.run_id != expected_run_id
                || !run_ids.insert(case.specification.run_id.as_str())
            {
                return Err(BatchExpansionError::invalid(format!(
                    "case `{}` child RunId is invalid or duplicated",
                    case.case_id
                )));
            }
            case.specification
                .validate()
                .map_err(BatchExpansionError::from)?;
            if case.case_seed != derive_case_seed(self.master_seed, &self.seed_name, &case.case_id)
            {
                return Err(BatchExpansionError::invalid(format!(
                    "case `{}` seed does not match the manifest policy",
                    case.case_id
                )));
            }
            if !case.specification.seeds.is_empty()
                || !case
                    .specification
                    .parameters
                    .as_object()
                    .is_some_and(|parameters| parameters.is_empty())
            {
                return Err(BatchExpansionError::invalid(format!(
                    "case `{}` must not contain unbound RunSpecification parameters or seeds",
                    case.case_id
                )));
            }
            if case
                .specification
                .dependencies
                .iter()
                .any(is_batch_dependent)
            {
                return Err(BatchExpansionError::invalid(
                    "independent case contains a step-output or continuation dependency",
                ));
            }
            let mut normalized = case.specification.clone();
            if let Some(template) = normalized_template.as_ref() {
                normalized.run_id = template.run_id.clone();
            }
            normalized.study.plan_sha256 = self.source_study_plan_sha256.clone();
            normalized.study_catalog_sha256 = self.source_study_catalog_sha256.clone();
            match normalized_template.as_ref() {
                Some(template) if template != &normalized => {
                    return Err(BatchExpansionError::invalid(
                        "child RunSpecifications do not share one immutable template",
                    ));
                }
                None => normalized_template = Some(normalized),
                _ => {}
            }
        }

        if manifest_digest(self)? != self.manifest_sha256 {
            return Err(BatchExpansionError::invalid(
                "manifest_sha256 does not match its content",
            ));
        }
        Ok(())
    }
}

/// A case-local immutable planner input produced from one batch tuple.
/// Callers persist the exact study and catalog by digest before publishing
/// the matching `specification` as a child run.
#[derive(Clone, Debug, PartialEq)]
pub struct MaterializedBatchCase {
    pub case_id: String,
    pub specification: RunSpecification,
    pub study: StudyPlan,
    pub catalog: StudyProblemCatalog,
    pub execution_plan: fullmag_plan::StudyExecutionPlan,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BatchExpansionError(String);

impl BatchExpansionError {
    fn invalid(message: impl Into<String>) -> Self {
        Self(format!("batch_expansion_invalid: {}", message.into()))
    }
}

impl std::fmt::Display for BatchExpansionError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl std::error::Error for BatchExpansionError {}

impl From<RunSpecError> for BatchExpansionError {
    fn from(error: RunSpecError) -> Self {
        Self::invalid(error.to_string())
    }
}

impl BatchAxisValues {
    fn expand_values(
        &self,
        value_kind: BatchAxisValueKind,
        max_cases: usize,
    ) -> Result<Vec<Value>, BatchExpansionError> {
        match self {
            Self::List { values } => {
                if values.len() > max_cases {
                    return Err(BatchExpansionError::invalid(format!(
                        "axis list has {} values, above max_cases={max_cases}",
                        values.len()
                    )));
                }
                Ok(values.clone())
            }
            Self::NumericRange {
                start,
                stop,
                step,
                endpoint,
            } => expand_numeric_range(value_kind, start, stop, step, *endpoint, max_cases),
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct DecimalValue {
    coefficient: i128,
    scale: u32,
}

impl DecimalValue {
    const MAX_SCALE: u32 = 18;

    fn parse(value: &str, field: &str) -> Result<Self, BatchExpansionError> {
        if value.is_empty() || value.trim() != value {
            return Err(BatchExpansionError::invalid(format!(
                "range {field} must be a decimal string without whitespace"
            )));
        }
        let (negative, unsigned) = match value.as_bytes()[0] {
            b'-' => (true, &value[1..]),
            b'+' => (false, &value[1..]),
            _ => (false, value),
        };
        let mut parts = unsigned.split('.');
        let whole = parts.next().unwrap_or_default();
        let fractional = parts.next().unwrap_or_default();
        if whole.is_empty()
            || !whole.bytes().all(|byte| byte.is_ascii_digit())
            || (unsigned.contains('.')
                && (fractional.is_empty() || !fractional.bytes().all(|byte| byte.is_ascii_digit())))
            || parts.next().is_some()
            || fractional.len() > Self::MAX_SCALE as usize
        {
            return Err(BatchExpansionError::invalid(format!(
                "range {field} must be a finite decimal with at most {} fractional digits",
                Self::MAX_SCALE
            )));
        }

        let digits = format!("{whole}{fractional}");
        let signed = if negative {
            format!("-{digits}")
        } else {
            digits
        };
        let coefficient = signed.parse::<i128>().map_err(|_| {
            BatchExpansionError::invalid(format!("range {field} exceeds the decimal integer range"))
        })?;
        Ok(Self::normalized(coefficient, fractional.len() as u32))
    }

    fn normalized(mut coefficient: i128, mut scale: u32) -> Self {
        while scale > 0 && coefficient % 10 == 0 {
            coefficient /= 10;
            scale -= 1;
        }
        Self { coefficient, scale }
    }

    fn at_scale(self, scale: u32, field: &str) -> Result<i128, BatchExpansionError> {
        let power = scale.checked_sub(self.scale).ok_or_else(|| {
            BatchExpansionError::invalid(format!("range {field} scale is inconsistent"))
        })?;
        let factor = 10_i128.checked_pow(power).ok_or_else(|| {
            BatchExpansionError::invalid(format!("range {field} scale overflows"))
        })?;
        self.coefficient.checked_mul(factor).ok_or_else(|| {
            BatchExpansionError::invalid(format!("range {field} exceeds the decimal integer range"))
        })
    }

    fn to_json_number(self) -> Result<serde_json::Number, BatchExpansionError> {
        let raw = self.coefficient.to_string();
        let (sign, digits) = raw
            .strip_prefix('-')
            .map(|digits| ("-", digits))
            .unwrap_or(("", raw.as_str()));
        let text = if self.scale == 0 {
            format!("{sign}{digits}")
        } else {
            let scale = self.scale as usize;
            let formatted = if digits.len() > scale {
                let split = digits.len() - scale;
                format!("{}{}.{}", sign, &digits[..split], &digits[split..])
            } else {
                format!("{sign}0.{}{}", "0".repeat(scale - digits.len()), digits)
            };
            formatted
        };
        let number = text.parse::<serde_json::Number>().map_err(|error| {
            BatchExpansionError::invalid(format!("range value is not a JSON number: {error}"))
        })?;
        if number.as_f64().is_none_or(|value| !value.is_finite()) {
            return Err(BatchExpansionError::invalid(
                "range value is outside finite JSON number bounds",
            ));
        }
        Ok(number)
    }
}

fn expand_numeric_range(
    value_kind: BatchAxisValueKind,
    start: &str,
    stop: &str,
    step: &str,
    endpoint: BatchRangeEndpoint,
    max_cases: usize,
) -> Result<Vec<Value>, BatchExpansionError> {
    if !matches!(
        value_kind,
        BatchAxisValueKind::Integer | BatchAxisValueKind::Number
    ) {
        return Err(BatchExpansionError::invalid(
            "numeric ranges require an integer or number axis",
        ));
    }
    let start = DecimalValue::parse(start, "start")?;
    let stop = DecimalValue::parse(stop, "stop")?;
    let step = DecimalValue::parse(step, "step")?;
    if value_kind == BatchAxisValueKind::Integer
        && [start.scale, stop.scale, step.scale]
            .into_iter()
            .any(|scale| scale != 0)
    {
        return Err(BatchExpansionError::invalid(
            "integer ranges cannot contain fractional start, stop, or step values",
        ));
    }

    let scale = start.scale.max(stop.scale).max(step.scale);
    let start = start.at_scale(scale, "start")?;
    let stop = stop.at_scale(scale, "stop")?;
    let step = step.at_scale(scale, "step")?;
    if step == 0 {
        return Err(BatchExpansionError::invalid("range step must not be zero"));
    }
    let difference = stop.checked_sub(start).ok_or_else(|| {
        BatchExpansionError::invalid("range difference exceeds the decimal integer range")
    })?;
    if (difference > 0 && step < 0) || (difference < 0 && step > 0) {
        return Err(BatchExpansionError::invalid(
            "range step direction does not lead from start to stop",
        ));
    }

    let distance = difference.unsigned_abs();
    let stride = step.unsigned_abs();
    let count = match endpoint {
        BatchRangeEndpoint::Inclusive => {
            if distance % stride != 0 {
                return Err(BatchExpansionError::invalid(
                    "inclusive range stop must be reached exactly by step",
                ));
            }
            distance / stride + 1
        }
        BatchRangeEndpoint::Exclusive if distance == 0 => 0,
        BatchRangeEndpoint::Exclusive => {
            distance / stride + if distance % stride == 0 { 0 } else { 1 }
        }
    };
    if count == 0 {
        return Err(BatchExpansionError::invalid("range produces no values"));
    }
    let count = usize::try_from(count)
        .map_err(|_| BatchExpansionError::invalid("range case count exceeds addressable size"))?;
    if count > max_cases {
        return Err(BatchExpansionError::invalid(format!(
            "range would create {count} cases, above max_cases={max_cases}"
        )));
    }

    let mut values = Vec::with_capacity(count);
    for index in 0..count {
        let index = i128::try_from(index)
            .map_err(|_| BatchExpansionError::invalid("range index exceeds decimal bounds"))?;
        let offset = step
            .checked_mul(index)
            .ok_or_else(|| BatchExpansionError::invalid("range value multiplication overflowed"))?;
        let coefficient = start
            .checked_add(offset)
            .ok_or_else(|| BatchExpansionError::invalid("range value addition overflowed"))?;
        values.push(Value::Number(
            DecimalValue::normalized(coefficient, scale).to_json_number()?,
        ));
    }
    Ok(values)
}

/// Expand an independent batch into stable child RunSpecifications.
///
/// Axis values remain in the typed case tuple until they are materialized into
/// a case-local StudyProblemCatalog. Cartesian axes multiply the current case
/// set; zip axes require an exact length match with the cases produced so far.
/// Case IDs derive from the batch ID and sorted canonical parameter tuple,
/// while child RunIds and case seeds derive from the case ID. The resulting
/// manifest digest binds the source run, axis bindings, seed policy,
/// concurrency cap, and all child RunSpecs.
pub fn expand_independent_batch(
    request: BatchExpansionRequest,
) -> Result<BatchExpansionManifest, BatchExpansionError> {
    validate_identifier(&request.batch_id, "batch_id")?;
    validate_identifier(&request.seed_name, "seed_name")?;

    if request.strategy != BatchExecutionStrategy::Independent {
        return Err(BatchExpansionError::invalid(
            "only independent strategy is currently supported by the pure expander",
        ));
    }
    if request.max_cases == 0 || request.max_cases > BATCH_EXPANSION_MAX_CASES {
        return Err(BatchExpansionError::invalid(format!(
            "max_cases must be between 1 and {BATCH_EXPANSION_MAX_CASES}"
        )));
    }
    if request.max_parallel_cases == Some(0) {
        return Err(BatchExpansionError::invalid(
            "max_parallel_cases must be positive when specified",
        ));
    }
    if request.axes.is_empty() {
        return Err(BatchExpansionError::invalid(
            "at least one parameter axis is required",
        ));
    }
    validate_axis_bindings(&request.axes)?;

    let source_run_sha256 = request.template.fingerprint()?;
    if !request.template.seeds.is_empty() {
        return Err(BatchExpansionError::invalid(
            "batch template must not contain unbound RunSpecification seeds",
        ));
    }
    if !request
        .template
        .parameters
        .as_object()
        .is_some_and(|parameters| parameters.is_empty())
    {
        return Err(BatchExpansionError::invalid(
            "batch template must not contain unbound RunSpecification parameters",
        ));
    }
    if request.template.dependencies.iter().any(is_batch_dependent) {
        return Err(BatchExpansionError::invalid(
            "independent expansion cannot inherit step-output or continuation dependencies",
        ));
    }
    let source_study_plan_sha256 = request.template.study.plan_sha256.clone();
    let source_study_catalog_sha256 = request.template.study_catalog_sha256.clone();

    let tuples = expand_axes(&request.axes, request.max_cases)?;
    let mut cases = Vec::with_capacity(tuples.len());
    for parameter_tuple in tuples {
        let case_id = case_id_for(&request.batch_id, &parameter_tuple);
        let mut specification = request.template.clone();
        specification.run_id = run_id_for_case(&case_id)?;
        let case_seed = derive_case_seed(request.master_seed, &request.seed_name, &case_id);
        specification
            .validate()
            .map_err(BatchExpansionError::from)?;
        cases.push(BatchCase {
            case_id,
            parameter_tuple,
            case_seed,
            specification,
        });
    }

    let mut manifest = BatchExpansionManifest {
        schema_version: BATCH_EXPANSION_MANIFEST_SCHEMA.to_string(),
        batch_id: request.batch_id,
        strategy: request.strategy,
        failure_policy: request.failure_policy,
        source_run_sha256,
        source_study_plan_sha256,
        source_study_catalog_sha256,
        axes: request.axes,
        master_seed: request.master_seed,
        seed_name: request.seed_name,
        max_parallel_cases: request.max_parallel_cases,
        cases,
        manifest_sha256: String::new(),
    };
    manifest.manifest_sha256 = manifest_digest(&manifest)?;
    manifest.validate_integrity()?;
    Ok(manifest)
}

/// Materialize one case's typed axis values and deterministic stochastic
/// seeds into an immutable case-local StudyPlan and StudyProblemCatalog.
/// Durable Submit can call this per case and persist the returned catalog by
/// digest before publishing its child RunSpecification.
pub fn materialize_independent_batch_case(
    manifest: &mut BatchExpansionManifest,
    case_id: &str,
    source_study: &StudyPlan,
    source_catalog: &StudyProblemCatalog,
) -> Result<MaterializedBatchCase, BatchExpansionError> {
    manifest.validate_integrity()?;
    let (source_plan_sha256, source_catalog_sha256) =
        validate_source_catalog(manifest, source_study, source_catalog)?;
    let case_index = manifest
        .cases
        .iter()
        .position(|case| case.case_id == case_id)
        .ok_or_else(|| BatchExpansionError::invalid(format!("unknown case `{case_id}`")))?;
    let materialized =
        materialize_batch_case_unchecked(manifest, case_index, source_study, source_catalog)?;
    validate_case_digest_binding(
        manifest,
        case_index,
        &materialized.specification,
        &source_plan_sha256,
        &source_catalog_sha256,
    )?;
    manifest.cases[case_index].specification = materialized.specification.clone();
    manifest.manifest_sha256 = manifest_digest(manifest)?;
    manifest.validate_integrity()?;
    Ok(materialized)
}

/// Return a case snapshot with the resolved batch output policy captured in
/// every child ProblemIR. This remains a pure application transformation:
/// callers can persist the returned Study/catalog by digest before publishing
/// the matching RunSpecification.
pub fn bind_batch_case_output_storage(
    materialized: &MaterializedBatchCase,
    output_storage: &OutputStorageIR,
) -> Result<MaterializedBatchCase, BatchExpansionError> {
    output_storage
        .validate()
        .map_err(|errors| BatchExpansionError::invalid(errors.join("; ")))?;
    let output_dir = output_storage.output_dir.as_deref().ok_or_else(|| {
        BatchExpansionError::invalid("output_storage.output_dir must be present and absolute")
    })?;
    if !Path::new(output_dir).is_absolute() {
        return Err(BatchExpansionError::invalid(
            "output_storage.output_dir must be absolute",
        ));
    }
    if let Some(temp_dir) = output_storage.temp_dir.as_deref() {
        if !Path::new(temp_dir).is_absolute() {
            return Err(BatchExpansionError::invalid(
                "output_storage.temp_dir must be absolute when specified",
            ));
        }
    }

    let serialized_storage = serde_json::to_value(output_storage).map_err(|error| {
        BatchExpansionError::invalid(format!("OutputStorageIR serialization failed: {error}"))
    })?;
    let mut replacements = BTreeMap::<String, ProblemIR>::new();
    let mut captured_source_ids = BTreeMap::new();
    for entry in materialized.catalog.entries() {
        let step_id = entry.step_id().to_string();
        let mut problem = entry.problem().clone();
        problem
            .problem_meta
            .runtime_metadata
            .insert("output_storage".into(), serialized_storage.clone());
        problem
            .problem_meta
            .runtime_metadata
            .remove("output_storage_source_dir");

        if entry.captured_input_identity().is_none() {
            let identity = serde_json::json!({
                "policy": "batch-case-input-source.v1",
                "case_id": materialized.case_id.as_str(),
                "step_id": step_id.as_str(),
            });
            captured_source_ids.insert(
                step_id.clone(),
                format!("batch-input:{}", digest_json(&identity)),
            );
        }
        replacements.insert(step_id, problem);
    }

    let (study, catalog) = materialized
        .catalog
        .with_problem_replacements(&materialized.study, &replacements, &captured_source_ids)
        .map_err(|error| BatchExpansionError::invalid(error.to_string()))?;
    let execution_plan = fullmag_plan::lower_study_plan_with_catalog(&study, &catalog)
        .map_err(|error| BatchExpansionError::invalid(error.to_string()))?;
    let study_sha256 = study
        .canonical_sha256()
        .map_err(|error| BatchExpansionError::invalid(error.to_string()))?;
    let study_catalog_sha256 = catalog_sha256(&catalog)?;

    let mut specification = materialized.specification.clone();
    specification.study.plan_version = study.schema_version.clone();
    specification.study.plan_sha256 = study_sha256;
    specification.study_catalog_sha256 = study_catalog_sha256;
    specification
        .validate()
        .map_err(BatchExpansionError::from)?;

    Ok(MaterializedBatchCase {
        case_id: materialized.case_id.clone(),
        specification,
        study,
        catalog,
        execution_plan,
    })
}

/// Materialize and validate every case without rewriting the manifest after
/// each item. Submit uses this bounded pass to reject invalid planner inputs
/// before accepting the parent while keeping the work linear in case count.
pub fn validate_independent_batch_cases<F>(
    manifest: &BatchExpansionManifest,
    source_study: &StudyPlan,
    source_catalog: &StudyProblemCatalog,
    mut validate_case: F,
) -> Result<(), BatchExpansionError>
where
    F: FnMut(&MaterializedBatchCase) -> std::result::Result<(), String>,
{
    manifest.validate_integrity()?;
    let (source_plan_sha256, source_catalog_sha256) =
        validate_source_catalog(manifest, source_study, source_catalog)?;
    for case_index in 0..manifest.cases.len() {
        let materialized =
            materialize_batch_case_unchecked(manifest, case_index, source_study, source_catalog)?;
        validate_case_digest_binding(
            manifest,
            case_index,
            &materialized.specification,
            &source_plan_sha256,
            &source_catalog_sha256,
        )?;
        validate_case(&materialized).map_err(BatchExpansionError::invalid)?;
    }
    Ok(())
}

fn validate_source_catalog(
    manifest: &BatchExpansionManifest,
    source_study: &StudyPlan,
    source_catalog: &StudyProblemCatalog,
) -> Result<(String, String), BatchExpansionError> {
    source_catalog
        .validate_for(source_study)
        .map_err(|error| BatchExpansionError::invalid(error.to_string()))?;
    let source_plan_sha256 = source_study
        .canonical_sha256()
        .map_err(|error| BatchExpansionError::invalid(error.to_string()))?;
    let source_catalog_sha256 = catalog_sha256(source_catalog)?;
    if source_plan_sha256 != manifest.source_study_plan_sha256
        || source_catalog_sha256 != manifest.source_study_catalog_sha256
    {
        return Err(BatchExpansionError::invalid(
            "source StudyPlan or StudyProblemCatalog digest differs from the batch snapshot",
        ));
    }
    Ok((source_plan_sha256, source_catalog_sha256))
}

fn validate_case_digest_binding(
    manifest: &BatchExpansionManifest,
    case_index: usize,
    specification: &RunSpecification,
    source_plan_sha256: &str,
    source_catalog_sha256: &str,
) -> Result<(), BatchExpansionError> {
    let current_specification = &manifest.cases[case_index].specification;
    let is_source_bound = current_specification.study.plan_sha256.as_str() == source_plan_sha256
        && current_specification.study_catalog_sha256.as_str() == source_catalog_sha256;
    let is_case_bound = current_specification.study.plan_sha256 == specification.study.plan_sha256
        && current_specification.study_catalog_sha256 == specification.study_catalog_sha256;
    if !is_source_bound && !is_case_bound {
        return Err(BatchExpansionError::invalid(format!(
            "case `{}` has conflicting materialized Study/catalog digests",
            manifest.cases[case_index].case_id
        )));
    }
    Ok(())
}

fn materialize_batch_case_unchecked(
    manifest: &BatchExpansionManifest,
    case_index: usize,
    source_study: &StudyPlan,
    source_catalog: &StudyProblemCatalog,
) -> Result<MaterializedBatchCase, BatchExpansionError> {
    let case = manifest.cases[case_index].clone();
    if case.specification.study.study_id.as_str() != source_study.study_id.as_str()
        || case.specification.study.plan_version != source_study.schema_version
    {
        return Err(BatchExpansionError::invalid(format!(
            "case `{}` RunSpecification references a different Study identity or version",
            case.case_id
        )));
    }

    let mut replacements = BTreeMap::<String, ProblemIR>::new();
    for entry in source_catalog.entries() {
        let mut problem = entry.problem().clone();
        if apply_case_seed(&mut problem, case.case_seed, entry.step_id())? {
            replacements.insert(entry.step_id().to_string(), problem);
        }
    }

    for axis in &manifest.axes {
        let value = case
            .parameter_tuple
            .get(&axis.name)
            .and_then(Value::as_f64)
            .filter(|value| value.is_finite())
            .ok_or_else(|| {
                BatchExpansionError::invalid(format!(
                    "case `{}` axis `{}` does not contain a finite number",
                    case.case_id, axis.name
                ))
            })?;
        let step_id = match &axis.target {
            BatchAxisTarget::ExternalFieldB { step_id, .. }
            | BatchAxisTarget::ZhangLiCurrentDensity { step_id, .. } => step_id,
        };
        let problem = match replacements.entry(step_id.clone()) {
            std::collections::btree_map::Entry::Occupied(entry) => entry.into_mut(),
            std::collections::btree_map::Entry::Vacant(entry) => {
                let source = source_catalog
                    .entries()
                    .iter()
                    .find(|candidate| candidate.step_id() == step_id.as_str())
                    .ok_or_else(|| {
                        BatchExpansionError::invalid(format!(
                            "axis `{}` targets missing Study step `{step_id}`",
                            axis.name
                        ))
                    })?;
                entry.insert(source.problem().clone())
            }
        };
        match &axis.target {
            BatchAxisTarget::ExternalFieldB { direction, .. } => {
                apply_external_field_b(problem, *direction, value, &axis.name)?;
            }
            BatchAxisTarget::ZhangLiCurrentDensity {
                module_id,
                direction,
                ..
            } => apply_zhang_li_current_density(problem, module_id, *direction, value, &axis.name)?,
        }
    }

    let mut captured_source_ids = BTreeMap::new();
    for step_id in replacements.keys() {
        let entry = source_catalog
            .entries()
            .iter()
            .find(|candidate| candidate.step_id() == step_id.as_str())
            .ok_or_else(|| {
                BatchExpansionError::invalid(format!(
                    "replacement step `{step_id}` is missing from the source catalog"
                ))
            })?;
        if entry.captured_input_identity().is_none() {
            let identity = serde_json::json!({
                "policy": "batch-case-input-source.v1",
                "batch_id": manifest.batch_id,
                "case_id": case.case_id,
                "step_id": step_id,
            });
            captured_source_ids.insert(
                step_id.clone(),
                format!("batch-input:{}", digest_json(&identity)),
            );
        }
    }

    let (study, catalog) = source_catalog
        .with_problem_replacements(source_study, &replacements, &captured_source_ids)
        .map_err(|error| BatchExpansionError::invalid(error.to_string()))?;
    let execution_plan = fullmag_plan::lower_study_plan_with_catalog(&study, &catalog)
        .map_err(|error| BatchExpansionError::invalid(error.to_string()))?;
    let study_sha256 = study
        .canonical_sha256()
        .map_err(|error| BatchExpansionError::invalid(error.to_string()))?;
    let catalog_sha256 = catalog_sha256(&catalog)?;

    let mut specification = case.specification.clone();
    specification.study.plan_version = study.schema_version.clone();
    specification.study.plan_sha256 = study_sha256;
    specification.study_catalog_sha256 = catalog_sha256;
    specification
        .validate()
        .map_err(BatchExpansionError::from)?;

    Ok(MaterializedBatchCase {
        case_id: case.case_id,
        specification,
        study,
        catalog,
        execution_plan,
    })
}

fn catalog_sha256(catalog: &StudyProblemCatalog) -> Result<String, BatchExpansionError> {
    let value = serde_json::to_value(catalog).map_err(|error| {
        BatchExpansionError::invalid(format!("StudyProblemCatalog serialization failed: {error}"))
    })?;
    Ok(digest_json(&value))
}

fn apply_case_seed(
    problem: &mut ProblemIR,
    case_seed: u64,
    step_id: &str,
) -> Result<bool, BatchExpansionError> {
    let has_thermal_noise = problem
        .energy_terms
        .iter()
        .any(|term| matches!(term, EnergyTermIR::ThermalNoise { .. }));
    if problem
        .temperature
        .is_some_and(|temperature| temperature > 0.0)
        && !has_thermal_noise
    {
        return Err(BatchExpansionError::invalid(format!(
            "Study step `{step_id}` uses legacy temperature without an explicit ThermalNoise seed binding"
        )));
    }

    let mut changed = false;
    for (index, term) in problem.energy_terms.iter_mut().enumerate() {
        if let EnergyTermIR::ThermalNoise { seed, .. } = term {
            *seed = Some(derive_component_seed(
                case_seed,
                step_id,
                "thermal_noise",
                &index.to_string(),
            ));
            changed = true;
        }
    }
    for (index, magnet) in problem.magnets.iter_mut().enumerate() {
        let component_id = format!(
            "{}:{index}",
            magnet.object_id.as_deref().unwrap_or(magnet.name.as_str())
        );
        if let Some(InitialMagnetizationIR::RandomSeeded { seed }) =
            &mut magnet.initial_magnetization
        {
            *seed =
                derive_component_seed(case_seed, step_id, "initial_magnetization", &component_id);
            changed = true;
        }
    }
    Ok(changed)
}

fn derive_component_seed(case_seed: u64, step_id: &str, kind: &str, identity: &str) -> u64 {
    let value = serde_json::json!({
        "policy": "batch-stochastic-component-seed.v1",
        "case_seed": case_seed,
        "step_id": step_id,
        "kind": kind,
        "identity": identity,
    });
    let digest = Sha256::digest(canonical_json_bytes(&value));
    u64::from_be_bytes(
        digest[..8]
            .try_into()
            .expect("SHA-256 has at least 8 bytes"),
    )
    .max(1)
}

fn apply_external_field_b(
    problem: &mut ProblemIR,
    direction: [f64; 3],
    magnitude_t: f64,
    axis_name: &str,
) -> Result<(), BatchExpansionError> {
    let normalized_direction = normalized_axis_direction(direction, axis_name)?;
    let field_b = normalized_direction.map(|component| component * magnitude_t);
    let zeeman_count = problem
        .energy_terms
        .iter()
        .filter(|term| matches!(term, EnergyTermIR::Zeeman { .. }))
        .count();
    if zeeman_count > 1 {
        return Err(BatchExpansionError::invalid(format!(
            "axis `{axis_name}` cannot bind a ProblemIR with multiple Zeeman terms"
        )));
    }
    if let Some(index) = problem
        .energy_terms
        .iter()
        .position(|term| matches!(term, EnergyTermIR::Zeeman { .. }))
    {
        let EnergyTermIR::Zeeman { b } = &mut problem.energy_terms[index] else {
            unreachable!("Zeeman index must point at an EnergyTermIR::Zeeman")
        };
        *b = field_b;
    } else {
        problem
            .energy_terms
            .push(EnergyTermIR::Zeeman { b: field_b });
    }
    Ok(())
}

fn apply_zhang_li_current_density(
    problem: &mut ProblemIR,
    module_id: &str,
    direction: [f64; 3],
    magnitude_apm2: f64,
    axis_name: &str,
) -> Result<(), BatchExpansionError> {
    let normalized_direction = normalized_axis_direction(direction, axis_name)?;
    let current_density = normalized_direction.map(|component| component * magnitude_apm2);
    ensure_spin_torque_module_active(problem, module_id, axis_name)?;

    let matching_modules = problem
        .spin_torque_modules
        .iter()
        .enumerate()
        .filter_map(|(index, module)| match module {
            SpinTorqueModuleIR::ZhangLi { id: Some(id), .. } if id == module_id => Some(index),
            _ => None,
        })
        .collect::<Vec<_>>();
    if matching_modules.len() != 1 {
        return Err(BatchExpansionError::invalid(format!(
            "axis `{axis_name}` requires exactly one Zhang-Li module `{module_id}` in the targeted Study step"
        )));
    }

    let legacy_has_current_density = problem.current_density.is_some();
    let SpinTorqueModuleIR::ZhangLi {
        current_density: module_current_density,
        current_source,
        ..
    } = &mut problem.spin_torque_modules[matching_modules[0]]
    else {
        unreachable!("matched Zhang-Li module index must point at ZhangLi")
    };
    if current_source.is_some() {
        return Err(BatchExpansionError::invalid(format!(
            "axis `{axis_name}` cannot replace a Zhang-Li current_source binding"
        )));
    }
    *module_current_density = Some(current_density);
    if legacy_has_current_density {
        problem.current_density = Some(current_density);
    }
    Ok(())
}

fn ensure_spin_torque_module_active(
    problem: &ProblemIR,
    module_id: &str,
    axis_name: &str,
) -> Result<(), BatchExpansionError> {
    let Some(graph) = &problem.physics_graph else {
        return Ok(());
    };
    let modules = graph
        .get("modules")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            BatchExpansionError::invalid(format!(
                "axis `{axis_name}` cannot resolve spin-torque activation in the Study step's physics_graph"
            ))
        })?;
    let matching = modules
        .iter()
        .filter(|module| {
            module.get("kind").and_then(Value::as_str) == Some("spin_torque")
                && module.get("id").and_then(Value::as_str) == Some(module_id)
        })
        .collect::<Vec<_>>();
    if matching.len() != 1
        || !matches!(
            matching[0].get("activation").and_then(Value::as_str),
            Some("active" | "configured")
        )
    {
        return Err(BatchExpansionError::invalid(format!(
            "axis `{axis_name}` targets Zhang-Li module `{module_id}` that is missing, ambiguous, or not executable"
        )));
    }
    Ok(())
}

fn normalized_axis_direction(
    direction: [f64; 3],
    axis_name: &str,
) -> Result<[f64; 3], BatchExpansionError> {
    let norm = direction
        .iter()
        .fold(0.0_f64, |norm, component| norm.hypot(*component));
    if !norm.is_finite() || norm == 0.0 {
        return Err(BatchExpansionError::invalid(format!(
            "axis `{axis_name}` direction must be finite and nonzero"
        )));
    }
    Ok(direction.map(|component| component / norm))
}

fn validate_axis_bindings(axes: &[BatchAxis]) -> Result<(), BatchExpansionError> {
    let mut names = HashSet::new();
    let mut targets = HashSet::new();
    for axis in axes {
        validate_identifier(&axis.name, "axis.name")?;
        if !names.insert(axis.name.as_str()) {
            return Err(BatchExpansionError::invalid(format!(
                "axis name `{}` is duplicated",
                axis.name
            )));
        }
        match &axis.target {
            BatchAxisTarget::ExternalFieldB { step_id, direction } => {
                validate_identifier(step_id, "axis.target.step_id")?;
                if axis.value_kind != BatchAxisValueKind::Number || axis.canonical_unit != "T" {
                    return Err(BatchExpansionError::invalid(format!(
                        "axis `{}` external_field_b target requires numeric values in canonical unit T",
                        axis.name
                    )));
                }
                normalized_axis_direction(*direction, &axis.name)?;
                if !targets.insert(format!("external_field_b:{step_id}")) {
                    return Err(BatchExpansionError::invalid(format!(
                        "multiple batch axes target external_field_b for Study step `{step_id}`"
                    )));
                }
            }
            BatchAxisTarget::ZhangLiCurrentDensity {
                step_id,
                module_id,
                direction,
            } => {
                validate_identifier(step_id, "axis.target.step_id")?;
                validate_identifier(module_id, "axis.target.module_id")?;
                if axis.value_kind != BatchAxisValueKind::Number || axis.canonical_unit != "A/m^2" {
                    return Err(BatchExpansionError::invalid(format!(
                        "axis `{}` zhang_li_current_density target requires numeric values in canonical unit A/m^2",
                        axis.name
                    )));
                }
                normalized_axis_direction(*direction, &axis.name)?;
                let binding_key = format!("zhang_li_current_density:{step_id}:{module_id}");
                if !targets.insert(binding_key) {
                    return Err(BatchExpansionError::invalid(format!(
                        "multiple batch axes target Zhang-Li module `{module_id}` in Study step `{step_id}`"
                    )));
                }
            }
        }
    }
    Ok(())
}

fn is_batch_dependent(dependency: &crate::RunDependency) -> bool {
    matches!(
        dependency,
        crate::RunDependency::StepOutput { .. } | crate::RunDependency::ExplicitContinuation { .. }
    )
}

fn case_id_for(batch_id: &str, parameter_tuple: &BTreeMap<String, Value>) -> String {
    let case_identity = serde_json::json!({
        "schema_version": BATCH_EXPANSION_MANIFEST_SCHEMA,
        "batch_id": batch_id,
        "parameter_tuple": parameter_tuple,
    });
    format!("case-{}", digest_json(&case_identity))
}

fn run_id_for_case(case_id: &str) -> Result<RunId, BatchExpansionError> {
    let digest = case_id
        .strip_prefix("case-")
        .ok_or_else(|| BatchExpansionError::invalid("case_id must have the `case-` prefix"))?;
    if digest.len() != 64
        || !digest
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err(BatchExpansionError::invalid(
            "case_id must contain a lowercase SHA-256 digest",
        ));
    }
    Ok(RunId::parse(format!("run-batch-{digest}"))?)
}

fn expand_axes(
    axes: &[BatchAxis],
    max_cases: usize,
) -> Result<Vec<BTreeMap<String, Value>>, BatchExpansionError> {
    let mut names = BTreeSet::new();
    let mut tuples = vec![BTreeMap::new()];

    for (axis_index, axis) in axes.iter().enumerate() {
        validate_identifier(&axis.name, "axis.name")?;
        if !names.insert(axis.name.as_str()) {
            return Err(BatchExpansionError::invalid(format!(
                "duplicate axis `{}`",
                axis.name
            )));
        }
        if axis.canonical_unit.trim().is_empty()
            || axis.canonical_unit.len() > 128
            || axis.canonical_unit.chars().any(char::is_control)
        {
            return Err(BatchExpansionError::invalid(format!(
                "axis `{}` canonical_unit must be non-empty, at most 128 UTF-8 bytes, and contain no control characters",
                axis.name
            )));
        }
        let values = axis.values.expand_values(axis.value_kind, max_cases)?;
        if values.is_empty() {
            return Err(BatchExpansionError::invalid(format!(
                "axis `{}` has no values",
                axis.name
            )));
        }
        if axis_index == 0 && axis.join != BatchAxisJoin::Cartesian {
            return Err(BatchExpansionError::invalid(
                "the first axis must use cartesian join",
            ));
        }

        let mut seen_values = HashSet::new();
        for value in &values {
            if !matches_axis_kind(value, axis.value_kind) {
                return Err(BatchExpansionError::invalid(format!(
                    "axis `{}` contains a value that does not match {:?}",
                    axis.name, axis.value_kind
                )));
            }
            if !seen_values.insert(canonical_json_bytes(value)) {
                return Err(BatchExpansionError::invalid(format!(
                    "axis `{}` contains a duplicate canonical value",
                    axis.name
                )));
            }
        }

        match axis.join {
            BatchAxisJoin::Cartesian => {
                let expanded_count = tuples
                    .len()
                    .checked_mul(values.len())
                    .ok_or_else(|| BatchExpansionError::invalid("case count overflow"))?;
                if expanded_count > max_cases {
                    return Err(BatchExpansionError::invalid(format!(
                        "expansion would create {expanded_count} cases, above max_cases={max_cases}"
                    )));
                }
                let mut expanded = Vec::with_capacity(expanded_count);
                for tuple in tuples {
                    for value in &values {
                        let mut next = tuple.clone();
                        next.insert(axis.name.clone(), value.clone());
                        expanded.push(next);
                    }
                }
                tuples = expanded;
            }
            BatchAxisJoin::Zip => {
                if tuples.len() != values.len() {
                    return Err(BatchExpansionError::invalid(format!(
                        "zip axis `{}` has {} values but the preceding axes produced {} cases",
                        axis.name,
                        values.len(),
                        tuples.len()
                    )));
                }
                for (tuple, value) in tuples.iter_mut().zip(&values) {
                    tuple.insert(axis.name.clone(), value.clone());
                }
            }
        }
    }

    if tuples.len() > max_cases {
        return Err(BatchExpansionError::invalid(format!(
            "expansion would create {} cases, above max_cases={max_cases}",
            tuples.len()
        )));
    }
    Ok(tuples)
}

fn matches_axis_kind(value: &Value, kind: BatchAxisValueKind) -> bool {
    match kind {
        BatchAxisValueKind::Boolean => value.is_boolean(),
        BatchAxisValueKind::Integer => value
            .as_number()
            .is_some_and(|number| number.as_i64().is_some() || number.as_u64().is_some()),
        BatchAxisValueKind::Number => value.is_number(),
        BatchAxisValueKind::String => value.is_string(),
    }
}

fn derive_case_seed(master_seed: u64, seed_name: &str, case_id: &str) -> u64 {
    let value = serde_json::json!({
        "policy": BATCH_SEED_POLICY,
        "master_seed": master_seed,
        "seed_name": seed_name,
        "case_id": case_id,
    });
    let digest = Sha256::digest(canonical_json_bytes(&value));
    u64::from_be_bytes(
        digest[..8]
            .try_into()
            .expect("SHA-256 has at least 8 bytes"),
    )
    .max(1)
}

fn manifest_digest(manifest: &BatchExpansionManifest) -> Result<String, BatchExpansionError> {
    let mut value = serde_json::to_value(manifest).map_err(|error| {
        BatchExpansionError::invalid(format!("manifest serialization failed: {error}"))
    })?;
    if let Value::Object(object) = &mut value {
        object.remove("manifest_sha256");
    }
    Ok(digest_json(&value))
}

fn digest_json(value: &Value) -> String {
    format!("{:x}", Sha256::digest(canonical_json_bytes(value)))
}

fn validate_sha256(value: &str, field: &str) -> Result<(), BatchExpansionError> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err(BatchExpansionError::invalid(format!(
            "{field} must be a lowercase 64-character SHA-256 digest"
        )));
    }
    Ok(())
}

fn validate_identifier(value: &str, field: &str) -> Result<(), BatchExpansionError> {
    if value.is_empty()
        || value.trim() != value
        || value.len() > 256
        || value
            .chars()
            .any(|character| character.is_control() || matches!(character, '/' | '\\'))
    {
        return Err(BatchExpansionError::invalid(format!(
            "{field} must be a non-empty portable identifier"
        )));
    }
    Ok(())
}

#[cfg(test)]
#[path = "batch_expansion_tests.rs"]
mod tests;
