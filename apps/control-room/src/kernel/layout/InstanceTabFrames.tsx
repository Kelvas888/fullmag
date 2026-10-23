"use client";

import { Button } from "@/shared/ui/Button";

import { useInstanceDiscovery } from "../resources/instanceDiscoveryResources";
import { instanceOrigin, instanceTabs, useInstanceTabs } from "./instanceTabs";

/**
 * Other instances' own Control Rooms, each in a frame of its own origin, so the
 * UI always matches the version of that instance's API (ADR 0069). A frame is
 * created the first time its tab comes to the front and then stays mounted
 * (hidden by visibility) to keep its view state and WebGL context.
 */
export function InstanceTabFrames() {
  const tabs = useInstanceTabs();
  const discovery = useInstanceDiscovery();
  const activePort = tabs.activePort;
  const framed = tabs.framedPorts.filter((port) => tabs.openPorts.includes(port));
  const known = new Set((discovery.data?.instances ?? []).map((instance) => instance.port));
  const activeUnavailable = activePort !== null && discovery.data !== null && !known.has(activePort);

  return (
    <div
      className="fm-instance-frames"
      data-active-port={activePort ?? undefined}
      data-state={activePort === null ? "hidden" : "visible"}
    >
      {/* Frames exist only after a client-side activation, so reading the
          page location here never runs during server rendering. */}
      {framed.map((port) => (
        <iframe
          allow="fullscreen; clipboard-read; clipboard-write"
          className="fm-instance-frames__frame"
          data-active={port === activePort || undefined}
          data-instance-port={port}
          key={port}
          src={`${instanceOrigin(port, window.location)}/workspace`}
          title={`Fullmag instance on port ${port}`}
        />
      ))}
      {activeUnavailable ? (
        <div className="fm-instance-frames__unavailable" role="status">
          <p>No Fullmag instance answers on port {activePort}.</p>
          <Button onClick={() => instanceTabs.close(activePort)} type="button" variant="secondary">
            Close tab
          </Button>
        </div>
      ) : null}
    </div>
  );
}
