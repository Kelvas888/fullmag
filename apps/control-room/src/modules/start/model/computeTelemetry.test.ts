import { describe, expect, it } from "vitest";

import type { CpuTelemetryResource, GpuTelemetryResource } from "@/kernel/api/apiTypes";

import {
  computeFromTelemetry,
  isTelemetrySampleStale,
} from "./computeTelemetry";

const cpuTelemetry = (sampledAt: number): CpuTelemetryResource => ({
  logical_cpus: 8,
  memory_total_mb: 16_384,
  memory_used_mb: 2_048,
  process_cpu_percent: 0,
  process_rss_mb: 32,
  process_threads: 1,
  sample_time_unix_ms: sampledAt,
  status: "available",
  utilization_cpu_percent: 10,
});

const gpuTelemetry = (sampledAt: number): GpuTelemetryResource => ({
  devices: [],
  sample_time_unix_ms: sampledAt,
  status: "available",
});

describe("compute telemetry sample time", () => {
  it("uses the GPU timestamp when it is newer", () => {
    const compute = computeFromTelemetry(cpuTelemetry(1_000), gpuTelemetry(3_000), null);

    expect(compute?.sampledAt).toBe(3_000);
  });

  it("uses the CPU timestamp when it is newer", () => {
    const compute = computeFromTelemetry(cpuTelemetry(5_000), gpuTelemetry(3_000), null);

    expect(compute?.sampledAt).toBe(5_000);
  });
});

describe("compute telemetry freshness", () => {
  it("keeps a sample current through 30 seconds and marks older samples stale", () => {
    const now = 60_000;

    expect(isTelemetrySampleStale(now - 30_000, now)).toBe(false);
    expect(isTelemetrySampleStale(now - 30_001, now)).toBe(true);
  });

  it("does not treat a future-dated sample as current", () => {
    expect(isTelemetrySampleStale(60_001, 60_000)).toBe(true);
  });
});
