"use client";

import { useSyncExternalStore } from "react";

import type { ObjectEditSessionController } from "./ObjectEditSessionController";
import type {
  ObjectEditSessionSnapshot,
  GeometryObjectDraft,
} from "./objectEditTypes";

export function useObjectEditSelector(
  controller: ObjectEditSessionController<GeometryObjectDraft>,
): ObjectEditSessionSnapshot<GeometryObjectDraft> {
  return useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getServerSnapshot,
  );
}
