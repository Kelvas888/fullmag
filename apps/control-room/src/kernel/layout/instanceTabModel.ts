import type { DiscoveredInstance } from "../api/apiTypes";

export type SessionTone = "running" | "failed" | "idle";

/** The dot colour of a session lifecycle word; the word itself stays in the title. */
export function sessionTone(status: string | undefined): SessionTone {
  switch (status) {
    case "running":
    case "activating":
    case "materializing_script":
    case "waiting_for_compute":
      return "running";
    case "failed":
      return "failed";
    default:
      return "idle";
  }
}

export function instanceTabLabel(instance: DiscoveredInstance | undefined): string {
  const session = instance?.sessions.find((entry) => entry.current) ?? instance?.sessions[0];
  return session?.name || (instance ? "No session" : "Unavailable");
}
