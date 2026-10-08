"use client";

import { useCallback } from "react";

import {
  DATA_ANTENNA_FIELD_SOLUTION_PATH,
  DATA_ANTENNA_FIELD_SOLUTION_PAYLOAD_PATH,
  DATA_ANTENNA_EXTERNAL_LEAD_INSPECTION_PATH,
  DATA_ANTENNA_EXTERNAL_LEAD_INSPECTION_DISPLAY_PATH,
  DATA_ANTENNA_EXTERNAL_LEAD_INSPECTION_PAYLOAD_PATH,
  DATA_ANTENNA_STAGE_OUTPUT_CATALOG_PATH,
  DATA_ANTENNA_SOURCE_SPECTRUM_PATH,
  DATA_ANTENNA_SOURCE_SPECTRUM_PAYLOAD_PATH,
} from "../api/apiPaths";
import { ControlRoomApiError } from "../api/ControlRoomApi";
import type {
  AntennaFieldSolutionResource,
  AntennaFieldPayloadKind,
  AntennaExternalLeadInspectionResource,
  AntennaInspectionDisplayResource,
  AntennaInspectionManifestPayloadKind,
  AntennaInspectionPayloadKind,
  AntennaStageOutputCatalogResource,
  AntennaSpectrumPayloadKind,
  AntennaSourceSpectrumResource,
  BinaryResourceResult,
} from "../api/apiTypes";
import { useKernel } from "../KernelContext";

import { useResource } from "./useResource";
import { sessionResourceIdentitiesEqual } from "./sessionResourceIdentity";
import { useSessionScopedResourceKey } from "./useSessionScopedResourceKey";

export interface AntennaResourceOptions {
  enabled?: boolean;
}

interface AntennaPayloadResourceOptions extends AntennaResourceOptions {
  expectedEtag?: string;
  maxResponseBytes?: number;
  range?: string;
}

export function antennaSpectrumPayloadEtag(
  spectrum: AntennaSourceSpectrumResource,
  payloadKind: AntennaSpectrumPayloadKind,
): string {
  if (!spectrum.payloads) {
    throw new Error("antenna spectrum manifest has no binary payload references");
  }
  const token = `antenna-source-spectrum-payload:${spectrum.session_id}:${spectrum.session_epoch}:${spectrum.request_scope_epoch}:${spectrum.output_id}:${payloadKind}:${spectrum.content_digest}:${spectrum.payloads[payloadKind].sha256}`;
  return `"${token.replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;
}

export function antennaFieldPayloadEtag(
  solution: AntennaFieldSolutionResource,
  payloadKind: AntennaFieldPayloadKind,
  portModeId?: string,
): string {
  const basis = portModeId
    ? solution.bases.find((item) => item.port_mode_id === portModeId)
    : undefined;
  const reference = (() => {
    switch (payloadKind) {
      case "conductor_positions": return solution.conductor_positions;
      case "sample_positions": return solution.sample_positions;
      case "sample_topology": return solution.sample_topology;
      case "electric_potential_per_ampere": return basis?.electric_potential_per_ampere;
      case "current_density_per_ampere": return basis?.current_density_per_ampere;
      case "magnetic_field_per_ampere": return basis?.magnetic_field_per_ampere;
    }
  })();
  if (!reference) {
    throw new Error("antenna field manifest has no selected binary payload reference");
  }
  const token = `antenna-field-payload:${solution.session_id}:${solution.session_epoch}:${solution.request_scope_epoch}:${solution.solution_id}:${payloadKind}:${portModeId ?? ""}:${solution.content_digest}:${reference.sha256}`;
  return `"${token.replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;
}

export function requireMatchingAntennaPayloadRevision(
  result: BinaryResourceResult<ArrayBuffer> | null,
  expectedEtag: string,
): BinaryResourceResult<ArrayBuffer> | null {
  if (result?.status === "ready" && result.etag !== expectedEtag) {
    throw new Error("antenna payload revision does not match selected manifest");
  }
  return result;
}

