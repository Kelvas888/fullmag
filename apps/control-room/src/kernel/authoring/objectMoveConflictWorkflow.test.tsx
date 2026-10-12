import { act } from "react";
import { hydrateRoot, type Root } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ControlRoomApiError } from "@/kernel/api/ControlRoomApi";
import { MODEL_SCENE_PATH, SESSIONS_PATH, SIMULATION_PREPARATION_PATH } from "@/kernel/api/apiPaths";
import { CommandRegistry } from "@/kernel/commands/CommandRegistry";
import { DiagnosticRecorderController } from "@/kernel/performance/diagnostic-recorder/DiagnosticRecorderController";
import { EventBus } from "@/kernel/events/EventBus";
import type { KernelEventMap } from "@/kernel/events/eventTypes";
import { KernelContext } from "@/kernel/KernelContext";
import { LayoutController } from "@/kernel/layout/LayoutController";
import {
  TestEvent,
  TestElement,
  installSimulationPreparationTestDom,
} from "@/kernel/layout/simulationPreparationTestDom.test-support";
import { ResourceInvalidationController } from "@/kernel/resources/ResourceInvalidationController";
import {
  resetSharedResourceRuntimeStoreForTests,
  sharedResourceRuntimeStore,
} from "@/kernel/resources/ResourceRuntimeStore";
import { sessionScopedResourceKey } from "@/kernel/resources/sessionResourceIdentity";
import { SESSION_STATUS_RESOURCE_KEY } from "@/kernel/resources/useSessionStatus";
import { SelectionController } from "@/kernel/selection/SelectionController";
import type { KernelApi } from "@/kernel/types";
import { RIBBON_COMMANDS } from "@/modules/ribbon/ribbonCommands";
import { Viewport3DObjectMoveResourceSurface } from "@/modules/viewport-3d/Viewport3DObjectMoveInteraction";

import { ObjectMoveToolController } from "./ObjectMoveToolController";
import { commitObjectMoveWorkflow } from "./objectMoveConflictWorkflow";

// The scene hook reads the session-scoped key once identity is confirmed.
const SESSION_A_SCENE_KEY = sessionScopedResourceKey(
  {
    requestScopeEpoch: "test-api:session-a",
    sessionEpoch: "session-a@1",
    sessionId: "session-a",
  },
  MODEL_SCENE_PATH,
);

const SCENE_A_41 = scene(41, [
  { id: "magnet-a", role: "magnet", translation: [1e-9, 0, 0] },
  { id: "magnet-b", role: "magnet", translation: [0, 0, 0] },
]);

