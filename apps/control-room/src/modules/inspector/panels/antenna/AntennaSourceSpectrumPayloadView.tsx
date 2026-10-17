"use client";

import { useId, useMemo, useRef, useState, type ReactNode } from "react";

import type {
  AntennaSourceSpectrumResource,
  BinaryResourceResult,
} from "@/kernel/api/apiTypes";
import { antennaSpectrumPayloadByteLengths } from "@/kernel/api/codecs/antennaSpectrumManifestCodec";
import { ControlRoomApiError } from "@/kernel/api/ControlRoomApi";
import {
  antennaSpectrumPayloadEtag,
  useAntennaSourceSpectrumPayloadResource,
} from "@/kernel/resources/antennaResources";
import type { ResourceResult } from "@/kernel/resources/resourceTypes";
import { Button } from "@/shared/ui/Button";

import { useAntennaSpectrumGridCompatibility, type AntennaSpectrumKGrid } from "./useAntennaSpectrumGridCompatibility";
import { AntennaSpectrumExport } from "./AntennaSpectrumExport";

const MAX_AXIS_CELLS = 64;
const MAX_DISPLAY_PAYLOAD_BYTES = 64 * 1024 * 1024;

interface SpectrumPayloadViewProps {
  outputId: string;
  spectrum: AntennaSourceSpectrumResource;
  expectedKGrid?: AntennaSpectrumKGrid;
}

interface DecodedPayloads {
  amplitudes: number[];
  kU: number[];
  kV: number[];
  power: number[];
}

interface HeatmapCell {
  kUIndex: number;
  kVIndex: number;
  normalizedPower: number;
  power: number;
}

type SpectrumPayloadResource = Pick<
  ResourceResult<BinaryResourceResult<ArrayBuffer> | null>,
  "data" | "error" | "refreshError" | "status"
>;

function useSpectrumPayloadSnapshot({ data, error, refreshError, status }: SpectrumPayloadResource) {
  return useMemo(() => ({ data, error, refreshError, status }), [data, error, refreshError, status]);
}