export async function antennaInspectionPayloadEtag(
  inspection: AntennaExternalLeadInspectionResource,
  payloadKind: AntennaInspectionPayloadKind,
  payloadSha256: string,
): Promise<string> {
  const output = inspection.outputs.length === 1 ? inspection.outputs[0] : null;
  if (!output || !Number.isSafeInteger(inspection.stage_revision) ||
    !/^[0-9a-f]{64}$/.test(payloadSha256)) {
    throw new Error("antenna inspection payload has invalid owner or digest");
  }
  // This ordered tuple is the API's immutable binary-response identity.
  const token = JSON.stringify([
    inspection.session_id, inspection.session_epoch, inspection.request_scope_epoch,
    inspection.run_id, inspection.stage_revision, inspection.runtime_stage_id,
    inspection.stage_id, inspection.output_id, output.inspection_ref.content_digest,
    payloadKind, payloadSha256,
  ]);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  const hex = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `"${hex}"`;
}

function concretePath(template: string, name: string, value: string): string {
  return template.replace(`{${name}}`, encodeURIComponent(value));
}

function concreteSpectrumPayloadPath(
  outputId: string,
  payloadKind: AntennaSpectrumPayloadKind,
): string {
  return concretePath(
    concretePath(
      DATA_ANTENNA_SOURCE_SPECTRUM_PAYLOAD_PATH,
      "output_id",
      outputId,
    ),
    "payload_kind",
    payloadKind,
  );
}

function concreteFieldPayloadPath(
  solutionId: string,
  payloadKind: AntennaFieldPayloadKind,
  portModeId?: string,
): string {
  const path = concretePath(
    concretePath(DATA_ANTENNA_FIELD_SOLUTION_PAYLOAD_PATH, "solution_id", solutionId),
    "payload_kind",
    payloadKind,
  );
  return portModeId ? `${path}?port_mode_id=${encodeURIComponent(portModeId)}` : path;
}

function ignoreMissingAntennaResource<T>(error: unknown): T | null {
  if (
    error instanceof ControlRoomApiError &&
    error.status === 404 &&
    error.code !== "missing_payload"
  ) {
    return null;
  }
  throw error;
}

export function useAntennaFieldSolutionResource(
  solutionId: string | null | undefined,
  options: AntennaResourceOptions = {},
) {
  const { api } = useKernel();
  const unscopedResourceKey = solutionId
    ? concretePath(DATA_ANTENNA_FIELD_SOLUTION_PATH, "solution_id", solutionId)
    : `${DATA_ANTENNA_FIELD_SOLUTION_PATH}:none`;
  const { resourceKey, sessionIdentity } = useSessionScopedResourceKey(unscopedResourceKey);
  const load = useCallback(
    ({ signal, sessionScopeKey }: { signal: AbortSignal; sessionScopeKey?: string }) =>
      solutionId
        ? api.data.antenna
            .fieldSolution(solutionId, { signal, sessionScopeKey })
            .catch(ignoreMissingAntennaResource<AntennaFieldSolutionResource>)
        : Promise.resolve(null),
    [api, solutionId],
  );

  return useResource<AntennaFieldSolutionResource | null>({
    enabled: Boolean(solutionId && sessionIdentity) && options.enabled !== false,
    load,
    resolveRevision: (data) => data?.content_digest ?? null,
    resourceKey,
  });
}

export function useAntennaStageOutputCatalogResource(
  stageId: string | null | undefined,
  options: AntennaResourceOptions = {},
) {
  const { api } = useKernel();
  const unscopedResourceKey = stageId
    ? concretePath(
        DATA_ANTENNA_STAGE_OUTPUT_CATALOG_PATH,
        "stage_id",
        stageId,
      )
    : `${DATA_ANTENNA_STAGE_OUTPUT_CATALOG_PATH}:none`;
  const { resourceKey, sessionIdentity } = useSessionScopedResourceKey(unscopedResourceKey);
  const load = useCallback(
    ({ signal, sessionScopeKey }: { signal: AbortSignal; sessionScopeKey?: string }) =>
      stageId
        ? api.data.antenna
            .stageOutputCatalog(stageId, { signal, sessionScopeKey })
            .catch(ignoreMissingAntennaResource<AntennaStageOutputCatalogResource>)
        : Promise.resolve(null),
    [api, stageId],
  );

  return useResource<AntennaStageOutputCatalogResource | null>({
    enabled: Boolean(stageId && sessionIdentity) && options.enabled !== false,
    load,
    resolveRevision: (data) =>
      data
        ? `${data.stage_revision}:${data.content_digest}`
        : null,
    resourceKey,
  });
}