describe("mounted viewport object move integration", () => {
  afterEach(() => resetSharedResourceRuntimeStoreForTests());

  it("hydrates stably and drives command, pointer gesture, 409, real refetch, rebase, retry and ACK", async () => {
    const scene42 = scene(42, [
      { id: "magnet-a", role: "magnet", translation: [1e-9, 0, 0] },
      { id: "magnet-b", role: "magnet", translation: [0, 0, 0] },
    ]);
    const secondScene = deferred<typeof scene42>();
    const sceneLoad = vi
      .fn()
      .mockResolvedValueOnce(SCENE_A_41)
      .mockImplementationOnce(() => secondScene.promise)
      .mockResolvedValue(scene(43, [
        { id: "magnet-a", role: "magnet", translation: [5e-9, 0, 0] },
        { id: "magnet-b", role: "magnet", translation: [0, 0, 0] },
      ]));
    const commitTransaction = vi
      .fn()
      .mockRejectedValueOnce(
        new ControlRoomApiError("stale", 409, "request-1", "revision_conflict"),
      )
      .mockResolvedValueOnce({ scene_revision: 43 });
    const fixture = createFixture({ commitTransaction, sceneLoad });
    selectObject(fixture.selection, "magnet-a");
    const serverHtml = renderToString(
      <KernelContext.Provider value={fixture.kernel}>
        <Viewport3DObjectMoveResourceSurface />
      </KernelContext.Provider>,
    );
    // Scene loading is gated on a confirmed session identity, so the
    // deterministic server render stays idle until the client confirms it.
    expect(serverHtml).toContain('data-scene-status="idle"');
    expect(serverHtml).not.toContain("move-gizmo:magnet-a");

    const mounted = await hydrateFixture(fixture, serverHtml);
    try {
      expect(mounted.consoleError.mock.calls.flat().join(" ")).not.toContain("hydration");
      expect(surface(mounted.container).getAttribute("data-scene-status")).toBe("ready");

      await act(async () => {
        await fixture.commands.execute("geometry.move-selected", commandContext(fixture, SCENE_A_41));
      });
      const axis = moveAxis(mounted.container, "x", "magnet-a");
      const release = installPointerCapture(axis);

      await act(async () => {
        axis.dispatchEvent(pointerEvent("pointerdown", 7, [0, 0, 0]));
        axis.dispatchEvent(pointerEvent("pointermove", 7, [4e-9, 0, 0]));
      });
      expect(surface(mounted.container).getAttribute("data-orbit-blocked")).toBe("true");
      expect(commitTransaction).not.toHaveBeenCalled();

      await act(async () => {
        axis.dispatchEvent(pointerEvent("pointerup", 7, [4e-9, 0, 0]));
        await Promise.resolve();
      });
      expect(release).toHaveBeenCalledOnce();
      expect(surface(mounted.container).getAttribute("data-orbit-blocked")).toBe("false");
      expect(commitTransaction).toHaveBeenCalledTimes(1);
      expect(commitTransaction.mock.calls[0]?.[0]).toMatchObject({
        base_revision: 41,
        object_id: "magnet-a",
        transform: { translation: [5e-9, 0, 0] },
      });
      expect(commitTransaction.mock.calls[0]?.[1]).toEqual({
        sessionScopeKey: "session=session-a&epoch=session-a%401&request_scope_epoch=test-api%3Asession-a",
      });
      expect(conflictPanel(mounted.container)).not.toBeNull();
      expect(fixture.invalidate).not.toHaveBeenCalled();
      expect(surface(mounted.container).getAttribute("data-scene-status")).toBe("ready");
      expect(findButton(mounted.container, "Refetch Scene")?.disabled).toBe(false);

      await act(async () => clickButton(mounted.container, "Refetch Scene"));
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 0));
      });
      expect(conflictPanel(mounted.container)).not.toBeNull();
      expect(sceneLoad).toHaveBeenCalledTimes(2);
      expect(surface(mounted.container).getAttribute("data-scene-status")).toBe("stale");
      secondScene.resolve(scene42);
      await flushResource();
      expect(surface(mounted.container).getAttribute("data-scene-status")).toBe("ready");

      await act(async () => clickButton(mounted.container, "Rebase Draft"));
      expect(conflictPanel(mounted.container)?.getAttribute("data-move-conflict")).toBe("rebased");
      await act(async () => {
        clickButton(mounted.container, "Retry Move");
        await Promise.resolve();
      });
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 0));
      });

      expect(commitTransaction).toHaveBeenCalledTimes(2);
      expect(sceneLoad).toHaveBeenCalledTimes(3);
      expect(commitTransaction.mock.calls[1]?.[0]).toMatchObject({
        base_revision: 42,
        object_id: "magnet-a",
        transform: { translation: [5e-9, 0, 0] },
      });
      // Geometry dependents: scene, validation, diagnostics, readiness, status,
      // preparation, current mesh build and latest successful mesh build.
      expect(fixture.invalidate).toHaveBeenCalledTimes(8);
      expect(
        fixture.invalidate.mock.calls.every(([resourceKey, revision]) =>
          revision === (resourceKey === SIMULATION_PREPARATION_PATH ? "scene:43" : 43)
        ),
      ).toBe(true);
      expect(conflictPanel(mounted.container)).toBeNull();
      expect(surface(mounted.container).getAttribute("data-draft-reset-revision")).toBe("1");
      expect(surface(mounted.container).getAttribute("data-orbit-blocked")).toBe("false");
    } finally {
      await mounted.cleanup();
    }
  });

  it("blocks a second gesture and ignores a late ACK after selection A to B to A", async () => {
    const pendingAck = deferred<{ scene_revision: number }>();
    const commitTransaction = vi.fn(() => pendingAck.promise);
    const fixture = createFixture({ commitTransaction });
    selectObject(fixture.selection, "magnet-a");
    const mounted = await hydrateFixture(fixture);
    try {
      await activateMove(fixture, SCENE_A_41);
      const firstAxis = moveAxis(mounted.container, "x", "magnet-a");
      installPointerCapture(firstAxis);
      await act(async () => {
        firstAxis.dispatchEvent(pointerEvent("pointerdown", 13, [0, 0, 0]));
        firstAxis.dispatchEvent(pointerEvent("pointermove", 13, [4e-9, 0, 0]));
        firstAxis.dispatchEvent(pointerEvent("pointerup", 13, [4e-9, 0, 0]));
        await Promise.resolve();
      });
      expect(commitTransaction).toHaveBeenCalledOnce();

      await act(async () => selectObject(fixture.selection, "magnet-b"));
      await act(async () => selectObject(fixture.selection, "magnet-a"));
      await activateMove(fixture, SCENE_A_41);
      const secondAxis = moveAxis(mounted.container, "x", "magnet-a");
      const secondCapture = vi.fn();
      Object.assign(secondAxis, {
        releasePointerCapture: vi.fn(),
        setPointerCapture: secondCapture,
      });
      await act(async () => {
        secondAxis.dispatchEvent(pointerEvent("pointerdown", 14, [0, 0, 0]));
      });

      expect(secondCapture).not.toHaveBeenCalled();
      expect(commitTransaction).toHaveBeenCalledOnce();
      expect(surface(mounted.container).getAttribute("data-draft-reset-revision")).toBe("0");

      pendingAck.resolve({ scene_revision: 42 });
      await flushResource();

      expect(fixture.objectMoveTool.getSnapshot()?.objectId).toBe("magnet-a");
      expect(surface(mounted.container).getAttribute("data-draft-reset-revision")).toBe("0");
      expect(conflictPanel(mounted.container)).toBeNull();
      expect(commitTransaction).toHaveBeenCalledOnce();
    } finally {
      pendingAck.resolve({ scene_revision: 42 });
      await mounted.cleanup();
    }
  });

  it("expires A atomically for A to B to A, removal and role change without implicit reactivation", async () => {
    const fixture = createFixture();
    selectObject(fixture.selection, "magnet-a");
    const mounted = await hydrateFixture(fixture);
    try {
      await activateMove(fixture, SCENE_A_41);
      expect(moveAxis(mounted.container, "x", "magnet-a")).not.toBeNull();

      await act(async () => selectObject(fixture.selection, "magnet-b"));
      expect(fixture.objectMoveTool.getSnapshot()).toBeNull();
      await act(async () => selectObject(fixture.selection, "magnet-a"));
      expect(mounted.container.querySelector('[name="move-gizmo:magnet-a"]')).toBeNull();

      await activateMove(fixture, SCENE_A_41);
      sharedResourceRuntimeStore.updateData(
        SESSION_A_SCENE_KEY,
        scene(42, [{ id: "magnet-b", role: "magnet", translation: [0, 0, 0] }]),
        42,
      );
      await flushResource();
      expect(fixture.objectMoveTool.getSnapshot()).toBeNull();

      sharedResourceRuntimeStore.updateData(SESSION_A_SCENE_KEY, SCENE_A_41, 43);
      await flushResource();
      await activateMove(fixture, SCENE_A_41);
      sharedResourceRuntimeStore.updateData(
        SESSION_A_SCENE_KEY,
        scene(44, [{ id: "magnet-a", role: "auxiliary", translation: [1e-9, 0, 0] }]),
        44,
      );
      await flushResource();
      expect(fixture.objectMoveTool.getSnapshot()).toBeNull();
      expect(mounted.container.querySelector('[name="move-gizmo:magnet-a"]')).toBeNull();
    } finally {
      await mounted.cleanup();
    }
  });

  it("clears a 409 conflict on session identity change and cannot retry the stale object", async () => {
    const commitTransaction = vi.fn().mockRejectedValueOnce(
      new ControlRoomApiError("stale", 409, "request-1", "revision_conflict"),
    );
    const fixture = createFixture({ commitTransaction });
    selectObject(fixture.selection, "magnet-a");
    const mounted = await hydrateFixture(fixture);
    try {
      await activateMove(fixture, SCENE_A_41);
      const axis = moveAxis(mounted.container, "x", "magnet-a");
      installPointerCapture(axis);
      await act(async () => {
        axis.dispatchEvent(pointerEvent("pointerdown", 5, [0, 0, 0]));
        axis.dispatchEvent(pointerEvent("pointermove", 5, [2e-9, 0, 0]));
        axis.dispatchEvent(pointerEvent("pointerup", 5, [2e-9, 0, 0]));
        await Promise.resolve();
      });
      expect(conflictPanel(mounted.container)).not.toBeNull();

      // Session B is both current in the collection and reported by status, so
      // its identity is confirmed and A's cached scene/conflict must not leak.
      sharedResourceRuntimeStore.updateData(
        SESSIONS_PATH,
        sessionCollection("session-b"),
        "sessions:2",
      );
      sharedResourceRuntimeStore.updateData(
        SESSION_STATUS_RESOURCE_KEY,
        sessionStatus("session-b", "session-b@2", 42),
        42,
      );
      await flushResource();

      expect(fixture.objectMoveTool.getSnapshot()).toBeNull();
      expect(conflictPanel(mounted.container)).toBeNull();
      expect(surface(mounted.container).getAttribute("data-orbit-blocked")).toBe("false");
      expect(commitTransaction).toHaveBeenCalledOnce();
      expect(findButton(mounted.container, "Retry Move")).toBeNull();
    } finally {
      await mounted.cleanup();
    }
  });
});

