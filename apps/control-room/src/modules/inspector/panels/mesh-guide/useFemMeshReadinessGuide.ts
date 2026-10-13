"use client";

import { useMemo } from "react";

import * as geometryLifecycleResources from "@/kernel/resources/geometryLifecycleResources";
import { useSessionStatusSelector } from "@/kernel/resources/useSessionStatus";

import {
  evaluateFemMeshReadinessGuide,
  type FemMeshReadinessGuideModel,
} from "./femMeshReadinessGuide";

type OptionalResourceHook<T> = (options?: { enabled?: boolean }) => {
  data: T | null;
  status?: string;
};

function getOptionalLifecycleHook<T>(
  hookName: keyof typeof geometryLifecycleResources,
): OptionalResourceHook<T> | undefined {
  try {
    const candidate = geometryLifecycleResources[hookName];
    return typeof candidate === "function"
      ? (candidate as unknown as OptionalResourceHook<T>)
      : undefined;
  } catch {
    return undefined;
  }
}

function useOptionalResource<T>(
  hookName: keyof typeof geometryLifecycleResources,
  options: { enabled: boolean },
): { data: T | null; status: string } {
  const hook = getOptionalLifecycleHook<T>(hookName);
  if (typeof hook === "function") {
    return hook(options) as { data: T | null; status: string };
  }
  return { data: null, status: "idle" };
}

function useOptionalScopedResource<T>(
  hookName: keyof typeof geometryLifecycleResources,
  id: string | null | undefined,
  options: { enabled: boolean },
): { data: T | null; status: string } {
  let hook: unknown;
  try {
    hook = geometryLifecycleResources[hookName];
  } catch {
    hook = undefined;
  }
  if (typeof hook === "function") {
    return (
      hook as (
        targetId: string | null | undefined,
        hookOptions?: { enabled?: boolean },
      ) => { data: T | null; status: string }
    )(id, options);
  }
  return { data: null, status: "idle" };
}

export function useFemMeshReadinessGuide(options?: {
  enabled?: boolean;
  selectedObjectId?: string | null;
}): FemMeshReadinessGuideModel | null {
  const discretization = useSessionStatusSelector(
    (status) => status.data?.domain?.discretization ?? null,
  );
  const normalizedLane =
    typeof discretization === "string"
      ? discretization.trim().toLowerCase()
      : "";
  const femEnabled = options?.enabled !== false && normalizedLane === "fem";

  const scene = useOptionalResource("useSceneResource", {
    enabled: femEnabled,
  });
  const geometryValidation = useOptionalResource(
    "useGeometryValidationResource",
    { enabled: femEnabled },
  );
  const universePolicy = useOptionalResource("useUniverseMeshPolicyResource", {
    enabled: femEnabled,
  });
  const sharedDomainPolicy = useOptionalResource(
    "useMeshSharedDomainPolicyResource",
    { enabled: femEnabled },
  );
  const meshSemantics = useOptionalResource("useMeshSemanticsResource", {
    enabled: femEnabled,
  });
  const meshSummary = useOptionalResource("useMeshSummaryResource", {
    enabled: femEnabled,
  });
  const activeBuild = useOptionalResource("useMeshBuildCurrent", {
    enabled: femEnabled,
  });
  const latestBuild = useOptionalResource("useMeshBuildLatestSuccessful", {
    enabled: femEnabled,
  });
  const qualityGates = useOptionalResource(
    "useMeshSharedDomainQualityResource",
    {
      enabled: femEnabled,
    },
  );
  const selectedObjectPolicy = useOptionalScopedResource(
    "useObjectMeshPolicyResource",
    options?.selectedObjectId,
    { enabled: femEnabled && Boolean(options?.selectedObjectId) },
  );

  return useMemo(() => {
    if (!femEnabled) return null;

    return evaluateFemMeshReadinessGuide({
      activeBuild: activeBuild.data,
      geometryValidation: geometryValidation.data,
      latestBuild: latestBuild.data,
      meshSemantics: meshSemantics.data,
      meshSummary: meshSummary.data,
      qualityGates: qualityGates.data,
      scene: scene.data,
      selectedObjectId: options?.selectedObjectId ?? null,
      selectedObjectPolicy: selectedObjectPolicy.data,
      sharedDomainPolicy: sharedDomainPolicy.data,
      universePolicy: universePolicy.data,
    });
  }, [
    activeBuild.data,
    femEnabled,
    geometryValidation.data,
    latestBuild.data,
    meshSemantics.data,
    meshSummary.data,
    options?.selectedObjectId,
    qualityGates.data,
    scene.data,
    selectedObjectPolicy.data,
    sharedDomainPolicy.data,
    universePolicy.data,
  ]);
}
