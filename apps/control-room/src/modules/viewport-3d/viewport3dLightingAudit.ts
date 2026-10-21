import {
  Frustum,
  Matrix4,
  Mesh,
  MeshLambertMaterial,
  type Camera,
  type Scene,
} from "three";

export const VIEWPORT_3D_LIGHTING_AUDIT_METHOD =
  "three-scene-visible-world-layer-0-mesh-frustum-precomputed-bounds-lambert-visible-opacity" as const;

export interface Viewport3DLightingAudit {
  litPrimitiveMeshCount: number;
  otherSurfaceMeshCount: number;
  litPrimitiveObjectIds: string[];
  method: typeof VIEWPORT_3D_LIGHTING_AUDIT_METHOD;
}

/**
 * Reads the current Three scene/camera matrices and reports renderable lighting
 * candidates. This is not evidence of GPU draw calls or visible screenshot pixels.
 * Call after Three has updated the scene and camera matrices for the rendered frame.
 */
export function readViewport3DLightingAudit(
  scene: Scene,
  camera: Camera,
): Viewport3DLightingAudit {
  const viewProjection = new Matrix4().multiplyMatrices(
    camera.projectionMatrix,
    camera.matrixWorldInverse,
  );
  const frustum = new Frustum();
  frustum.setFromProjectionMatrix(viewProjection);

  const litPrimitiveObjectIds = new Set<string>();
  let litPrimitiveMeshCount = 0;
  let otherSurfaceMeshCount = 0;

  scene.traverseVisible((object) => {
    if (!(object instanceof Mesh) || !object.layers.isEnabled(0)) return;
    // Screen-space line quads are annotations, not lightable world surfaces.
    if ("isLineSegments2" in object && object.isLineSegments2 === true) return;

    if (isRenderableLitPrimitive(object, frustum)) {
      litPrimitiveMeshCount += 1;
      const objectId = object.userData.objectId;
      if (typeof objectId === "string" && objectId.length > 0) {
        litPrimitiveObjectIds.add(objectId);
      }
      return;
    }

    otherSurfaceMeshCount += 1;
  });

  return {
    litPrimitiveMeshCount,
    otherSurfaceMeshCount,
    litPrimitiveObjectIds: [...litPrimitiveObjectIds].sort(),
    method: VIEWPORT_3D_LIGHTING_AUDIT_METHOD,
  };
}

function isRenderableLitPrimitive(
  mesh: Mesh,
  frustum: Frustum,
): boolean {
  if (mesh.userData.primitive !== true || !hasVisibleLambertMaterials(mesh)) {
    return false;
  }

  const localSphere = mesh.geometry.boundingSphere;
  if (!localSphere || !isFiniteSphere(localSphere)) return false;

  const worldSphere = localSphere.clone().applyMatrix4(mesh.matrixWorld);
  return isFiniteSphere(worldSphere) && frustum.intersectsSphere(worldSphere);
}

function hasVisibleLambertMaterials(mesh: Mesh): boolean {
  const materials = Array.isArray(mesh.material)
    ? mesh.material
    : [mesh.material];

  return (
    materials.length > 0 &&
    materials.every(
      (material) =>
        material instanceof MeshLambertMaterial &&
        material.visible &&
        Number.isFinite(material.opacity) &&
        material.opacity > 0,
    )
  );
}

function isFiniteSphere(sphere: {
  center: { x: number; y: number; z: number };
  radius: number;
}): boolean {
  return (
    Number.isFinite(sphere.center.x) &&
    Number.isFinite(sphere.center.y) &&
    Number.isFinite(sphere.center.z) &&
    Number.isFinite(sphere.radius) &&
    sphere.radius >= 0
  );
}