describe("object move conflict workflow", () => {
  it("commits even when the before-scene history capture is unavailable and reports degraded history", async () => {
    const commitTransaction = vi.fn().mockResolvedValue({ scene_revision: 8 });
    const history = {
      getGeneration: () => 0,
      getSnapshot: () => ({ canRedo: false, canUndo: false, redoLabel: null, undoLabel: null, pending: false }),
      record: vi.fn(),
    };
    const api = {
      model: {
        commitTransaction,
        scene: vi.fn().mockRejectedValue(new Error("scene unavailable")),
      },
    };
    const onAcknowledged = vi.fn();
    const onConflict = vi.fn();
    const onHistoryDegraded = vi.fn();

    const committed = await commitObjectMoveWorkflow({
      api: api as never,
      baseRevision: 7,
      historyContext: {
        api: api as never,
        authoringHistory: history as never,
        isCurrentSessionScope: () => true,
        resourceData: {},
        selection: undefined,
        sessionScopeKey: "session=session-a&epoch=session-a%401&request_scope_epoch=api%3A1",
      },
      isCurrentSessionScope: () => true,
      objectId: "magnet-a",
      onAcknowledged,
      onConflict,
      onHistoryDegraded,
      resources: { invalidate: vi.fn() } as never,
      sessionScopeKey: "session=session-a&epoch=session-a%401&request_scope_epoch=api%3A1",
      translation: [2e-9, 0, 0],
    });

    expect(committed).toBe(true);
    expect(commitTransaction).toHaveBeenCalledWith(
      {
        base_revision: 7,
        kind: "commit_object_transform",
        object_id: "magnet-a",
        transform: { translation: [2e-9, 0, 0] },
      },
      { sessionScopeKey: "session=session-a&epoch=session-a%401&request_scope_epoch=api%3A1" },
    );
    expect(onAcknowledged).toHaveBeenCalledOnce();
    expect(onConflict).not.toHaveBeenCalled();
    expect(onHistoryDegraded).toHaveBeenCalledOnce();
    expect(history.record).not.toHaveBeenCalled();
  });
});