export function useAntennaFieldSolutionPayloadResource(
  solutionId: string | null | undefined,
  payloadKind: AntennaFieldPayloadKind | null | undefined,
  portModeId: string | null | undefined,
  options: AntennaPayloadResourceOptions = {},
) {
  const { api } = useKernel();
  const unscopedResourceKey = solutionId && payloadKind
    ? `${concreteFieldPayloadPath(solutionId, payloadKind, portModeId ?? undefined)}${options.expectedEtag ? `#${options.expectedEtag}` : ""}${options.range ? `@${options.range}` : ""}`
    : `${DATA_ANTENNA_FIELD_SOLUTION_PAYLOAD_PATH}:none`;
  const { resourceKey, sessionIdentity } = useSessionScopedResourceKey(unscopedResourceKey);
  const load = useCallback(
    async ({ signal, sessionScopeKey }: { signal: AbortSignal; sessionScopeKey?: string }) => {
      if (!solutionId || !payloadKind) return null;
      const result = await api.data.antenna
        .fieldSolutionPayload(solutionId, payloadKind, portModeId ?? undefined, { signal, sessionScopeKey, range: options.range, maxResponseBytes: options.maxResponseBytes })
        .catch(ignoreMissingAntennaResource<BinaryResourceResult<ArrayBuffer>>);
      return options.expectedEtag
        ? requireMatchingAntennaPayloadRevision(result, options.expectedEtag)
        : result;
    },
    [api, options.expectedEtag, options.maxResponseBytes, options.range, payloadKind, portModeId, solutionId],
  );

  return useResource<BinaryResourceResult<ArrayBuffer> | null>({
    enabled: Boolean(solutionId && payloadKind && sessionIdentity) && options.enabled !== false,
    load,
    resolveRevision: (data) => data?.status === "ready" ? data.etag : null,
    resourceKey,
  });
}

export function useAntennaSourceSpectrumResource(
  outputId: string | null | undefined,
  options: AntennaResourceOptions = {},
) {
  const { api } = useKernel();
  const unscopedResourceKey = outputId
    ? concretePath(DATA_ANTENNA_SOURCE_SPECTRUM_PATH, "output_id", outputId)
    : `${DATA_ANTENNA_SOURCE_SPECTRUM_PATH}:none`;
  const { resourceKey, sessionIdentity } = useSessionScopedResourceKey(unscopedResourceKey);
  const load = useCallback(
    ({ signal, sessionScopeKey }: { signal: AbortSignal; sessionScopeKey?: string }) =>
      outputId
        ? api.data.antenna
            .sourceSpectrum(outputId, { signal, sessionScopeKey })
            .catch(ignoreMissingAntennaResource<AntennaSourceSpectrumResource>)
        : Promise.resolve(null),
    [api, outputId],
  );

  return useResource<AntennaSourceSpectrumResource | null>({
    enabled: Boolean(outputId && sessionIdentity) && options.enabled !== false,
    load,
    resolveRevision: (data) => data?.content_digest ?? null,
    resourceKey,
  });
}

export function useAntennaSourceSpectrumPayloadResource(
  outputId: string | null | undefined,
  payloadKind: AntennaSpectrumPayloadKind | null | undefined,
  options: AntennaPayloadResourceOptions = {},
) {
  const { api } = useKernel();
  const unscopedResourceKey = outputId && payloadKind
    ? `${concreteSpectrumPayloadPath(outputId, payloadKind)}${options.expectedEtag ? `#${options.expectedEtag}` : ""}${options.range ? `@${options.range}` : ""}`
    : `${DATA_ANTENNA_SOURCE_SPECTRUM_PAYLOAD_PATH}:none`;
  const { resourceKey, sessionIdentity } = useSessionScopedResourceKey(unscopedResourceKey);
  const load = useCallback(
    async ({ signal, sessionScopeKey }: { signal: AbortSignal; sessionScopeKey?: string }) => {
      if (!outputId || !payloadKind) return null;
      const result = await api.data.antenna
        .sourceSpectrumPayload(outputId, payloadKind, { signal, sessionScopeKey, range: options.range, maxResponseBytes: options.maxResponseBytes })
        .catch(ignoreMissingAntennaResource<BinaryResourceResult<ArrayBuffer>>);
      return options.expectedEtag
        ? requireMatchingAntennaPayloadRevision(result, options.expectedEtag)
        : result;
    },
    [api, options.expectedEtag, options.maxResponseBytes, options.range, outputId, payloadKind],
  );

  return useResource<BinaryResourceResult<ArrayBuffer> | null>({
    enabled:
      Boolean(outputId && payloadKind && sessionIdentity) && options.enabled !== false,
    load,
    resolveRevision: (data) =>
      data?.status === "ready" ? data.etag : null,
    resourceKey,
  });
}

