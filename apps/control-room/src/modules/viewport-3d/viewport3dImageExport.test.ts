import { afterEach, describe, expect, it, vi } from "vitest";
import { PerspectiveCamera, SRGBColorSpace, Vector2, Vector4, WebGLRenderTarget } from "three";

import {
  captureViewport3DImage,
  registerViewport3DCaptureSource,
  unpremultiplySrgbChannel,
  type Viewport3DCaptureSource,
} from "./viewport3dImageExport";

const unregister: Array<() => void> = [];

afterEach(() => {
  for (const cleanup of unregister.splice(0)) cleanup();
  vi.restoreAllMocks();
});

function register(canvas: HTMLCanvasElement, source: Viewport3DCaptureSource): void {
  unregister.push(registerViewport3DCaptureSource(canvas, source));
}

function captureCanvas(width = 16, height = 12): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

function rendererFor(canvasWidth = 16, canvasHeight = 12) {
  const renderer = {
    autoClear: false,
    autoClearColor: false,
    autoClearDepth: true,
    autoClearStencil: true,
    outputColorSpace: SRGBColorSpace,
    getClearAlpha: vi.fn(() => 0.5),
    getClearColor: vi.fn((target: { setHex: (value: number) => unknown }) => {
      target.setHex(0x123456);
      return target;
    }),
    getContext: vi.fn(() => ({ isContextLost: () => false })),
    getDrawingBufferSize: vi.fn((target: Vector2) => target.set(canvasWidth, canvasHeight)),
    getRenderTarget: vi.fn(() => null),
    getScissor: vi.fn((target: Vector4) => target.set(2, 3, 8, 9)),
    getScissorTest: vi.fn(() => true),
    getViewport: vi.fn((target: Vector4) => target.set(1, 4, 10, 11)),
    readRenderTargetPixels: vi.fn((_target, _x, _y, width: number, height: number, pixels: Uint8Array) => {
      for (let index = 0; index < width * height; index += 1) pixels[index * 4 + 3] = 255;
    }),
    clearDepth: vi.fn(),
    render: vi.fn(),
    setClearColor: vi.fn(),
    setRenderTarget: vi.fn(),
    setScissor: vi.fn(),
    setScissorTest: vi.fn(),
    setViewport: vi.fn(),
  };
  return renderer;
}

function fakeCanvasDocument(): {
  context: { drawImage: ReturnType<typeof vi.fn> };
  createdCanvases: HTMLCanvasElement[];
  document: Document;
} {
  const context = {
    createImageData: vi.fn((width: number, height: number) => ({ data: new Uint8ClampedArray(width * height * 4) })),
    drawImage: vi.fn(),
    putImageData: vi.fn(),
  };
  const createdCanvases: HTMLCanvasElement[] = [];
  const createElement = vi.fn(() => {
    const outputCanvas = {
      height: 0,
      width: 0,
      getContext: vi.fn(() => context),
      toBlob: vi.fn((callback: BlobCallback) => callback(new Blob(["png"], { type: "image/png" }))),
    };
    createdCanvases.push(outputCanvas as unknown as HTMLCanvasElement);
    return outputCanvas;
  });
  const document = {
    createElement: createElement as unknown as Document["createElement"],
    defaultView: { getComputedStyle: vi.fn() },
  } as unknown as Document;
  return { context, createdCanvases, document };
}

function offscreenCanvas(documentRef: Document): HTMLCanvasElement {
  const rect = { left: 0, top: 0, width: 16, height: 12, right: 16, bottom: 12 } as DOMRect;
  const root = { getBoundingClientRect: () => rect, querySelector: () => null };
  return {
    height: 12,
    width: 16,
    ownerDocument: documentRef,
    closest: vi.fn(() => root),
    getBoundingClientRect: () => rect,
  } as HTMLCanvasElement;
}

describe("unpremultiplySrgbChannel", () => {
  it("keeps opaque bytes unchanged and clears RGB for fully transparent pixels", () => {
    expect(unpremultiplySrgbChannel(137, 255)).toBe(137);
    expect(unpremultiplySrgbChannel(137, 0)).toBe(0);
  });

  it("unpremultiplies partially transparent sRGB in linear light", () => {
    // sRGB byte 137 represents linear 0.25; at alpha 128 it expands to about sRGB 187.
    expect(unpremultiplySrgbChannel(137, 128)).toBe(187);
    expect(unpremultiplySrgbChannel(255, 128)).toBe(255);
  });
});