function createFixture(options: {
  commitTransaction?: ReturnType<typeof vi.fn>;
  sceneLoad?: ReturnType<typeof vi.fn>;
} = {}) {
  const bus = new EventBus<KernelEventMap>();
  const resources = new ResourceInvalidationController(bus);
  const selection = new SelectionController(bus);
  const layout = new LayoutController(bus);
  const objectMoveTool = new ObjectMoveToolController();
  const commands = new CommandRegistry();
  for (const command of RIBBON_COMMANDS) commands.register(command);
  const invalidate = vi.spyOn(resources, "invalidate");
  const sceneLoad = options.sceneLoad ?? vi.fn().mockResolvedValue(SCENE_A_41);
  const commitTransaction = options.commitTransaction ??
    vi.fn().mockResolvedValue({ scene_revision: 43 });
  const kernel = {
    api: {
      model: { commitTransaction, scene: sceneLoad },
      sessions: {
        current: { status: vi.fn().mockResolvedValue(sessionStatus("session-a", "session-a@1", 41)) },
        // Session identity is confirmed against the session collection.
        list: vi.fn().mockResolvedValue(sessionCollection("session-a")),
      },
    },
    bus,
    commands,
    diagnosticRecorder: new DiagnosticRecorderController({ config: { enabled: false } }),
    layout,
    objectMoveTool,
    resources,
    selection,
  } as unknown as KernelApi;
  return { commands, commitTransaction, invalidate, kernel, layout, objectMoveTool, resources, sceneLoad, selection };
}