export function AntennaSourceSpectrumPayloadView({
  outputId,
  spectrum,
  expectedKGrid,
}: SpectrumPayloadViewProps) {
  const manifest = useMemo(() => {
    try {
      const lengths = antennaSpectrumPayloadByteLengths(spectrum);
      if (lengths.total > MAX_DISPLAY_PAYLOAD_BYTES) throw new Error("Antenna spectrum exceeds the 64 MiB interactive display budget. No binary payload was requested.");
      return {
        kind: "ready" as const,
        lengths,
        etags: {
          k_u_rad_per_m: antennaSpectrumPayloadEtag(spectrum, "k_u_rad_per_m"),
          k_v_rad_per_m: antennaSpectrumPayloadEtag(spectrum, "k_v_rad_per_m"),
          amplitudes_re_im: antennaSpectrumPayloadEtag(spectrum, "amplitudes_re_im"),
          power: antennaSpectrumPayloadEtag(spectrum, "power"),
        },
      };
    } catch (error) {
      return { kind: "error" as const,
        error: error instanceof Error ? error : new Error("spectrum manifest validation failed") };
    }
  }, [spectrum]);
  const gridCompatibility = useAntennaSpectrumGridCompatibility(spectrum, expectedKGrid, manifest.kind === "ready");
  const payloadsEnabled = manifest.kind === "ready" && gridCompatibility.kind === "ready";
  const kU = useSpectrumPayloadSnapshot(useAntennaSourceSpectrumPayloadResource(outputId, "k_u_rad_per_m", {
    enabled: payloadsEnabled,
    expectedEtag: manifest.kind === "ready" ? manifest.etags.k_u_rad_per_m : undefined,
    maxResponseBytes: manifest.kind === "ready" ? manifest.lengths.payloads.k_u_rad_per_m : undefined,
  }));
  const kV = useSpectrumPayloadSnapshot(useAntennaSourceSpectrumPayloadResource(outputId, "k_v_rad_per_m", {
    enabled: payloadsEnabled,
    expectedEtag: manifest.kind === "ready" ? manifest.etags.k_v_rad_per_m : undefined,
    maxResponseBytes: manifest.kind === "ready" ? manifest.lengths.payloads.k_v_rad_per_m : undefined,
  }));
  const amplitudes = useSpectrumPayloadSnapshot(useAntennaSourceSpectrumPayloadResource(
    outputId,
    "amplitudes_re_im",
    {
      enabled: payloadsEnabled,
      expectedEtag: manifest.kind === "ready" ? manifest.etags.amplitudes_re_im : undefined,
      maxResponseBytes: manifest.kind === "ready" ? manifest.lengths.payloads.amplitudes_re_im : undefined,
    },
  ));
  const power = useSpectrumPayloadSnapshot(useAntennaSourceSpectrumPayloadResource(outputId, "power", {
    enabled: payloadsEnabled,
    expectedEtag: manifest.kind === "ready" ? manifest.etags.power : undefined,
    maxResponseBytes: manifest.kind === "ready" ? manifest.lengths.payloads.power : undefined,
  }));
  const payloads = useMemo(() => {
    if (!payloadsEnabled) return { kind: "pending" as const };
    const decoded = decodePayloads(kU, kV, amplitudes, power);
    if (decoded.kind !== "ready") return decoded;
    const integrityError = validatePayloads(decoded.value, spectrum, expectedKGrid);
    if (integrityError) return { kind: "integrity-error" as const, error: integrityError };
    return {
      ...decoded,
      cells: heatmapCells(decoded.value.kU, decoded.value.kV, decoded.value.power),
      extrema: spectrumPowerExtrema(decoded.value.power),
      rangeU: spectrumPowerExtrema(decoded.value.kU),
      rangeV: spectrumPowerExtrema(decoded.value.kV),
    };
  }, [amplitudes, kU, kV, payloadsEnabled, power, spectrum, expectedKGrid]);

  if (manifest.kind === "error") {
    return (
      <section className="fm-antenna-spectrum" aria-label="Antenna source spectrum payload">
        <p className="fm-antenna-spectrum__status fm-antenna-spectrum__status--error" role="alert">
          FFT manifest unavailable: {formatPayloadError(manifest.error)}
        </p>
      </section>
    );
  }

  if (gridCompatibility.kind !== "ready") {
    return <section className="fm-antenna-spectrum" aria-label="Antenna source spectrum payload">
      <p className={gridCompatibility.kind === "error" ? "fm-antenna-spectrum__status fm-antenna-spectrum__status--error" : "fm-antenna-spectrum__status"} role={gridCompatibility.kind === "error" ? "alert" : "status"}>
        {gridCompatibility.kind === "error" ? `FFT configuration unavailable: ${gridCompatibility.error}` : "Verifying authored wave-vector grid…"}
      </p>
    </section>;
  }

  if (payloads.kind === "pending") {
    return (
      <section className="fm-antenna-spectrum" aria-label="Antenna source spectrum payload">
        <p className="fm-antenna-spectrum__status" role="status">
          Loading binary FFT payloads…
        </p>
      </section>
    );
  }
  if (payloads.kind === "error") {
    return (
      <section className="fm-antenna-spectrum" aria-label="Antenna source spectrum payload">
        <p className="fm-antenna-spectrum__status fm-antenna-spectrum__status--error" role="alert">
          FFT payload unavailable: {formatPayloadError(payloads.error)}
        </p>
      </section>
    );
  }

  if (payloads.kind === "integrity-error") {
    return (
      <section className="fm-antenna-spectrum" aria-label="Antenna source spectrum payload">
        <p className="fm-antenna-spectrum__status fm-antenna-spectrum__status--error" role="alert">
          FFT payload integrity error: {payloads.error}
        </p>
      </section>
    );
  }

  const { cells, extrema, rangeU, rangeV } = payloads;
  const peak = extrema ? { index: extrema.peakIndex, value: extrema.maximum } : null;
  const peakKU = peak ? payloads.value.kU[peak.index % payloads.value.kU.length] : null;
  const peakKV = peak
    ? payloads.value.kV[Math.floor(peak.index / payloads.value.kU.length)]
    : null;
  const renderedCellCount = cells.length;
  const isBinned = payloads.value.kU.length > MAX_AXIS_CELLS ||
    payloads.value.kV.length > MAX_AXIS_CELLS;
  const powerUnit = spectrum.payloads?.power.unit ?? `(${spectrum.amplitude_unit})^2`;
  const transverse = spectrum.component === "transverse";
  const componentLabel = transverse ? "H transverse (x, y, z)" : spectrum.component === "vector_power" ? "H vector (x, y, z)" : `H_${spectrum.component}`;
  const powerExpression = transverse ? "|H\u22a5_x|² + |H\u22a5_y|² + |H\u22a5_z|²" : spectrum.component === "vector_power"
    ? "|H_x|² + |H_y|² + |H_z|²" : `|H_${spectrum.component}|²`;
  const normalizationLabel = spectrum.normalization === "integral_si" ? "Integral SI" : "Unitary discrete";

  return (
    <section className="fm-antenna-spectrum" aria-label="Antenna source spectrum payload">
      <div className="fm-antenna-spectrum__header">
        <div>
          <h3 className="fm-antenna-spectrum__title">Source FFT power · {componentLabel}</h3>
          <p className="fm-antenna-spectrum__subtitle">
            {powerExpression} at (k<sub>u</sub>, k<sub>v</sub>) · {normalizationLabel} normalization
            {" · "}per 1 A port-current basis; drive waveform not applied
          </p>
        </div>
        <span className="fm-antenna-spectrum__badge" data-status="ready">
          {isBinned ? "max-pooled" : "full grid"}
        </span>
      </div>
      <SpectrumPowerGrid cells={cells} kU={payloads.value.kU} kV={payloads.value.kV}
        amplitudes={payloads.value.amplitudes} componentLabels={spectrum.component_labels} amplitudeUnit={spectrum.amplitude_unit}
        waveVectorUnit={spectrum.wave_vector_unit} powerUnit={powerUnit} componentPrefix={transverse ? "H\u22a5" : "H"} componentLabel={componentLabel} isBinned={isBinned} peakIndex={extrema?.peakIndex ?? -1}>
        <AntennaSpectrumExport spectrum={spectrum} amplitudes={payloads.value.amplitudes}
          kU={payloads.value.kU} kV={payloads.value.kV} power={payloads.value.power} />
      </SpectrumPowerGrid>
      {extrema ? <SpectrumPowerScale minimum={extrema.minimum} maximum={extrema.maximum} unit={powerUnit} /> : null}
      <div className="fm-antenna-spectrum__axes" aria-label="Source spectrum axes">
        <span>u: {Math.min(MAX_AXIS_CELLS, payloads.value.kU.length)} / {payloads.value.kU.length} · {spectrum.wave_vector_unit}</span>
        <span>v: {Math.min(MAX_AXIS_CELLS, payloads.value.kV.length)} / {payloads.value.kV.length} · {spectrum.wave_vector_unit}</span>
        <span>k_u range: {formatScientific(rangeU?.minimum)} … {formatScientific(rangeU?.maximum)} {spectrum.wave_vector_unit}</span>
        <span>k_v range: {formatScientific(rangeV?.minimum)} … {formatScientific(rangeV?.maximum)} {spectrum.wave_vector_unit}</span>
        <span>cells: {renderedCellCount}{isBinned ? " (max-pooled)" : ""}</span>
      </div>
      <div className="fm-antenna-spectrum__summary" aria-label="Source spectrum peak">
        <span>
          Peak {peak ? formatScientific(peak.value) : "unavailable"} {powerUnit}
        </span>
        <span>
          k=({peakKU === null ? "—" : formatScientific(peakKU)}, {peakKV === null ? "—" : formatScientific(peakKV)}) {spectrum.wave_vector_unit}
        </span>
      </div>
    </section>
  );
}