export function useAntennaExternalLeadInspectionResource(
  stageId: string | null | undefined,
  options: AntennaResourceOptions & { pauseLoad?: boolean } = {},
) {
  const { api } = useKernel();
  const unscopedResourceKey = stageId
    ? concretePath(DATA_ANTENNA_EXTERNAL_LEAD_INSPECTION_PATH, "stage_id", stageId)
    : `${DATA_ANTENNA_EXTERNAL_LEAD_INSPECTION_PATH}:none`;
  const { resourceKey, sessionIdentity } = useSessionScopedResourceKey(unscopedResourceKey);
  const load = useCallback(
    ({ signal, sessionScopeKey }: { signal: AbortSignal; sessionScopeKey?: string }) =>
      stageId
        ? api.data.antenna
            .externalLeadInspection(stageId, { signal, sessionScopeKey })
            .catch(ignoreMissingAntennaResource<AntennaExternalLeadInspectionResource>)
        : Promise.resolve(null),
    [api, stageId],
  );

  return useResource<AntennaExternalLeadInspectionResource | null>({
    enabled: Boolean(stageId && sessionIdentity) && options.enabled !== false,
    pauseLoad: options.pauseLoad,
    load,
    resolveRevision: (data) => data ? `${data.stage_revision}:${data.record_content_digest}` : null,
    resourceKey,
  });
}

function inspectionDisplayPayloadMatchesManifest(
  display: AntennaInspectionDisplayResource["device_potential"],
  manifest: NonNullable<AntennaExternalLeadInspectionResource["manifest"]>["device_potential"],
): boolean {
  return (["sha256", "byte_count", "value_count", "scalar_type", "layout", "unit"] as const)
    .every((key) => display[key] === manifest[key]);
}

export function antennaInspectionDisplayMatchesOwner(
  inspection: AntennaExternalLeadInspectionResource,
  display: AntennaInspectionDisplayResource,
): boolean {
  const output = inspection.outputs.length === 1 ? inspection.outputs[0] : null;
  return Boolean(output && inspection.manifest &&
    display.schema_version === "antenna_inspection_display.v1" &&
    display.session_id === inspection.session_id &&
    display.session_epoch === inspection.session_epoch &&
    display.request_scope_epoch === inspection.request_scope_epoch &&
    display.run_id === inspection.run_id &&
    display.runtime_stage_id === inspection.runtime_stage_id &&
    display.stage_revision === inspection.stage_revision &&
    display.record_content_digest === inspection.record_content_digest &&
    display.content_digest === output.inspection_ref.content_digest &&
    display.content_digest === inspection.manifest.content_digest &&
    display.source_object_id === inspection.manifest.source_object_id &&
    inspectionDisplayPayloadMatchesManifest(display.device_potential, inspection.manifest.device_potential) &&
    inspectionDisplayPayloadMatchesManifest(display.sample_positions, inspection.manifest.sample_positions) &&
    inspectionDisplayPayloadMatchesManifest(display.magnetic_field, inspection.manifest.magnetic_field) &&
    display.sampling_carrier.carrier_kind === inspection.manifest.sampling_carrier.carrier_kind &&
    display.sampling_carrier.location === inspection.manifest.sampling_carrier.location &&
    display.sampling_carrier.sample_count === inspection.manifest.sampling_carrier.sample_count &&
    display.sampling_carrier.topology_digest === inspection.manifest.sampling_carrier.topology_digest &&
    JSON.stringify(display.sampling_carrier.domain) === JSON.stringify(inspection.manifest.sampling_carrier.domain) &&
    display.status === "inspection_only" && display.qualification === "NOT VERIFIED" &&
    display.field_scope === "external_electrode_truncation" &&
    display.normalization === "raw_authored_current" && display.capabilities.display === true &&
    display.capabilities.per_ampere_basis === false && display.capabilities.llg_drive === false &&
    display.capabilities.source_fft === false && display.capabilities.current_density === false);
}