async function hydrateFixture(
  fixture: ReturnType<typeof createFixture>,
  serverHtml = renderToString(
    <KernelContext.Provider value={fixture.kernel}>
      <Viewport3DObjectMoveResourceSurface />
    </KernelContext.Provider>,
  ),
) {
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
  // Session collection -> session status -> scoped scene: one hop per flush.
  for (let hop = 0; hop < 4; hop += 1) await flushResource();
  return {
    consoleError,
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
  currentScene: typeof SCENE_A_41,
) {
  await act(async () => {
    await fixture.commands.execute("geometry.move-selected", commandContext(fixture, currentScene));
  });
}

function commandContext(fixture: ReturnType<typeof createFixture>, currentScene: unknown) {
  return {
    api: fixture.kernel.api,
    layout: fixture.layout,
    objectMoveTool: fixture.objectMoveTool,
    resourceData: { [MODEL_SCENE_PATH]: currentScene },
    selection: fixture.selection,
    source: "test" as const,
  };
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
    session: { session_epoch: sessionEpoch, session_id: sessionId, request_scope_epoch: `test-api:${sessionId}` },
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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => { resolve = next; });
  return { promise, resolve };
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

function conflictPanel(container: TestElement): TestElement | null {
  return container.querySelector(".fm-viewport-3d__move-conflict");
}

function moveAxis(container: TestElement, axis: string, objectId: string): TestElement {
  return descendants(container, "mesh")
    .find((element) => element.getAttribute("name") === `move-axis:${axis}:${objectId}`)!;
}

function findButton(container: TestElement, label: string): TestElement | null {
  return descendants(container, "button").find((button) => button.textContent === label) ?? null;
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

function clickButton(container: TestElement, label: string): void {
  const button = findButton(container, label);
  if (!button) throw new Error(`Button not found: ${label}`);
  button.click();
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