function spectrumPowerExtrema(power: readonly number[]): { minimum: number; maximum: number; peakIndex: number } | null {
  let minimum = Infinity;
  let maximum = -Infinity;
  let peakIndex = -1;
  for (let index = 0; index < power.length; index += 1) {
    const value = power[index]!;
    if (!Number.isFinite(value)) continue;
    minimum = Math.min(minimum, value);
    if (value > maximum) { maximum = value; peakIndex = index; }
  }
  return peakIndex < 0 ? null : { minimum, maximum, peakIndex };
}

function SpectrumPowerScale({ minimum, maximum, unit }: { minimum: number; maximum: number; unit: string }) {
  return <div className="fm-antenna-spectrum__scale" role="group" aria-label="Source spectrum color scale">
    {minimum === maximum ? <span>Uniform power: {formatScientific(minimum)} {unit}</span> : <>
      <span>Linear power scale</span>
      <span>{formatScientific(minimum)} {unit}</span>
      <span className="fm-antenna-spectrum__scale-bar" aria-hidden="true" />
      <span>{formatScientific(maximum)} {unit}</span>
    </>}
  </div>;
}

function spectrumGridTarget(key: string, index: number, columns: number, count: number, wholeGrid = false): number | null {
  const rowStart = Math.floor(index / columns) * columns;
  const rowEnd = Math.min(count - 1, rowStart + columns - 1);
  switch (key) {
    case "ArrowLeft": return Math.max(rowStart, index - 1);
    case "ArrowRight": return Math.min(rowEnd, index + 1);
    case "ArrowUp": return index >= columns ? index - columns : index;
    case "ArrowDown": return index + columns < count ? index + columns : index;
    case "Home": return wholeGrid ? 0 : rowStart;
    case "End": return wholeGrid ? count - 1 : rowEnd;
    default: return null;
  }
}

