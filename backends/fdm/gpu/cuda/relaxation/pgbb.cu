/*
 * pgbb.cu — device-resident projected-gradient Barzilai-Borwein minimizer.
 *
 * docs/physics/0500-fdm-relaxation-algorithms.md §3.1.2 (algorithm) and §3.1.7
 * (this realization). The host loop in crates/fullmag-runner/src/relaxation/
 * direct_minimizer.rs is the reference: same retraction, chord, Armijo test,
 * backtracking and BB step rule. Every vector stays on the device; only control
 * scalars (energies, products, a validity flag) are copied to the host.
 */

#include "context.hpp"
#include "../integrators/fsal_policy.hpp"
#include <cuda_runtime.h>
#include <cfloat>
#include <cmath>
#include <limits>
#include <mutex>
#include <utility>

namespace fullmag {
namespace fdm {

extern void set_cuda_error(Context &ctx, const char *operation, cudaError_t err);

extern void launch_exchange_field_fp32(Context &ctx);
extern void launch_demag_field_fp32(Context &ctx);
extern void launch_effective_field_fp32(Context &ctx, double evaluation_time);
extern double launch_exchange_energy_fp32(Context &ctx);
extern double launch_demag_energy_fp32(Context &ctx);
extern double launch_external_energy_fp32(Context &ctx);
extern double reduce_uniaxial_anisotropy_energy_fp32(Context &ctx);
extern double reduce_cubic_anisotropy_energy_fp32(Context &ctx);
extern double reduce_dmi_energy_fp32(Context &ctx);
extern void launch_exchange_field_fp64(Context &ctx);
extern void launch_demag_field_fp64(Context &ctx);
extern void launch_effective_field_fp64(Context &ctx, double evaluation_time);
extern double launch_exchange_energy_fp64(Context &ctx);
extern double launch_demag_energy_fp64(Context &ctx);
extern double launch_external_energy_fp64(Context &ctx);
extern double reduce_uniaxial_anisotropy_energy_fp64(Context &ctx);
extern double reduce_cubic_anisotropy_energy_fp64(Context &ctx);
extern double reduce_dmi_energy_fp64(Context &ctx);
double reduce_max_norm_fp32(Context &ctx, const void *vx, const void *vy, const void *vz, uint64_t n);
double reduce_max_norm_fp64(Context &ctx, const void *vx, const void *vy, const void *vz, uint64_t n);
double reduce_max_cross_norm_fp32(Context &ctx,
    const void *ax, const void *ay, const void *az,
    const void *bx, const void *by, const void *bz, uint64_t n);
double reduce_max_cross_norm_fp64(Context &ctx,
    const void *ax, const void *ay, const void *az,
    const void *bx, const void *by, const void *bz, uint64_t n);

namespace {

constexpr double MU0 = 4.0 * kFullmagPi * 1e-7;
constexpr int BLOCK = 256;
constexpr uint64_t MAX_BLOCKS = 4096;

template <typename S>
struct Field {
    S *x;
    S *y;
    S *z;
};

template <typename S>
Field<S> as_field(const DeviceVectorField &field) {
    return {static_cast<S *>(field.x), static_cast<S *>(field.y), static_cast<S *>(field.z)};
}

template <typename S> __device__ __forceinline__ S tiny_norm_sq();
template <> __device__ __forceinline__ float tiny_norm_sq<float>() { return FLT_MIN; }
template <> __device__ __forceinline__ double tiny_norm_sq<double>() { return DBL_MIN; }
template <typename S> __device__ __forceinline__ S quiet_nan();
template <> __device__ __forceinline__ float quiet_nan<float>() { return nanf(""); }
template <> __device__ __forceinline__ double quiet_nan<double>() { return nan(""); }

__device__ __forceinline__ bool cell_active(const uint8_t *active, int has_active, uint64_t i) {
    return has_active == 0 || active[i] != 0;
}

// g = -(H - (m.H / |m|^2) m), the host `tangent_gradient_from_field`.
template <typename S>
__global__ void tangent_gradient_kernel(
    Field<S> m, Field<S> h, Field<S> g, const uint8_t *active, int has_active, uint64_t n)
{
    for (uint64_t i = blockIdx.x * static_cast<uint64_t>(blockDim.x) + threadIdx.x; i < n;
         i += static_cast<uint64_t>(gridDim.x) * blockDim.x) {
        if (!cell_active(active, has_active, i)) {
            g.x[i] = S(0); g.y[i] = S(0); g.z[i] = S(0);
            continue;
        }
        const S mx = m.x[i], my = m.y[i], mz = m.z[i];
        const S hx = h.x[i], hy = h.y[i], hz = h.z[i];
        const S norm_sq = mx * mx + my * my + mz * mz;
        if (!isfinite(norm_sq) || norm_sq <= tiny_norm_sq<S>()) {
            const S nan = quiet_nan<S>();
            g.x[i] = nan; g.y[i] = nan; g.z[i] = nan;
            continue;
        }
        const S c = (mx * hx + my * hy + mz * hz) / norm_sq;
        g.x[i] = -(hx - c * mx);
        g.y[i] = -(hy - c * my);
        g.z[i] = -(hz - c * mz);
    }
}

// m_t = normalize(m_prev - lambda g); a degenerate cell raises the flag.
template <typename S>
__global__ void retract_kernel(
    Field<S> m_prev, Field<S> g, double lambda, Field<S> m_out,
    const uint8_t *active, int has_active, int *invalid, uint64_t n)
{
    const S step = static_cast<S>(lambda);
    for (uint64_t i = blockIdx.x * static_cast<uint64_t>(blockDim.x) + threadIdx.x; i < n;
         i += static_cast<uint64_t>(gridDim.x) * blockDim.x) {
        if (!cell_active(active, has_active, i)) {
            m_out.x[i] = S(0); m_out.y[i] = S(0); m_out.z[i] = S(0);
            continue;
        }
        const S vx = m_prev.x[i] - step * g.x[i];
        const S vy = m_prev.y[i] - step * g.y[i];
        const S vz = m_prev.z[i] - step * g.z[i];
        const S norm_sq = vx * vx + vy * vy + vz * vz;
        if (!isfinite(norm_sq) || norm_sq <= tiny_norm_sq<S>()) {
            atomicExch(invalid, 1);
            m_out.x[i] = m_prev.x[i]; m_out.y[i] = m_prev.y[i]; m_out.z[i] = m_prev.z[i];
            continue;
        }
        const S inv = S(1) / sqrt(norm_sq);
        m_out.x[i] = vx * inv;
        m_out.y[i] = vy * inv;
        m_out.z[i] = vz * inv;
    }
}

__device__ __forceinline__ double cell_weight(
    const double *volume_fraction, int has_vf, const uint8_t *active, int has_active, uint64_t i)
{
    if (!cell_active(active, has_active, i)) return 0.0;
    return has_vf ? volume_fraction[i] : 1.0;
}

__device__ __forceinline__ void block_sum_store(double value, double *block_out) {
    __shared__ double shared[BLOCK];
    shared[threadIdx.x] = value;
    __syncthreads();
    for (int offset = blockDim.x / 2; offset > 0; offset >>= 1) {
        if (threadIdx.x < offset) shared[threadIdx.x] += shared[threadIdx.x + offset];
        __syncthreads();
    }
    if (threadIdx.x == 0) block_out[blockIdx.x] = shared[0];
}

// sum_i coeff phi_i a_i . (b_i - c_i); c may be null (then c = 0).
template <typename S>
__global__ void metric_dot_blocks_kernel(
    Field<S> a, Field<S> b, Field<S> c, int has_c,
    const double *volume_fraction, int has_vf, const uint8_t *active, int has_active,
    double coeff, double *block_out, uint64_t n)
{
    double sum = 0.0;
    for (uint64_t i = blockIdx.x * static_cast<uint64_t>(blockDim.x) + threadIdx.x; i < n;
         i += static_cast<uint64_t>(gridDim.x) * blockDim.x) {
        const double w = cell_weight(volume_fraction, has_vf, active, has_active, i);
        if (w == 0.0) continue;
        double bx = static_cast<double>(b.x[i]);
        double by = static_cast<double>(b.y[i]);
        double bz = static_cast<double>(b.z[i]);
        if (has_c) {
            bx -= static_cast<double>(c.x[i]);
            by -= static_cast<double>(c.y[i]);
            bz -= static_cast<double>(c.z[i]);
        }
        sum += coeff * w * (static_cast<double>(a.x[i]) * bx +
                            static_cast<double>(a.y[i]) * by +
                            static_cast<double>(a.z[i]) * bz);
    }
    block_sum_store(sum, block_out);
}

// BB products with s = P_m(m - m_prev), y = g - P_m(g_prev), P_m(v) = v - (m.v/|m|^2) m.
// term: 0 -> <s,s>, 1 -> <s,y>, 2 -> <y,y>.
template <typename S>
__global__ void bb_term_blocks_kernel(
    Field<S> m, Field<S> m_prev, Field<S> g, Field<S> g_prev, int term,
    const double *volume_fraction, int has_vf, const uint8_t *active, int has_active,
    double coeff, double *block_out, uint64_t n)
{
    double sum = 0.0;
    for (uint64_t i = blockIdx.x * static_cast<uint64_t>(blockDim.x) + threadIdx.x; i < n;
         i += static_cast<uint64_t>(gridDim.x) * blockDim.x) {
        const double w = cell_weight(volume_fraction, has_vf, active, has_active, i);
        if (w == 0.0) continue;
        const double m0 = m.x[i], m1 = m.y[i], m2 = m.z[i];
        const double norm_sq = m0 * m0 + m1 * m1 + m2 * m2;
        const double inv = norm_sq > 0.0 ? 1.0 / norm_sq : 0.0;
        double d0 = m0 - static_cast<double>(m_prev.x[i]);
        double d1 = m1 - static_cast<double>(m_prev.y[i]);
        double d2 = m2 - static_cast<double>(m_prev.z[i]);
        double c = (m0 * d0 + m1 * d1 + m2 * d2) * inv;
        const double s0 = d0 - c * m0, s1 = d1 - c * m1, s2 = d2 - c * m2;
        d0 = g_prev.x[i]; d1 = g_prev.y[i]; d2 = g_prev.z[i];
        c = (m0 * d0 + m1 * d1 + m2 * d2) * inv;
        const double y0 = static_cast<double>(g.x[i]) - (d0 - c * m0);
        const double y1 = static_cast<double>(g.y[i]) - (d1 - c * m1);
        const double y2 = static_cast<double>(g.z[i]) - (d2 - c * m2);
        const double product = term == 0 ? s0 * s0 + s1 * s1 + s2 * s2
                             : term == 1 ? s0 * y0 + s1 * y1 + s2 * y2
                                         : y0 * y0 + y1 * y1 + y2 * y2;
        sum += coeff * w * product;
    }
    block_sum_store(sum, block_out);
}

// component: 0..2 -> m_c over active cells, 3 -> active-cell count.
template <typename S>
__global__ void component_sum_blocks_kernel(
    Field<S> m, int component, const uint8_t *active, int has_active, double *block_out, uint64_t n)
{
    double sum = 0.0;
    for (uint64_t i = blockIdx.x * static_cast<uint64_t>(blockDim.x) + threadIdx.x; i < n;
         i += static_cast<uint64_t>(gridDim.x) * blockDim.x) {
        if (!cell_active(active, has_active, i)) continue;
        sum += component == 0 ? static_cast<double>(m.x[i])
             : component == 1 ? static_cast<double>(m.y[i])
             : component == 2 ? static_cast<double>(m.z[i])
                              : 1.0;
    }
    block_sum_store(sum, block_out);
}

__global__ void sum_blocks_kernel(const double *input, double *output, uint64_t n) {
    double sum = 0.0;
    for (uint64_t i = threadIdx.x; i < n; i += blockDim.x) sum += input[i];
    block_sum_store(sum, output);
}

uint64_t grid_for(uint64_t n) {
    const uint64_t blocks = (n + BLOCK - 1) / BLOCK;
    return blocks == 0 ? 1 : (blocks > MAX_BLOCKS ? MAX_BLOCKS : blocks);
}

void record_control_scalar(Context &ctx, uint64_t bytes) {
    if (fullmag_fdm_solver_phase_active(*ctx.execution_receipt)) {
        fullmag_fdm_record_control_scalar_d2h(ctx, bytes);
        fullmag_fdm_record_control_scalar_host_sync(ctx);
    }
}

// Reduce `blocks` partial sums in ctx.reduction_scratch to one host scalar.
bool finish_sum(Context &ctx, uint64_t blocks, double &out) {
    sum_blocks_kernel<<<1, BLOCK>>>(ctx.reduction_scratch, ctx.reduction_scratch, blocks);
    const cudaError_t err =
        cudaMemcpy(&out, ctx.reduction_scratch, sizeof(double), cudaMemcpyDeviceToHost);
    if (err != cudaSuccess) {
        set_cuda_error(ctx, "direct_minimizer_reduction", err);
        return false;
    }
    fullmag_fdm_note_operator_device_execution(ctx, FULLMAG_FDM_OPERATOR_REDUCTION);
    record_control_scalar(ctx, sizeof(double));
    return true;
}

int has_vf(const Context &ctx) {
    return ctx.boundary_tier > 0 && ctx.volume_fraction != nullptr ? 1 : 0;
}

double metric_coefficient(const Context &ctx) {
    return MU0 * ctx.Ms * ctx.dx * ctx.dy * ctx.dz;
}

template <typename S>
bool metric_dot(Context &ctx, const DeviceVectorField &a, const DeviceVectorField &b,
                const DeviceVectorField *c, double &out)
{
    const uint64_t blocks = grid_for(ctx.cell_count);
    const Field<S> none{nullptr, nullptr, nullptr};
    metric_dot_blocks_kernel<S><<<static_cast<unsigned>(blocks), BLOCK>>>(
        as_field<S>(a), as_field<S>(b), c ? as_field<S>(*c) : none, c ? 1 : 0,
        ctx.volume_fraction, has_vf(ctx), ctx.active_mask, ctx.has_active_mask ? 1 : 0,
        metric_coefficient(ctx), ctx.reduction_scratch, ctx.cell_count);
    return finish_sum(ctx, blocks, out);
}

template <typename S>
bool bb_term(Context &ctx, int term, double &out) {
    DirectMinimizerState &state = ctx.direct_minimizer;
    const uint64_t blocks = grid_for(ctx.cell_count);
    bb_term_blocks_kernel<S><<<static_cast<unsigned>(blocks), BLOCK>>>(
        as_field<S>(ctx.m), as_field<S>(state.m_prev), as_field<S>(state.g_trial),
        as_field<S>(state.g), term, ctx.volume_fraction, has_vf(ctx), ctx.active_mask,
        ctx.has_active_mask ? 1 : 0, metric_coefficient(ctx), ctx.reduction_scratch,
        ctx.cell_count);
    return finish_sum(ctx, blocks, out);
}

template <typename S>
bool mean_magnetization(Context &ctx, double out[3]) {
    const uint64_t blocks = grid_for(ctx.cell_count);
    double sums[4] = {0.0, 0.0, 0.0, 0.0};
    for (int component = 0; component < 4; ++component) {
        component_sum_blocks_kernel<S><<<static_cast<unsigned>(blocks), BLOCK>>>(
            as_field<S>(ctx.m), component, ctx.active_mask, ctx.has_active_mask ? 1 : 0,
            ctx.reduction_scratch, ctx.cell_count);
        if (!finish_sum(ctx, blocks, sums[component])) return false;
    }
    for (int component = 0; component < 3; ++component) {
        out[component] = sums[3] > 0.0 ? sums[component] / sums[3] : 0.0;
    }
    return true;
}

template <typename S>
void tangent_gradient(Context &ctx, const DeviceVectorField &out) {
    tangent_gradient_kernel<S><<<static_cast<unsigned>(grid_for(ctx.cell_count)), BLOCK>>>(
        as_field<S>(ctx.m), as_field<S>(ctx.work), as_field<S>(out), ctx.active_mask,
        ctx.has_active_mask ? 1 : 0, ctx.cell_count);
}

bool copy_field(Context &ctx, DeviceVectorField &dst, const DeviceVectorField &src) {
    const size_t bytes = ctx.cell_count *
        (ctx.precision == FULLMAG_FDM_PRECISION_DOUBLE ? sizeof(double) : sizeof(float));
    for (auto [d, s] : {std::pair{dst.x, src.x}, std::pair{dst.y, src.y}, std::pair{dst.z, src.z}}) {
        const cudaError_t err = cudaMemcpyAsync(d, s, bytes, cudaMemcpyDeviceToDevice, nullptr);
        if (err != cudaSuccess) {
            set_cuda_error(ctx, "direct_minimizer_copy", err);
            return false;
        }
    }
    return true;
}

// H_eff and energies of ctx.m, as context_fill_current_stats evaluates them.
template <typename S>
bool evaluate_state(Context &ctx, fullmag_fdm_step_stats &stats);

template <>
bool evaluate_state<float>(Context &ctx, fullmag_fdm_step_stats &stats) {
    if (ctx.enable_exchange) launch_exchange_field_fp32(ctx);
    if (ctx.enable_demag) launch_demag_field_fp32(ctx);
    launch_effective_field_fp32(ctx, ctx.current_time);
    stats.exchange_energy_joules = ctx.enable_exchange ? launch_exchange_energy_fp32(ctx) : 0.0;
    stats.demag_energy_joules = ctx.enable_demag ? launch_demag_energy_fp32(ctx) : 0.0;
    stats.external_energy_joules = launch_external_energy_fp32(ctx);
    stats.anisotropy_energy_joules = reduce_uniaxial_anisotropy_energy_fp32(ctx);
    stats.cubic_energy_joules = reduce_cubic_anisotropy_energy_fp32(ctx);
    stats.dmi_energy_joules = reduce_dmi_energy_fp32(ctx);
    stats.max_effective_field_amplitude =
        reduce_max_norm_fp32(ctx, ctx.work.x, ctx.work.y, ctx.work.z, ctx.cell_count);
    stats.max_demag_field_amplitude = ctx.enable_demag
        ? reduce_max_norm_fp32(ctx, ctx.h_demag.x, ctx.h_demag.y, ctx.h_demag.z, ctx.cell_count)
        : 0.0;
    stats.max_torque_Apm = reduce_max_cross_norm_fp32(
        ctx, ctx.m.x, ctx.m.y, ctx.m.z, ctx.work.x, ctx.work.y, ctx.work.z, ctx.cell_count);
    return ctx.last_error.empty();
}

template <>
bool evaluate_state<double>(Context &ctx, fullmag_fdm_step_stats &stats) {
    if (ctx.enable_exchange) launch_exchange_field_fp64(ctx);
    if (ctx.enable_demag) launch_demag_field_fp64(ctx);
    launch_effective_field_fp64(ctx, ctx.current_time);
    stats.exchange_energy_joules = ctx.enable_exchange ? launch_exchange_energy_fp64(ctx) : 0.0;
    stats.demag_energy_joules = ctx.enable_demag ? launch_demag_energy_fp64(ctx) : 0.0;
    stats.external_energy_joules = launch_external_energy_fp64(ctx);
    stats.anisotropy_energy_joules = reduce_uniaxial_anisotropy_energy_fp64(ctx);
    stats.cubic_energy_joules = reduce_cubic_anisotropy_energy_fp64(ctx);
    stats.dmi_energy_joules = reduce_dmi_energy_fp64(ctx);
    stats.max_effective_field_amplitude =
        reduce_max_norm_fp64(ctx, ctx.work.x, ctx.work.y, ctx.work.z, ctx.cell_count);
    stats.max_demag_field_amplitude = ctx.enable_demag
        ? reduce_max_norm_fp64(ctx, ctx.h_demag.x, ctx.h_demag.y, ctx.h_demag.z, ctx.cell_count)
        : 0.0;
    stats.max_torque_Apm = reduce_max_cross_norm_fp64(
        ctx, ctx.m.x, ctx.m.y, ctx.m.z, ctx.work.x, ctx.work.y, ctx.work.z, ctx.cell_count);
    return ctx.last_error.empty();
}

double total_energy(const fullmag_fdm_step_stats &stats) {
    return stats.exchange_energy_joules + stats.demag_energy_joules +
           stats.external_energy_joules + stats.anisotropy_energy_joules +
           stats.cubic_energy_joules + stats.dmi_energy_joules;
}

double clamp_step(const fullmag_fdm_direct_minimizer_config_v1 &config, double value) {
    return std::fmin(std::fmax(value, config.min_step_size), config.max_step_size);
}

// Host `fallback_reset_step_size(reset + 1)`.
double reset_step(const fullmag_fdm_direct_minimizer_config_v1 &config, uint64_t reset) {
    return clamp_step(config, config.initial_step_size / static_cast<double>(reset + 2));
}

void fill_status(const DirectMinimizerState &state, uint32_t status_code,
                 fullmag_fdm_direct_minimizer_status_v1 &out)
{
    out.status = status_code;
    out.use_bb1 = state.use_bb1 ? 1u : 0u;
    out.accepted_steps = state.accepted_steps;
    out.reset_consecutive = state.reset_consecutive;
    out.energy_j = state.energy_j;
    out.next_step_size = state.step_size;
    out.gradient_norm_sq = state.gradient_norm_sq;
    out.max_torque_apm = state.max_torque_apm;
}

// Evaluate the current state into the cache: H_eff (ctx.work), energy, gradient.
template <typename S>
bool refresh_cache(Context &ctx, fullmag_fdm_step_stats &stats) {
    DirectMinimizerState &state = ctx.direct_minimizer;
    if (!evaluate_state<S>(ctx, stats)) return false;
    stats.total_energy_joules = total_energy(stats);
    tangent_gradient<S>(ctx, state.g);
    double gradient_norm_sq = 0.0;
    if (!metric_dot<S>(ctx, state.g, state.g, nullptr, gradient_norm_sq)) return false;
    state.energy_j = stats.total_energy_joules;
    state.gradient_norm_sq = gradient_norm_sq;
    state.max_torque_apm = stats.max_torque_Apm;
    state.stats = stats;
    state.cache_valid = true;
    state.cache_revision = ctx.accepted_state_revision;
    return true;
}

template <typename S>
int begin_impl(Context &ctx, fullmag_fdm_step_stats &out_stats,
               fullmag_fdm_direct_minimizer_status_v1 &out_status)
{
    DirectMinimizerState &state = ctx.direct_minimizer;
    // Each minimization starts like the host DirectMinimizerState::new.
    state.step_size = state.config.initial_step_size;
    state.use_bb1 = true;
    state.reset_consecutive = 0;
    state.accepted_steps = 0;
    fullmag_fdm_step_stats stats{};
    stats.step = ctx.step_count;
    stats.time_seconds = ctx.current_time;
    if (!refresh_cache<S>(ctx, stats)) return FULLMAG_FDM_ERR_CUDA;
    if (!mean_magnetization<S>(ctx, out_status.mean_m)) return FULLMAG_FDM_ERR_CUDA;
    context_invalidate_observables(ctx);
    out_stats = stats;
    fill_status(state, FULLMAG_FDM_DIRECT_MINIMIZER_READY, out_status);
    return FULLMAG_FDM_OK;
}

template <typename S>
int step_impl(Context &ctx, fullmag_fdm_step_stats &out_stats,
              fullmag_fdm_direct_minimizer_status_v1 &out_status)
{
    DirectMinimizerState &state = ctx.direct_minimizer;
    const auto &config = state.config;
    if (!state.cache_valid || state.cache_revision != ctx.accepted_state_revision) {
        fullmag_fdm_step_stats stats{};
        if (!refresh_cache<S>(ctx, stats)) return FULLMAG_FDM_ERR_CUDA;
    }
    const double gradient_norm_sq = state.gradient_norm_sq;
    if (!std::isfinite(gradient_norm_sq) || gradient_norm_sq < 0.0) {
        fill_status(state, FULLMAG_FDM_DIRECT_MINIMIZER_GRADIENT_INVALID, out_status);
        return FULLMAG_FDM_OK;
    }
    if (gradient_norm_sq == 0.0) {
        fill_status(state, FULLMAG_FDM_DIRECT_MINIMIZER_GRADIENT_DEGENERATE, out_status);
        return FULLMAG_FDM_OK;
    }

    const double previous_energy = state.energy_j;
    const double tolerance = std::isfinite(previous_energy)
        ? std::fmax(config.energy_tolerance_relative * std::fabs(previous_energy), 0.0)
        : 0.0;
    if (!copy_field(ctx, state.m_prev, ctx.m) || !copy_field(ctx, state.h_prev, ctx.work)) {
        return FULLMAG_FDM_ERR_CUDA;
    }

    double step_size = state.step_size;
    uint32_t backtracks = 0;
    uint32_t evaluations = 0;
    double trial_energy = std::numeric_limits<double>::quiet_NaN();
    double chord = std::numeric_limits<double>::quiet_NaN();
    double last_step = step_size;
    bool accepted = false;
    fullmag_fdm_step_stats trial{};
    const unsigned grid = static_cast<unsigned>(grid_for(ctx.cell_count));
    for (;;) {
        last_step = step_size;
        int invalid = 0;
        if (cudaMemsetAsync(state.invalid_flag, 0, sizeof(int), nullptr) != cudaSuccess) {
            ctx.last_error = "direct_minimizer_flag_reset";
            return FULLMAG_FDM_ERR_CUDA;
        }
        retract_kernel<S><<<grid, BLOCK>>>(
            as_field<S>(state.m_prev), as_field<S>(state.g), step_size, as_field<S>(ctx.m),
            ctx.active_mask, ctx.has_active_mask ? 1 : 0, state.invalid_flag, ctx.cell_count);
        const cudaError_t err =
            cudaMemcpy(&invalid, state.invalid_flag, sizeof(int), cudaMemcpyDeviceToHost);
        if (err != cudaSuccess) {
            set_cuda_error(ctx, "direct_minimizer_retraction", err);
            return FULLMAG_FDM_ERR_CUDA;
        }
        record_control_scalar(ctx, sizeof(int));
        if (invalid == 0) {
            ++evaluations;
            trial = fullmag_fdm_step_stats{};
            if (!evaluate_state<S>(ctx, trial)) return FULLMAG_FDM_ERR_CUDA;
            trial_energy = total_energy(trial);
            trial.total_energy_joules = trial_energy;
            double chord_dot = 0.0;
            if (!metric_dot<S>(ctx, state.h_prev, ctx.m, &state.m_prev, chord_dot)) {
                return FULLMAG_FDM_ERR_CUDA;
            }
            chord = -chord_dot;
            // projected_gradient_armijo_accepts_with_tolerance
            if (std::isfinite(previous_energy) && std::isfinite(trial_energy) &&
                std::isfinite(chord) && chord < 0.0 &&
                (tolerance > 0.0 || trial_energy < previous_energy) &&
                trial_energy <= previous_energy + config.armijo_coefficient * chord + tolerance) {
                accepted = true;
                break;
            }
        }
        if (backtracks >= config.max_backtracks) break;
        step_size *= 0.5;
        ++backtracks;
    }

    out_status.backtracks = backtracks;
    out_status.energy_evaluations = evaluations;
    out_status.previous_energy_j = previous_energy;
    out_status.chord_increment_j = chord;
    out_status.energy_tolerance_j = tolerance;
    out_status.last_trial_energy_j = trial_energy;
    out_status.last_trial_step_size = last_step;
    if (!accepted) {
        // Nothing is committed: restore m_prev and its field.
        if (!copy_field(ctx, ctx.m, state.m_prev) || !copy_field(ctx, ctx.work, state.h_prev)) {
            return FULLMAG_FDM_ERR_CUDA;
        }
        context_invalidate_observables(ctx);
        fill_status(state, FULLMAG_FDM_DIRECT_MINIMIZER_LINE_SEARCH_EXHAUSTED, out_status);
        return FULLMAG_FDM_OK;
    }

    tangent_gradient<S>(ctx, state.g_trial);
    double s_dot_s = 0.0, s_dot_y = 0.0, y_dot_y = 0.0;
    if (!bb_term<S>(ctx, 0, s_dot_s) || !bb_term<S>(ctx, 1, s_dot_y) ||
        !bb_term<S>(ctx, 2, y_dot_y)) {
        return FULLMAG_FDM_ERR_CUDA;
    }
    // projected_gradient_step_size_update
    bool bb_ok = false;
    double next_step = 0.0;
    const bool curvature = std::isfinite(s_dot_y) && s_dot_y > 0.0;
    if (state.use_bb1) {
        if (curvature) { next_step = clamp_step(config, s_dot_s / s_dot_y); bb_ok = true; }
    } else if (curvature && std::isfinite(y_dot_y) && y_dot_y > 0.0) {
        next_step = clamp_step(config, s_dot_y / y_dot_y); bb_ok = true;
    } else if (curvature) {
        next_step = clamp_step(config, s_dot_s / s_dot_y); bb_ok = true;
    }
    if (!bb_ok) next_step = reset_step(config, state.reset_consecutive);
    state.reset_consecutive = bb_ok ? 0 : state.reset_consecutive + 1;
    state.use_bb1 = !state.use_bb1;
    state.step_size = next_step;

    std::swap(state.g, state.g_trial);
    double next_gradient_norm_sq = 0.0;
    if (!metric_dot<S>(ctx, state.g, state.g, nullptr, next_gradient_norm_sq)) {
        return FULLMAG_FDM_ERR_CUDA;
    }
    state.energy_j = trial_energy;
    state.gradient_norm_sq = next_gradient_norm_sq;
    state.max_torque_apm = trial.max_torque_Apm;
    ++state.accepted_steps;
    if (!mean_magnetization<S>(ctx, out_status.mean_m)) return FULLMAG_FDM_ERR_CUDA;

    // Minimization does not advance physical time.
    context_stage_accepted_step(ctx, 0.0);
    trial.step = ctx.pending_step_count;
    trial.time_seconds = ctx.pending_time;
    trial.dt_seconds = 0.0;
    state.stats = trial;
    // The commit increments the accepted-state revision once.
    state.cache_valid = true;
    state.cache_revision = ctx.accepted_state_revision + 1;

    out_status.accepted_step_size = last_step;
    out_status.s_dot_s = s_dot_s;
    out_status.s_dot_y = s_dot_y;
    out_status.y_dot_y = y_dot_y;
    fill_status(state, FULLMAG_FDM_DIRECT_MINIMIZER_ACCEPTED, out_status);
    out_stats = trial;
    return FULLMAG_FDM_OK;
}

bool supported_context(Context &ctx) {
    if (ctx.has_multilayer_plan_v2 || ctx.gpu_transport_rhs.active || ctx.has_frozen_mask ||
        ctx.temperature > 0.0) {
        ctx.last_error =
            "device direct minimizer supports single-grid FDM without frozen spins, "
            "spin transport or temperature";
        return false;
    }
    if (ctx.reduction_scratch == nullptr || ctx.reduction_scratch_len < MAX_BLOCKS) {
        ctx.last_error = "device direct minimizer requires the reduction scratch";
        return false;
    }
    return true;
}

} // namespace

int direct_minimizer_configure(
    Context &ctx, const fullmag_fdm_direct_minimizer_config_v1 &config)
{
    if (config.abi_version != FULLMAG_FDM_DIRECT_MINIMIZER_ABI_V1 ||
        config.struct_size != sizeof(config)) {
        ctx.last_error = "direct minimizer config ABI mismatch";
        return FULLMAG_FDM_ERR_ABI;
    }
    if (config.algorithm != FULLMAG_FDM_DIRECT_MINIMIZER_PROJECTED_GRADIENT_BB ||
        !(config.min_step_size > 0.0) || !(config.max_step_size >= config.min_step_size) ||
        !(config.initial_step_size > 0.0) || !(config.armijo_coefficient > 0.0) ||
        !(config.energy_tolerance_relative >= 0.0) || !std::isfinite(config.max_step_size)) {
        ctx.last_error = "invalid direct minimizer config";
        return FULLMAG_FDM_ERR_INVALID;
    }
    if (!supported_context(ctx)) return FULLMAG_FDM_ERR_INVALID;
    auto &receipt = *ctx.execution_receipt;
    {
        std::lock_guard<std::mutex> lock(receipt.accounting_mutex);
        if ((receipt.executed_device_operator_mask & FULLMAG_FDM_OPERATOR_LLG_INTEGRATOR) != 0) {
            ctx.last_error = "direct minimizer cannot be selected after LLG steps on this handle";
            return FULLMAG_FDM_ERR_INVALID;
        }
    }
    if (!context_allocate_direct_minimizer_workspace(ctx)) return FULLMAG_FDM_ERR_CUDA;
    DirectMinimizerState &state = ctx.direct_minimizer;
    state.config = config;
    state.configured = true;
    state.cache_valid = false;
    state.step_size = config.initial_step_size;
    {
        // The handle no longer integrates LLG: DIRECT_MINIMIZER replaces it.
        std::lock_guard<std::mutex> lock(receipt.accounting_mutex);
        receipt.required_operator_mask &= ~static_cast<uint64_t>(FULLMAG_FDM_OPERATOR_LLG_INTEGRATOR);
        receipt.device_operator_mask &= ~static_cast<uint64_t>(FULLMAG_FDM_OPERATOR_LLG_INTEGRATOR);
    }
    fullmag_fdm_commit_operator_residency(ctx);
    return FULLMAG_FDM_OK;
}

int direct_minimizer_begin(
    Context &ctx, fullmag_fdm_step_stats &out_stats,
    fullmag_fdm_direct_minimizer_status_v1 &out_status)
{
    if (!ctx.direct_minimizer.configured) {
        ctx.last_error = "direct minimizer is not configured";
        return FULLMAG_FDM_ERR_INVALID;
    }
    return ctx.precision == FULLMAG_FDM_PRECISION_DOUBLE
        ? begin_impl<double>(ctx, out_stats, out_status)
        : begin_impl<float>(ctx, out_stats, out_status);
}

int direct_minimizer_step(
    Context &ctx, fullmag_fdm_step_stats &out_stats,
    fullmag_fdm_direct_minimizer_status_v1 &out_status)
{
    if (!ctx.direct_minimizer.configured) {
        ctx.last_error = "direct minimizer is not configured";
        return FULLMAG_FDM_ERR_INVALID;
    }
    return ctx.precision == FULLMAG_FDM_PRECISION_DOUBLE
        ? step_impl<double>(ctx, out_stats, out_status)
        : step_impl<float>(ctx, out_stats, out_status);
}

} // namespace fdm
} // namespace fullmag
