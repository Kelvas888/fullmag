//! Material-owned local energy must not require an unrelated global interaction.
use fullmag_ir::{BackendPlanIR, BackendTarget, ProblemIR};
use fullmag_plan::plan;

fn local_only_problem() -> ProblemIR {
    let mut problem = ProblemIR::bootstrap_example();
    problem.energy_terms.clear();
    problem.backend_policy.requested_backend = BackendTarget::Fdm;
    problem.study.sampling_mut().outputs.clear();
    problem.problem_meta.runtime_metadata.insert(
        "runtime_selection".into(),
        serde_json::json!({"backend":"fdm", "device":"cpu"}),
    );
    problem
}

fn assert_missing_local_energy(problem: &ProblemIR) {
    let error = plan(problem).expect_err("a model without a realized interaction must fail");
    assert!(error.reasons.iter().any(|reason| reason
        .contains("or nonzero anisotropy in a referenced material")
        || reason.contains("at least one interaction or material anisotropy is required")));
}

#[test]
fn single_grid_accepts_material_uniaxial_without_global_energy_terms() {
    for ku1 in [1000.0, -1000.0] {
        let mut problem = local_only_problem();
        problem.materials[0].uniaxial_anisotropy = Some(ku1);
        problem.materials[0].anisotropy_axis = Some([0.0, 0.0, 1.0]);
        let planned = plan(&problem).expect("material anisotropy is an executable local field");
        let BackendPlanIR::Fdm(fdm) = planned.backend_plan else {
            panic!("expected the requested single-grid FDM plan");
        };
        assert!(!fdm.enable_exchange && !fdm.enable_demag);
        assert!(fdm.external_field.is_none());
        assert_eq!(fdm.material.uniaxial_anisotropy_ku1, Some(ku1));
        assert_eq!(fdm.material.anisotropy_axis, Some([0.0, 0.0, 1.0]));
    }
}

#[test]
fn single_grid_accepts_second_order_and_cubic_local_energy() {
    let mut problem = local_only_problem();
    problem.materials[0].uniaxial_anisotropy = Some(0.0);
    problem.materials[0].uniaxial_anisotropy_k2 = Some(1000.0);
    problem.materials[0].anisotropy_axis = Some([0.0, 0.0, 1.0]);
    assert!(plan(&problem).is_ok());
    problem.materials[0].uniaxial_anisotropy = None;
    problem.materials[0].uniaxial_anisotropy_k2 = None;
    problem.materials[0].cubic_anisotropy_kc1 = Some(1000.0);
    problem.materials[0].cubic_anisotropy_axis1 = Some([1.0, 0.0, 0.0]);
    problem.materials[0].cubic_anisotropy_axis2 = Some([0.0, 1.0, 0.0]);
    assert!(plan(&problem).is_ok());
}

#[test]
fn absent_zero_or_unreferenced_anisotropy_does_not_admit_empty_physics() {
    let mut problem = local_only_problem();
    assert_missing_local_energy(&problem);
    problem.materials[0].uniaxial_anisotropy = Some(0.0);
    problem.materials[0].anisotropy_axis = Some([0.0, 0.0, 1.0]);
    assert_missing_local_energy(&problem);
    let mut unused = problem.materials[0].clone();
    unused.name = "unused".into();
    unused.uniaxial_anisotropy = Some(1000.0);
    problem.materials.push(unused);
    assert_missing_local_energy(&problem);
}

#[test]
fn incomplete_or_nonfinite_local_coefficients_do_not_satisfy_admission() {
    let mut problem = local_only_problem();
    problem.materials[0].uniaxial_anisotropy_k2 = Some(1000.0);
    problem.materials[0].anisotropy_axis = Some([0.0, 0.0, 1.0]);
    assert_missing_local_energy(&problem);
    problem.materials[0].uniaxial_anisotropy_k2 = None;
    problem.materials[0].cubic_anisotropy_kc1 = Some(1000.0);
    problem.materials[0].cubic_anisotropy_kc2 = Some(f64::NAN);
    problem.materials[0].cubic_anisotropy_axis1 = Some([1.0, 0.0, 0.0]);
    problem.materials[0].cubic_anisotropy_axis2 = Some([0.0, 1.0, 0.0]);
    assert_missing_local_energy(&problem);
}

#[test]
fn invalid_axes_do_not_admit_local_only_anisotropy() {
    let mut problem = local_only_problem();
    problem.materials[0].uniaxial_anisotropy = Some(1000.0);
    for axis in [[0.0; 3], [f64::NAN, 0.0, 1.0], [f64::INFINITY, 0.0, 1.0]] {
        problem.materials[0].anisotropy_axis = Some(axis);
        assert_missing_local_energy(&problem);
    }
    problem.materials[0].uniaxial_anisotropy = None;
    problem.materials[0].cubic_anisotropy_kc1 = Some(1000.0);
    problem.materials[0].cubic_anisotropy_axis1 = Some([1.0, 0.0, 0.0]);
    problem.materials[0].cubic_anisotropy_axis2 = Some([2.0, 0.0, 0.0]);
    assert_missing_local_energy(&problem);
}
