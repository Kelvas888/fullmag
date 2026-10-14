import assert from "node:assert/strict";

/** Additional checks against the existing production UI fixture, not a solver oracle. */
export async function verifyClosedLoopVectorDisplay({ page, root, open, shot }) {
  const checks = [];
  const choose = async (label) => {
    await root.getByRole("combobox", { name: "Antenna quantity", exact: true }).click();
    await page.getByRole("option", { name: label, exact: true }).click();
  };
  const enable = async (label) => {
    const button = root.getByRole("button", { name: `Toggle ${label}`, exact: true });
    assert.equal(await button.isEnabled(), true);
    if (await button.getAttribute("aria-pressed") !== "true") await button.click();
  };
  const read = () => page.evaluate(() => window.__antennaFieldCanvas());
  for (const [quantity, label, count] of [
    ["current_density", "Current density J [A/m^2]", 1],
    ["current_density_per_ampere", "Inspection current J/Ic [1/m^2]", 1],
    ["magnetic_field", "Inspection Oersted field H [A/m]", 4],
    ["magnetic_field_per_ampere", "Inspection Oersted field H/Ic [1/m]", 4],
  ]) {
    await open("inspection-closed");
    await page.waitForFunction(() => document.querySelector('button[aria-label="Toggle Points"]')?.matches(":enabled"));
    const inspector = await root.elementHandle();
    await choose(label);
    await enable("Surface"); await enable("Points"); await enable("Vectors");
    await page.waitForFunction(([q, n]) => {
      const canvas = window.__antennaFieldCanvas?.();
      return canvas?.quantity === q && canvas.pointCount === n && canvas.glyphCount === n && canvas.surfaceTriangles === 4;
    }, [quantity, count]);
    assert.equal(await page.locator('[data-antenna-field-viewport] canvas').isVisible(), true);
    const initial = await read();
    const identities = state => [state.surfaceUuid, state.pointsUuid, state.materialUuid, state.paletteUuid];
    const expected = identities(initial);
    assert.ok(expected.every(Boolean));
    for (const component of ["x", "y", "z", "magnitude"]) {
      await root.getByRole("combobox", { name: "Component", exact: true }).selectOption(component);
      await page.waitForFunction(value => window.__antennaFieldCanvas?.().currentComponent === value,
        component === "magnitude" ? 0 : { x: 1, y: 2, z: 3 }[component]);
      const state = await read();
      assert.equal(state.glyphCount, count); assert.equal(state.surfaceTriangles, 4);
      assert.equal(state.lost, false); assert.ok(state.width > 0 && state.height > 0);
      assert.ok(Number.isFinite(state.minimum) && Number.isFinite(state.maximum));
      assert.deepEqual(identities(state), expected);
    }
    for (const palette of ["coolwarm", "viridis"]) {
      await root.getByRole("combobox", { name: "Point / vector palette", exact: true }).selectOption(palette);
      await page.waitForTimeout(150);
      assert.deepEqual(identities(await read()), expected);
    }
    assert.equal(await root.evaluate((element, previous) => element === previous, inspector), true);
    const before = await page.evaluate(() => window.__antennaVisualizationFixture.read().calls.length);
    await page.waitForTimeout(500);
    assert.equal(await page.evaluate(() => window.__antennaVisualizationFixture.read().calls.length), before);
    assert.deepEqual(await page.evaluate(() => window.__antennaVisualizationFixture.read().unexpected), []);
    await shot(`closed-loop-${quantity}-vectors`);
    await page.evaluate(() => window.__antennaVisualizationFixture.selectOther());
    await page.waitForFunction(() => window.__antennaFieldCanvas?.().sampleCount === 0 && window.__antennaFieldCanvas?.().paletteTextures === 0);
    checks.push(`${quantity}: complete glyphs, xyz/magnitude, stable geometry/material/LUT and Inspector, no idle reads, owner cleanup`);
  }
  // These scenarios must bind the helper's corresponding cancellation option.
  for (const [family, label, xShift, zShift] of [
    ["current", "Current density J [A/m^2]", 0, 0],
    ["magnetic", "Inspection Oersted field H [A/m]", 3e-7, 3e-8],
  ]) {
    await open(`inspection-closed-${family}-cancellation`);
    await page.waitForFunction(() => document.querySelector('button[aria-label="Toggle Points"]')?.matches(":enabled"));
    await choose(label); await enable("Surface");
    await root.getByRole("combobox", { name: "Component", exact: true }).selectOption("magnitude");
    await page.waitForFunction(() => window.__antennaFieldCanvas?.().surfaceTriangles === 4 && window.__antennaFieldCanvas?.().currentComponent === 0);
    const pixel = await page.evaluate(position => window.__antennaFieldPixel(position), [-4e-7/3+xShift,-1e-7/3,1e-7/3+zShift]);
    const reference = await page.evaluate(position => window.__antennaFieldPixel(position), [-0.4e-7+xShift,-0.8e-7,0.1e-7+zShift]);
    assert.ok(pixel[0] > 30 && pixel[1] < 45 && pixel[2] > 50 && pixel[3] === 255, `Wrong ${family} cancellation pixel: ${pixel}`);
    assert.ok(reference[1] > pixel[1]+50, `Missing ${family} magnitude contrast: ${reference}`);
    await shot(`closed-loop-${family}-vector-cancellation`);
    checks.push(`${family}: GPU pixel readback confirms norm after vector interpolation, cancellation=${pixel}, reference=${reference}`);
  }
  return checks;
}
