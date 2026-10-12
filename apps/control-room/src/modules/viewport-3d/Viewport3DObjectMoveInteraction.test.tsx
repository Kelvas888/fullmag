import { act } from "react";
import { hydrateRoot, type Root } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MODEL_SCENE_PATH } from "@/kernel/api/apiPaths";
import { CommandRegistry } from "@/kernel/commands/CommandRegistry";
import { DiagnosticRecorderController } from "@/kernel/performance/diagnostic-recorder/DiagnosticRecorderController";
import { EventBus } from "@/kernel/events/EventBus";
import type { KernelEventMap } from "@/kernel/events/eventTypes";
import { KernelContext } from "@/kernel/KernelContext";
import { LayoutController } from "@/kernel/layout/LayoutController";
import {
  TestElement,
  TestEvent,
  installSimulationPreparationTestDom,
} from "@/kernel/layout/simulationPreparationTestDom.test-support";
import { ObjectEditSessionController } from "@/kernel/authoring/object-edit/ObjectEditSessionController";
import {
  geometryObjectEditSessionTargetKey,
  resolveCommittedGeometryObjectDraft,
} from "@/kernel/authoring/object-edit/objectEditDraftModel";
import type { GeometryObjectDraft } from "@/kernel/authoring/object-edit/objectEditTypes";
import { ObjectMoveToolController } from "@/kernel/authoring/ObjectMoveToolController";
import { ResourceInvalidationController } from "@/kernel/resources/ResourceInvalidationController";
import {
  resetSharedResourceRuntimeStoreForTests,
} from "@/kernel/resources/ResourceRuntimeStore";
import { SelectionController } from "@/kernel/selection/SelectionController";
import type { KernelApi } from "@/kernel/types";
import { RIBBON_COMMANDS } from "@/modules/ribbon/ribbonCommands";

import { Viewport3DObjectMoveResourceSurface } from "./Viewport3DObjectMoveInteraction";

const SESSION_A_SCOPE_KEY =
  "session=session-a&epoch=session-a%401&request_scope_epoch=test-api%3Asession-a";
const SCENE_A_41 = scene(41, [
  { id: "magnet-a", role: "magnet", translation: [1e-9, 0, 0] },
  { id: "magnet-b", role: "magnet", translation: [0, 0, 0] },
]);

describe("viewport object move staged draft", () => {
  afterEach(() => resetSharedResourceRuntimeStoreForTests());

  it("stages pointerup in the shared geometry draft without a scene mutation", async () => {
    const fixture = createFixture();
    selectObject(fixture.selection, "magnet-a");
    const mounted = await hydrateFixture(fixture);
    try {
      const baseDraft = resolveCommittedGeometryObjectDraft(SCENE_A_41, "magnet-a");
      if (!baseDraft) throw new Error("Expected canonical test object draft");
      const identity = fixture.objectEditSession.activate({
        objectId: "magnet-a",
        sessionScopeKey: SESSION_A_SCOPE_KEY,
        targetKey: geometryObjectEditSessionTargetKey(
          SESSION_A_SCOPE_KEY,
          baseDraft,
        ),
      }, baseDraft);
      act(() => {
        fixture.objectEditSession.updateDraft(identity, (draft) => ({
          ...draft,
          length: "7e-9",
        }));
      });

      await activateMove(fixture, SCENE_A_41);
      const axis = moveAxis(mounted.container, "x", "magnet-a");
      const release = installPointerCapture(axis);
      await act(async () => {
        axis.dispatchEvent(pointerEvent("pointerdown", 7, [0, 0, 0]));
        axis.dispatchEvent(pointerEvent("pointermove", 7, [4e-9, 0, 0]));
        axis.dispatchEvent(pointerEvent("pointerup", 7, [4e-9, 0, 0]));
        await Promise.resolve();
      });

      expect(release).toHaveBeenCalledOnce();
      expect(surface(mounted.container).getAttribute("data-orbit-blocked")).toBe("false");
      expect(fixture.objectEditSession.getSnapshot()).toMatchObject({
        dirty: true,
        draft: {
          length: "7e-9",
          objectId: "magnet-a",
          translation: ["5e-9", "0", "0"],
        },
      });
      expect(fixture.commitTransaction).not.toHaveBeenCalled();
      expect(fixture.invalidate).not.toHaveBeenCalled();
    } finally {
      await mounted.cleanup();
    }
  });

  it("does not create a dirty draft or mutation for an axis click without movement", async () => {
    const fixture = createFixture();
    selectObject(fixture.selection, "magnet-a");
    const mounted = await hydrateFixture(fixture);
    try {
      await activateMove(fixture, SCENE_A_41);
      const axis = moveAxis(mounted.container, "x", "magnet-a");
      installPointerCapture(axis);
      await act(async () => {
        axis.dispatchEvent(pointerEvent("pointerdown", 8, [0, 0, 0]));
        axis.dispatchEvent(pointerEvent("pointerup", 8, [0, 0, 0]));
        await Promise.resolve();
      });

      expect(fixture.objectEditSession.getSnapshot()).toMatchObject({
        dirty: false,
        draft: null,
        identity: null,
      });
      expect(fixture.commitTransaction).not.toHaveBeenCalled();
      expect(fixture.invalidate).not.toHaveBeenCalled();
    } finally {
      await mounted.cleanup();
    }
  });
});