export function useAntennaInspectionDisplayResource(
  inspection: AntennaExternalLeadInspectionResource | null | undefined,
  options: AntennaResourceOptions = {},
) {
  const { api } = useKernel();
  const stageId = inspection?.runtime_stage_id;
  const contentDigest = inspection?.outputs.length === 1
    ? inspection.outputs[0].inspection_ref.content_digest : null;
  const unscopedResourceKey = inspection && stageId && contentDigest
    ? `${concretePath(DATA_ANTENNA_EXTERNAL_LEAD_INSPECTION_DISPLAY_PATH, "stage_id", stageId)}?content_digest=${encodeURIComponent(contentDigest)}#${inspection.stage_revision}:${inspection.record_content_digest}`
    : `${DATA_ANTENNA_EXTERNAL_LEAD_INSPECTION_DISPLAY_PATH}:none`;
  const { resourceKey, sessionIdentity } = useSessionScopedResourceKey(unscopedResourceKey);
  const ownerMatches = inspection && sessionResourceIdentitiesEqual(sessionIdentity, {
    sessionId: inspection.session_id, sessionEpoch: inspection.session_epoch,
    requestScopeEpoch: inspection.request_scope_epoch,
  });
  const load = useCallback(
    async ({ signal, sessionScopeKey }: { signal: AbortSignal; sessionScopeKey?: string }) => {
      if (!inspection || !ownerMatches || !stageId || !contentDigest) return null;
      const result = await api.data.antenna.externalLeadInspectionDisplay(
        stageId, contentDigest, { signal, sessionScopeKey },
      ).catch(ignoreMissingAntennaResource<AntennaInspectionDisplayResource>);
      if (result && !antennaInspectionDisplayMatchesOwner(inspection, result)) {
        throw new Error("antenna display metadata does not match its immutable inspection owner");
      }
      return result;
    }, [api, contentDigest, inspection, ownerMatches, stageId],
  );
  return useResource<AntennaInspectionDisplayResource | null>({
    enabled: Boolean(ownerMatches && stageId && contentDigest && inspection?.status === "inspection_only") && options.enabled !== false,
    load, resourceKey,
    resolveRevision: (data) => data ? `${data.stage_revision}:${data.record_content_digest}:${data.content_digest}` : null,
  });
}

type AntennaDisplayPayloadKind = "device_positions" | "device_topology" | "device_potential" | "sample_positions" | "magnetic_field";

export function useAntennaInspectionDisplayPayloadResource(
  inspection: AntennaExternalLeadInspectionResource | null | undefined,
  display: AntennaInspectionDisplayResource | null | undefined,
  payloadKind: AntennaDisplayPayloadKind | null | undefined,
  options: Pick<AntennaPayloadResourceOptions, "enabled" | "range" | "maxResponseBytes"> = {},
) {
  const { api } = useKernel();
  const compatible = Boolean(inspection && display && antennaInspectionDisplayMatchesOwner(inspection, display));
  const unscopedResourceKey = compatible && display && payloadKind
    ? `${concretePath(concretePath(DATA_ANTENNA_EXTERNAL_LEAD_INSPECTION_PAYLOAD_PATH, "stage_id", display.runtime_stage_id), "payload_kind", payloadKind)}?content_digest=${encodeURIComponent(display.content_digest)}#${display.stage_revision}:${display.record_content_digest}${options.range ? `@${options.range}` : ""}`
    : `${DATA_ANTENNA_EXTERNAL_LEAD_INSPECTION_PAYLOAD_PATH}:display:none`;
  const { resourceKey, sessionIdentity } = useSessionScopedResourceKey(unscopedResourceKey);
  const ownerMatches = display && sessionResourceIdentitiesEqual(sessionIdentity, {
    sessionId: display.session_id, sessionEpoch: display.session_epoch,
    requestScopeEpoch: display.request_scope_epoch,
  });
  const load = useCallback(
    async ({ signal, sessionScopeKey }: { signal: AbortSignal; sessionScopeKey?: string }) => {
      if (!compatible || !ownerMatches || !inspection || !display || !payloadKind) return null;
      const descriptor = display[payloadKind];
      if (!Number.isSafeInteger(descriptor.byte_count) || descriptor.byte_count <= 0 ||
          descriptor.byte_count > 64 * 1024 * 1024) {
        throw new Error("antenna display payload exceeds its complete bounded transport contract");
      }
      const expectedEtag = await antennaInspectionPayloadEtag(inspection, payloadKind, descriptor.sha256);
      const result = await api.data.antenna.externalLeadInspectionPayload(
        display.runtime_stage_id, payloadKind, display.content_digest,
        { signal, sessionScopeKey, range: options.range,
          maxResponseBytes: Math.min(options.maxResponseBytes ?? descriptor.byte_count, descriptor.byte_count) },
      );
      const pinned = requireMatchingAntennaPayloadRevision(result, expectedEtag);
      const complete = !options.range || options.range === `bytes=0-${descriptor.byte_count - 1}`;
      if (pinned?.status === "ready" && complete) {
        if (pinned.data.byteLength !== descriptor.byte_count) {
          throw new Error("antenna display payload length differs from its immutable descriptor");
        }
        const hash = await globalThis.crypto.subtle.digest("SHA-256", pinned.data);
        const hex = Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join("");
        if (hex !== descriptor.sha256) {
          throw new Error("antenna display payload digest differs from its immutable descriptor");
        }
      }
      return pinned;
    }, [api, compatible, display, inspection, options.maxResponseBytes, options.range, ownerMatches, payloadKind],
  );
  return useResource<BinaryResourceResult<ArrayBuffer> | null>({
    enabled: Boolean(compatible && ownerMatches && payloadKind) && options.enabled !== false,
    load, resourceKey, resolveRevision: (data) => data?.status === "ready" ? data.etag : null,
  });
}