/** Selection stays local: keyboard inspection never redecodes payloads or refetches resources. */
function SpectrumPowerGrid({ cells, kU, kV, amplitudes, componentLabels, amplitudeUnit, waveVectorUnit, powerUnit, componentPrefix, componentLabel, isBinned, peakIndex, children }: {
  cells: readonly HeatmapCell[]; kU: readonly number[]; kV: readonly number[];
  amplitudes: readonly number[]; componentLabels: readonly string[]; amplitudeUnit: string;
  waveVectorUnit: string; powerUnit: string; componentPrefix: string; componentLabel: string; isBinned: boolean; peakIndex: number; children: ReactNode;
}) {
  const [activeIndex, setActiveIndex] = useState(0);
  const helpId = useId();
  const gridRef = useRef<HTMLDivElement>(null);
  const peakCellIndex = useMemo(() => cells.findIndex(cell =>
    cell.kVIndex * kU.length + cell.kUIndex === peakIndex), [cells, kU.length, peakIndex]);
  const columns = Math.min(MAX_AXIS_CELLS, kU.length);
  const rows = Math.ceil(cells.length / columns);
  const selectedIndex = Math.min(activeIndex, cells.length - 1);
  const selected = cells[selectedIndex];
  return <>
    <div className="fm-antenna-spectrum__axes" role="group" aria-label="Source spectrum actions">
      {children}
      <Button size="sm" variant="secondary" disabled={peakCellIndex < 0} onClick={() => {
        gridRef.current?.querySelector<HTMLElement>(`[data-spectrum-cell-index="${peakCellIndex}"]`)?.focus();
      }}>Inspect peak</Button>
    </div>
    <p id={helpId} className="fm-antenna-spectrum__subtitle">
      Arrow keys inspect cells. Home/End move within a row; Ctrl+Home/End move to the grid edges.
      Cells follow the published k-grid order. Cell spacing represents sample indices, not k-distance; pooled cells report their strongest sample.
    </p>
    <div ref={gridRef} className="fm-antenna-spectrum__heatmap" role="grid"
      aria-label={`${cells.length} source-spectrum power cells`} aria-describedby={helpId}
      aria-rowcount={rows} aria-colcount={columns}
      style={{ gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))` }}>
      {Array.from({ length: rows }, (_, row) => <div role="row" aria-rowindex={row + 1}
        className="fm-antenna-spectrum__row" key={row}
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
        {cells.slice(row * columns, (row + 1) * columns).map((cell, column) => {
          const index = row * columns + column;
          const label = `${isBinned ? "bin maximum at " : ""}k_u=${formatScientific(kU[cell.kUIndex])} ${waveVectorUnit}, k_v=${formatScientific(kV[cell.kVIndex])} ${waveVectorUnit}, power=${formatScientific(cell.power)} ${powerUnit}`;
          return <span role="gridcell" key={`${cell.kVIndex}:${cell.kUIndex}`}
            className="fm-antenna-spectrum__cell" aria-colindex={column + 1}
            aria-label={label} title={label} aria-selected={index === selectedIndex}
            data-spectrum-cell-index={index} tabIndex={index === selectedIndex ? 0 : -1}
            onFocus={() => setActiveIndex(index)} onClick={(event) => event.currentTarget.focus()}
            onKeyDown={(event) => {
              const next = spectrumGridTarget(event.key, index, columns, cells.length, event.ctrlKey || event.metaKey);
              if (next === null) return;
              event.preventDefault();
              event.currentTarget.closest('[role="grid"]')
                ?.querySelector<HTMLElement>(`[data-spectrum-cell-index="${next}"]`)?.focus();
            }}
            style={{ background: `color-mix(in srgb, var(--fm-accent) ${8 + 92 * cell.normalizedPower}%, var(--fm-bg-panel-raised))` }} />;
        })}
      </div>)}
    </div>
    <div className="fm-antenna-spectrum__sample" role="group" aria-label="Selected source spectrum sample">
      <span>{isBinned ? "Bin maximum" : "Selected sample"} · {componentLabel}</span>
      <span>k_u {formatScientific(selected ? kU[selected.kUIndex] : undefined)} {waveVectorUnit}</span>
      <span>k_v {formatScientific(selected ? kV[selected.kVIndex] : undefined)} {waveVectorUnit}</span>
      <span>Power {formatScientific(selected?.power)} {powerUnit}</span>
    </div>
    {selected ? <div className="fm-antenna-spectrum__complex-sample">
      <table>
        <caption>Complex source amplitudes at selected sample</caption>
        <thead><tr>
          <th scope="col">Component</th>
          <th scope="col">Re [{amplitudeUnit}]</th>
          <th scope="col">Im [{amplitudeUnit}]</th>
          <th scope="col">Amplitude [{amplitudeUnit}]</th>
          <th scope="col">Phase [rad]</th>
        </tr></thead>
        <tbody>{componentLabels.map((label, component) => {
          const sample = selected.kVIndex * kU.length + selected.kUIndex;
          const offset = 2 * (component * kU.length * kV.length + sample);
          const re = amplitudes[offset]!, im = amplitudes[offset + 1]!;
          return <tr key={label}>
            <th scope="row">{componentPrefix}_{label}</th>
            <td>{formatScientific(re)}</td><td>{formatScientific(im)}</td>
            <td>{formatScientific(Math.hypot(re, im))}</td>
            <td>{re === 0 && im === 0 ? "undefined (zero amplitude)" : Math.atan2(im, re).toFixed(4)}</td>
          </tr>;
        })}</tbody>
      </table>
      <p className="fm-antenna-spectrum__subtitle">Phase is arg(Re + i Im) in the published Fourier convention; undefined at zero amplitude. Values use the same per-ampere basis and normalization as the map.</p>
    </div> : null}
  </>;
}

function decodePayloads(
  kU: SpectrumPayloadResource,
  kV: SpectrumPayloadResource,
  amplitudes: SpectrumPayloadResource,
  power: SpectrumPayloadResource,
):
  | { kind: "pending" }
  | { kind: "error"; error: Error }
  | { kind: "ready"; value: DecodedPayloads } {
  const resources = [kU, kV, amplitudes, power];
  const error = resources.find((resource) => resource.status === "error" || resource.error || resource.refreshError);
  if (error) {
    return { kind: "error", error: error.error ?? error.refreshError ?? new Error("binary request failed") };
  }
  if (resources.some((resource) => resource.status === "idle" || resource.status === "loading" || resource.status === "stale")) {
    return { kind: "pending" };
  }
  if (resources.some((resource) => !resource.data)) {
    return { kind: "error", error: new Error("binary payload is not published") };
  }
  const results = resources.map((resource) => resource.data);
  if (results.some((result) => !result || result.status !== "ready")) {
    return { kind: "error", error: new Error("binary payload returned without data") };
  }
  try {
    return {
      kind: "ready",
      value: {
        amplitudes: decodeF64LE(binaryData(results[2] ?? null)),
        kU: decodeF64LE(binaryData(results[0] ?? null)),
        kV: decodeF64LE(binaryData(results[1] ?? null)),
        power: decodeF64LE(binaryData(results[3] ?? null)),
      },
    };
  } catch (error) {
    return {
      kind: "error",
      error: error instanceof Error ? error : new Error("binary payload decoding failed"),
    };
  }
}

function formatPayloadError(error: Error): string {
  if (error instanceof ControlRoomApiError) {
    if (error.code === "missing_payload") {
      return "published spectrum manifest references a missing binary payload";
    }
    if (error.code === "unsupported_topology") {
      return "spectrum payload is unsupported for the resolved topology";
    }
  }
  return error.message;
}

function binaryData(result: BinaryResourceResult<ArrayBuffer> | null): ArrayBuffer {
  if (!result || result.status !== "ready") {
    throw new Error("binary payload returned without data");
  }
  return result.data;
}

function decodeF64LE(buffer: ArrayBuffer | undefined): number[] {
  if (!buffer || buffer.byteLength % 8 !== 0) {
    throw new Error("float64_le payload has a non-integral value count");
  }
  const view = new DataView(buffer);
  const values = new Array<number>(buffer.byteLength / 8);
  for (let index = 0; index < values.length; index += 1) {
    values[index] = view.getFloat64(index * 8, true);
  }
  return values;
}

function sameAxis(a: readonly number[], b: readonly number[]): boolean {
  return a.length === b.length && a.every((value, index) => Object.is(value, b[index]));
}

function validatePayloads(
  payloads: DecodedPayloads,
  spectrum: AntennaSourceSpectrumResource,
  expectedKGrid?: AntennaSpectrumKGrid,
): string | null {
  if (expectedKGrid && (!sameAxis(payloads.kU, expectedKGrid.k_u_rad_per_m) || !sameAxis(payloads.kV, expectedKGrid.k_v_rad_per_m))) {
    return "nonuniform k-grid payload differs from the authored axes";
  }
  if (payloads.kU.length !== spectrum.k_u_count) {
    return `k_u count ${payloads.kU.length} ≠ manifest ${spectrum.k_u_count}`;
  }
  if (payloads.kV.length !== spectrum.k_v_count) {
    return `k_v count ${payloads.kV.length} ≠ manifest ${spectrum.k_v_count}`;
  }
  if (payloads.power.length !== spectrum.power_count) {
    return `power count ${payloads.power.length} ≠ manifest ${spectrum.power_count}`;
  }
  if (payloads.amplitudes.length !== spectrum.amplitude_count * 2) {
    return `amplitude scalar count ${payloads.amplitudes.length} ≠ manifest ${spectrum.amplitude_count * 2}`;
  }
  if (payloads.power.length !== payloads.kU.length * payloads.kV.length) {
    return "power payload does not match the declared k-grid";
  }
  if (payloads.amplitudes.length !==
      2 * spectrum.component_labels.length * payloads.power.length) {
    return "complex amplitudes do not match the component and k-grid counts";
  }
  if (payloads.kU.some((value) => !Number.isFinite(value)) ||
      payloads.kV.some((value) => !Number.isFinite(value))) {
    return "wave-vector payload contains a non-finite value";
  }
  if (payloads.amplitudes.some((value) => !Number.isFinite(value))) {
    return "amplitude payload contains a non-finite value";
  }
  if (payloads.power.some((value) => !Number.isFinite(value) || value < 0)) {
    return "power payload contains a non-finite or negative value";
  }
  for (let cell = 0; cell < payloads.power.length; cell += 1) {
    let expectedPower = 0;
    for (let component = 0; component < spectrum.component_labels.length; component += 1) {
      const offset = 2 * (component * payloads.power.length + cell);
      const re = payloads.amplitudes[offset];
      const im = payloads.amplitudes[offset + 1];
      expectedPower += re * re + im * im;
    }
    const actualPower = payloads.power[cell];
    if (!Number.isFinite(expectedPower) ||
        Math.abs(expectedPower - actualPower) >
          1e-10 * Math.max(expectedPower, actualPower, 1e-300)) {
      return `power payload disagrees with complex amplitudes at k-grid cell ${cell}`;
    }
  }
  return null;
}

function heatmapCells(kU: readonly number[], kV: readonly number[], power: readonly number[]): HeatmapCell[] {
  const uBins = Math.min(MAX_AXIS_CELLS, kU.length);
  const vBins = Math.min(MAX_AXIS_CELLS, kV.length);
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  for (const value of power) {
    if (!Number.isFinite(value)) continue;
    if (value < min) min = value;
    if (value > max) max = value;
  }
  const range = max > min ? max - min : 1;
  const cells: HeatmapCell[] = [];
  for (let vBin = 0; vBin < vBins; vBin += 1) {
    const vStart = Math.floor(vBin * kV.length / vBins);
    const vEnd = Math.floor((vBin + 1) * kV.length / vBins);
    for (let uBin = 0; uBin < uBins; uBin += 1) {
      const uStart = Math.floor(uBin * kU.length / uBins);
      const uEnd = Math.floor((uBin + 1) * kU.length / uBins);
      let selectedU = uStart;
      let selectedV = vStart;
      let selectedPower = Number.NEGATIVE_INFINITY;
      for (let v = vStart; v < vEnd; v += 1) {
        for (let u = uStart; u < uEnd; u += 1) {
          const value = power[v * kU.length + u] ?? Number.NaN;
          if (Number.isFinite(value) && value > selectedPower) {
            selectedPower = value;
            selectedU = u;
            selectedV = v;
          }
        }
      }
      cells.push({
        kUIndex: selectedU,
        kVIndex: selectedV,
        normalizedPower: Number.isFinite(selectedPower)
          ? Math.max(0, Math.min(1, (selectedPower - min) / range)) : 0,
        power: selectedPower,
      });
    }
  }
  return cells;
}

function formatScientific(value: number | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toExponential(3) : "—";
}