function createFixture() {
  const bus = new EventBus<KernelEventMap>();
  const resources = new ResourceInvalidationController(bus);
  const selection = new SelectionController(bus);
  const layout = new LayoutController(bus);
  const objectMoveTool = new ObjectMoveToolController();
  const objectEditSession = new ObjectEditSessionController<GeometryObjectDraft>();
  const commands = new CommandRegistry();
  for (const command of RIBBON_COMMANDS) commands.register(command);
  const invalidate = vi.spyOn(resources, "invalidate");
  const sceneLoad = vi.fn().mockResolvedValue(SCENE_A_41);
  const commitTransaction = vi.fn().mockResolvedValue({ scene_revision: 42 });
  const kernel = {
    api: {
      model: { commitTransaction, scene: sceneLoad },
      sessions: {
        current: {
          status: vi.fn().mockResolvedValue(sessionStatus("session-a", "session-a@1", 41)),
        },
        list: vi.fn().mockResolvedValue(sessionCollection("session-a")),
      },
    },
    bus,
    commands,
    diagnosticRecorder: new DiagnosticRecorderController({ config: { enabled: false } }),
    layout,
    objectEditSession,
    objectMoveTool,
    resources,
    selection,
  } as unknown as KernelApi;
  return {
    commitTransaction,
    invalidate,
    kernel,
    layout,
    objectEditSession,
    objectMoveTool,
    resources,
    selection,
  };
}

async function hydrateFixture(fixture: ReturnType<typeof createFixture>) {
  const serverHtml = renderToString(
    <KernelContext.Provider value={fixture.kernel}>
      <Viewport3DObjectMoveResourceSurface />
    </KernelContext.Provider>,
  );
  const dom = installSimulationPreparationTestDom();
  const container = dom.document.createElement("div");
  container.innerHTML = serverHtml;
  const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
  let root: Root;
  await act(async () => {
    root = hydrateRoot(
      container as unknown as Element,
      <KernelContext.Provider value={fixture.kernel}>
        <Viewport3DObjectMoveResourceSurface />
      </KernelContext.Provider>,
    );
    await Promise.resolve();
    await Promise.resolve();
  });
  for (let hop = 0; hop < 4; hop += 1) await flushResource();
  return {
    container,
    cleanup: async () => {
      await act(async () => root.unmount());
      consoleError.mockRestore();
      dom.restore();
    },
  };
}

async function activateMove(
  fixture: ReturnType<typeof createFixture>,
  currentScene: unknown,
) {
  await act(async () => {
    await fixture.commands.execute("geometry.move-selected", {
      api: fixture.kernel.api,
      layout: fixture.layout,
      objectMoveTool: fixture.objectMoveTool,
      resourceData: { [MODEL_SCENE_PATH]: currentScene },
      selection: fixture.selection,
      source: "test",
    });
  });
}

function selectObject(selection: SelectionController, objectId: string): void {
  selection.set({
    kind: "object.root",
    label: objectId,
    nodeId: `model:object:${objectId}`,
    objectId,
    ref: {
      kind: "object.root",
      nodeId: `model:object:${objectId}`,
      objectId,
      type: "scene-object",
      visualizationTargetId: `object:${objectId}`,
    },
  }, "test");
}

function scene(
  revision: number,
  objects: Array<{ id: string; role: string; translation: number[] }>,
) {
  return {
    objects: objects.map((object) => ({
      geometry: { geometry_kind: "Box", geometry_params: { size: [2e-9, 2e-9, 2e-9] } },
      id: object.id,
      name: object.id,
      role: object.role,
      transform: { translation: object.translation },
    })),
    revision,
  };
}

function sessionStatus(sessionId: string, sessionEpoch: string, revision: number) {
  return {
    resources: { scene_revision: revision },
    session: {
      session_epoch: sessionEpoch,
      session_id: sessionId,
      request_scope_epoch: `test-api:${sessionId}`,
    },
  } as never;
}

function sessionCollection(currentSessionId: string) {
  return {
    schema_version: "2.0.0",
    sessions: [
      {
        current: true,
        name: currentSessionId,
        session_id: currentSessionId,
        status: "running",
      },
    ],
  };
}

async function flushResource(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
    await Promise.resolve();
    await Promise.resolve();
  });
}

function surface(container: TestElement): TestElement {
  return container.querySelector(".fm-viewport-3d__move-resource-surface")!;
}

function moveAxis(container: TestElement, axis: string, objectId: string): TestElement {
  return descendants(container, "mesh")
    .find((element) => element.getAttribute("name") === `move-axis:${axis}:${objectId}`)!;
}

function descendants(container: TestElement, tagName: string): TestElement[] {
  const matches: TestElement[] = [];
  const visit = (element: TestElement) => {
    for (const child of element.childNodes) {
      if (!(child instanceof TestElement)) continue;
      if (child.tagName.toLowerCase() === tagName) matches.push(child);
      visit(child);
    }
  };
  visit(container);
  return matches;
}

function pointerEvent(
  type: string,
  pointerId: number,
  point: [number, number, number],
): TestEvent {
  const event = new TestEvent(type, { bubbles: true }) as TestEvent & {
    point: { x: number; y: number; z: number };
    pointerId: number;
  };
  event.pointerId = pointerId;
  event.point = { x: point[0], y: point[1], z: point[2] };
  return event;
}

function installPointerCapture(element: TestElement) {
  const release = vi.fn();
  Object.assign(element, {
    releasePointerCapture: release,
    setPointerCapture: vi.fn(),
  });
  return release;
}