export function useAntennaExternalLeadInspectionPayloadResource(
  inspection: AntennaExternalLeadInspectionResource | null | undefined,
  payloadKind: AntennaInspectionManifestPayloadKind | null | undefined,
  options: Pick<AntennaPayloadResourceOptions, "enabled" | "range" | "maxResponseBytes"> = {},
) {
  const { api } = useKernel();
  const stageId = inspection?.runtime_stage_id;
  const contentDigest = inspection?.outputs.length === 1
    ? inspection.outputs[0].inspection_ref.content_digest : null;
  const unscopedResourceKey = inspection && stageId && payloadKind && contentDigest
    ? `${concretePath(concretePath(DATA_ANTENNA_EXTERNAL_LEAD_INSPECTION_PAYLOAD_PATH, "stage_id", stageId), "payload_kind", payloadKind)}?content_digest=${encodeURIComponent(contentDigest)}#${inspection.stage_revision}:${inspection.record_content_digest}${options.range ? `@${options.range}` : ""}`
    : `${DATA_ANTENNA_EXTERNAL_LEAD_INSPECTION_PAYLOAD_PATH}:none`;
  const { resourceKey, sessionIdentity } = useSessionScopedResourceKey(unscopedResourceKey);
  const ownerMatches = inspection && sessionResourceIdentitiesEqual(sessionIdentity, {
    sessionId: inspection.session_id,
    sessionEpoch: inspection.session_epoch,
    requestScopeEpoch: inspection.request_scope_epoch,
  });
  const hasPayload = Boolean(
    inspection?.status === "inspection_only" && inspection.manifest &&
    contentDigest && inspection.manifest.content_digest === contentDigest,
  );
  const load = useCallback(
    async ({ signal, sessionScopeKey }: { signal: AbortSignal; sessionScopeKey?: string }) => {
      if (!inspection || !ownerMatches || !hasPayload || !stageId || !payloadKind || !contentDigest) return null;
      const descriptor = inspection.manifest?.[payloadKind];
      if (!descriptor) throw new Error("antenna inspection has no selected payload descriptor");
      const expectedEtag = await antennaInspectionPayloadEtag(inspection, payloadKind, descriptor.sha256);
      const result = await api.data.antenna.externalLeadInspectionPayload(
        stageId, payloadKind, contentDigest, { signal, sessionScopeKey, range: options.range, maxResponseBytes: options.maxResponseBytes },
      );
      return requireMatchingAntennaPayloadRevision(result, expectedEtag);
    },
    [api, contentDigest, hasPayload, inspection, options.maxResponseBytes, options.range, ownerMatches, payloadKind, stageId],
  );

  return useResource<BinaryResourceResult<ArrayBuffer> | null>({
    enabled: Boolean(ownerMatches && hasPayload && stageId && payloadKind) && options.enabled !== false,
    load,
    resolveRevision: (data) => data?.status === "ready" ? data.etag : null,
    resourceKey,
  });
}