describe("captureViewport3DImage", () => {
  it("reports a lost WebGL context with an actionable error", async () => {
    const canvas = captureCanvas();
    const renderer = rendererFor();
    renderer.getContext.mockReturnValue({ isContextLost: () => true });
    register(canvas, { camera: new PerspectiveCamera(), renderer: renderer as never, scene: {} as never });

    await expect(captureViewport3DImage(canvas, { background: "transparent", annotations: false }))
      .rejects.toThrow(/context was lost.*Reopen the viewport/i);
  });

  it("rejects an empty drawing buffer before allocating a render target", async () => {
    const canvas = captureCanvas(0, 0);
    const renderer = rendererFor(0, 0);
    register(canvas, { camera: new PerspectiveCamera(), renderer: renderer as never, scene: {} as never });

    await expect(captureViewport3DImage(canvas, { background: "view", annotations: false }))
      .rejects.toThrow(/drawing buffer is empty.*Resize the viewport/i);
    expect(renderer.render).not.toHaveBeenCalled();
  });

  it("restores render, background, camera-layer, and clear state after an offscreen capture", async () => {
    const { document: documentRef } = fakeCanvasDocument();
    const canvas = offscreenCanvas(documentRef);
    const renderer = rendererFor();
    const camera = new PerspectiveCamera();
    camera.layers.enable(31);
    const originalMask = camera.layers.mask;
    const originalBackground = { isColor: true };
    const scene = { background: originalBackground };
    renderer.render.mockImplementation(() => {
      expect(scene.background).toBeNull();
      expect(camera.layers.mask & (1 << 31)).toBe(0);
    });
    register(canvas, { camera, renderer: renderer as never, scene: scene as never });
    const dispose = vi.spyOn(WebGLRenderTarget.prototype, "dispose");

    const blob = await captureViewport3DImage(canvas, { background: "transparent", annotations: false });

    expect(blob.type).toBe("image/png");
    expect(scene.background).toBe(originalBackground);
    expect(camera.layers.mask).toBe(originalMask);
    expect(renderer.setRenderTarget).toHaveBeenLastCalledWith(null);
    expect(renderer.setViewport).toHaveBeenLastCalledWith(expect.objectContaining({ x: 1, y: 4, z: 10, w: 11 }));
    expect(renderer.setScissor).toHaveBeenLastCalledWith(expect.objectContaining({ x: 2, y: 3, z: 8, w: 9 }));
    expect(renderer.setScissorTest).toHaveBeenLastCalledWith(true);
    expect(renderer.setClearColor).toHaveBeenLastCalledWith(expect.objectContaining({ r: expect.any(Number) }), 0.5);
    expect(renderer.autoClear).toBe(false);
    expect(renderer.autoClearColor).toBe(false);
    expect(renderer.autoClearDepth).toBe(true);
    expect(renderer.autoClearStencil).toBe(true);
    expect(dispose).toHaveBeenCalledOnce();
  });

  it("restores and disposes the offscreen target when scene rendering throws", async () => {
    const { document: documentRef } = fakeCanvasDocument();
    const canvas = offscreenCanvas(documentRef);
    const renderer = rendererFor();
    const camera = new PerspectiveCamera();
    camera.layers.enable(31);
    const originalMask = camera.layers.mask;
    const scene = { background: { isColor: true } };
    const originalBackground = scene.background;
    renderer.render.mockImplementation(() => {
      throw new Error("render failed");
    });
    register(canvas, { camera, renderer: renderer as never, scene: scene as never });
    const dispose = vi.spyOn(WebGLRenderTarget.prototype, "dispose");

    await expect(captureViewport3DImage(canvas, { background: "transparent", annotations: false }))
      .rejects.toThrow("render failed");

    expect(scene.background).toBe(originalBackground);
    expect(camera.layers.mask).toBe(originalMask);
    expect(renderer.setRenderTarget).toHaveBeenLastCalledWith(null);
    expect(renderer.autoClear).toBe(false);
    expect(renderer.autoClearColor).toBe(false);
    expect(renderer.autoClearDepth).toBe(true);
    expect(renderer.autoClearStencil).toBe(true);
    expect(dispose).toHaveBeenCalledOnce();
  });

  it("renders transparent annotations in a separate layer-31 pass after clearing depth", async () => {
    const { document: documentRef } = fakeCanvasDocument();
    const canvas = offscreenCanvas(documentRef);
    const renderer = rendererFor();
    const camera = new PerspectiveCamera();
    camera.layers.enable(31);
    const scene = { background: { isColor: true } };
    renderer.render.mockImplementation(() => {
      if (renderer.render.mock.calls.length === 1) {
        expect(camera.layers.mask).toBe(1 << 0);
      } else {
        expect(camera.layers.mask).toBe(1 << 31);
        expect(renderer.autoClear).toBe(false);
      }
      expect(scene.background).toBeNull();
    });
    register(canvas, { camera, renderer: renderer as never, scene: scene as never });

    const blob = await captureViewport3DImage(canvas, { background: "transparent", annotations: true });

    expect(blob.type).toBe("image/png");
    expect(renderer.render).toHaveBeenCalledTimes(2);
    expect(renderer.clearDepth).toHaveBeenCalledOnce();
    expect(camera.layers.mask).toBe(1 | (1 << 31));
  });

  it("uses the composed opaque canvas even when DOM annotations are omitted", async () => {
    const fakeDocument = fakeCanvasDocument();
    const canvas = offscreenCanvas(fakeDocument.document);
    const renderer = rendererFor();
    register(canvas, { camera: new PerspectiveCamera(), renderer: renderer as never, scene: {} as never });

    const blob = await captureViewport3DImage(canvas, { background: "view", annotations: false });

    expect(blob.type).toBe("image/png");
    expect(fakeDocument.createdCanvases).toHaveLength(1);
    expect(fakeDocument.context.drawImage).toHaveBeenCalledWith(canvas, 0, 0, 16, 12);
    expect(renderer.render).not.toHaveBeenCalled();
  });

  it("does not let an old registration cleanup remove the replacement source", async () => {
    const canvas = captureCanvas();
    const oldSource = { camera: new PerspectiveCamera(), renderer: rendererFor() as never, scene: {} as never };
    const replacement = { camera: new PerspectiveCamera(), renderer: rendererFor() as never, scene: {} as never };
    const cleanupOld = registerViewport3DCaptureSource(canvas, oldSource);
    register(canvas, replacement);
    cleanupOld();
    (replacement.renderer as ReturnType<typeof rendererFor>).getContext.mockReturnValue({ isContextLost: () => true });

    await expect(captureViewport3DImage(canvas, { background: "view", annotations: true }))
      .rejects.toThrow(/context was lost/i);
  });
});
