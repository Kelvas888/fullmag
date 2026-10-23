"use client";

import { useCallback, useEffect } from "react";

import { PLATFORM_INSTANCES_PATH } from "../api/apiPaths";
import type { InstanceDiscoveryResource } from "../api/apiTypes";
import { useKernel } from "../KernelContext";

import type { ResourceResult } from "./resourceTypes";
import { useResource } from "./useResource";

/** How often the tab strip refreshes the instances while the page is visible. */
export const INSTANCE_DISCOVERY_POLL_MS = 5_000;

export interface InstanceDiscoveryOptions {
  readonly enabled?: boolean;
  /** Refresh periodically while the page is visible (one owner per page). */
  readonly poll?: boolean;
}

/**
 * Fullmag instances on this host (ADR 0069). Discovery runs in the backend, so
 * closed ports never reach the browser console.
 */
export function useInstanceDiscovery({
  enabled = true,
  poll = false,
}: InstanceDiscoveryOptions = {}): ResourceResult<InstanceDiscoveryResource> {
  const { api } = useKernel();
  const load = useCallback(
    ({ signal }: { signal: AbortSignal }) => api.platform.instances({ signal }),
    [api],
  );
  const resource = useResource<InstanceDiscoveryResource>({
    enabled,
    load,
    // Every discovery probes the whole port window; shared refreshes of the
    // page must not run it more often than the strip's own cadence.
    minRefetchIntervalMs: INSTANCE_DISCOVERY_POLL_MS,
    notifyOnError: false,
    resolveRevision: () => null,
    resourceKey: PLATFORM_INSTANCES_PATH,
  });
  const refetch = resource.refetch;
  useEffect(() => {
    if (!enabled || !poll) return;
    const refreshVisible = () => {
      if (document.visibilityState === "visible") refetch();
    };
    const timer = window.setInterval(refreshVisible, INSTANCE_DISCOVERY_POLL_MS);
    document.addEventListener("visibilitychange", refreshVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", refreshVisible);
    };
  }, [enabled, poll, refetch]);
  return resource;
}
