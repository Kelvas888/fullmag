"use client";

import { useLayoutEffect, useRef, useState } from "react";

import type { AntennaSourceSpectrumResource } from "@/kernel/api/apiTypes";
import { downloadChartBlob } from "@/shared/analysis-charts/chartExport";
import { Button } from "@/shared/ui/Button";

interface SpectrumExportProps {
  spectrum: AntennaSourceSpectrumResource;
  amplitudes: readonly number[];
  kU: readonly number[];
  kV: readonly number[];
  power: readonly number[];
}

/** Exports validated full-resolution carriers, never the pooled display cells. */
async function spectrumExportBlob(source: SpectrumExportProps, signal: AbortSignal): Promise<Blob> {
  const parts: BlobPart[] = [
    '{"export_schema":"fullmag_source_spectrum_export.v1","manifest":',
    JSON.stringify(source.spectrum),
    ',"data":{',
  ];
  const arrays = [
    ["k_u_rad_per_m", source.kU], ["k_v_rad_per_m", source.kV],
    ["amplitudes_re_im", source.amplitudes], ["power", source.power],
  ] as const;
  for (const [arrayIndex, [name, values]] of arrays.entries()) {
    parts.push(`${arrayIndex ? "," : ""}"${name}":[`);
    for (let offset = 0; offset < values.length; offset += 4096) {
      await new Promise<void>(resolve => setTimeout(resolve, 0));
      signal.throwIfAborted();
      const chunk = JSON.stringify(values.slice(offset, offset + 4096));
      parts.push(new Blob([`${offset ? "," : ""}${chunk.slice(1, -1)}`]));
    }
    parts.push("]");
  }
  signal.throwIfAborted();
  parts.push("}}\n");
  return new Blob(parts, { type: "application/json" });
}

export function AntennaSpectrumExport(props: SpectrumExportProps) {
  const { spectrum, amplitudes, kU, kV, power } = props;
  const job = useRef<AbortController | null>(null);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  useLayoutEffect(() => () => { job.current?.abort(); }, [spectrum, amplitudes, kU, kV, power]);

  const exportData = async () => {
    if (job.current && !job.current.signal.aborted) return;
    const controller = new AbortController();
    job.current = controller;
    setPending(true);
    setFailed(false);
    try {
      const content = await spectrumExportBlob(props, controller.signal);
      controller.signal.throwIfAborted();
      const id = spectrum.output_id.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 80) || "output";
      if (!downloadChartBlob({ content, filename: `antenna-spectrum-${id}.json`, mimeType: "application/json" })) {
        setFailed(true);
      }
    } catch {
      if (!controller.signal.aborted) setFailed(true);
    } finally {
      if (job.current === controller) {
        job.current = null;
        setPending(false);
      }
    }
  };

  return <>
    <Button type="button" size="sm" variant="secondary" disabled={pending} onClick={() => { void exportData(); }}>
      {pending ? "Preparing spectrum…" : "Export full spectrum (JSON)"}
    </Button>
    {failed ? <p role="alert">Spectrum export failed. Try again.</p> : null}
  </>;
}
