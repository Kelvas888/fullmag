"use client";

import { ExternalLink, House, X } from "lucide-react";

import { Button } from "@/shared/ui/Button";
import { Tabs, TabsList, TabsTrigger } from "@/shared/ui/Tabs";

import type { DiscoveredInstance } from "../api/apiTypes";
import { useInstanceDiscovery } from "../resources/instanceDiscoveryResources";
import { useSessionCollection } from "../resources/useSessionCollection";
import { homeView, useHomeViewOpen } from "./homeView";
import { instanceOrigin, instanceTabs, useInstanceTabs } from "./instanceTabs";

const HOME_TAB = "home";
const SESSION_TAB = "session";
const INSTANCE_TAB_PREFIX = "instance:";

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

/**
 * Home, this instance's session and one tab per other Fullmag instance on the
 * host (ADR 0069). Switching tabs never stops a session: Home and other
 * instances lie over the mounted workspace.
 */
export function InstanceTabStrip() {
  const sessions = useSessionCollection();
  const discovery = useInstanceDiscovery({ poll: true });
  const tabs = useInstanceTabs();
  const homeOpen = useHomeViewOpen();
  const current = sessions.resource.data?.sessions.find((entry) => entry.current) ?? null;
  const instances = new Map(
    (discovery.data?.instances ?? []).map((instance) => [instance.port, instance]),
  );
  const discoveryKnown = discovery.data !== null;

  const value = tabs.activePort !== null
    ? `${INSTANCE_TAB_PREFIX}${tabs.activePort}`
    : current && !homeOpen
      ? SESSION_TAB
      : HOME_TAB;

  const select = (next: string) => {
    if (next === HOME_TAB) {
      instanceTabs.activate(null);
      homeView.open();
    } else if (next === SESSION_TAB) {
      instanceTabs.activate(null);
      homeView.close();
    } else if (next.startsWith(INSTANCE_TAB_PREFIX)) {
      instanceTabs.activate(Number(next.slice(INSTANCE_TAB_PREFIX.length)));
    }
  };

  return (
    <nav aria-label="Sessions" className="fm-instance-tabs" data-instance-tabs="">
      <Tabs onValueChange={select} value={value}>
        <TabsList aria-label="Open sessions" className="fm-instance-tabs__list">
          <TabsTrigger className="fm-instance-tabs__tab" data-tab-kind="home" value={HOME_TAB}>
            <House aria-hidden="true" size={13} />
            Home
          </TabsTrigger>
          {current ? (
            <TabsTrigger
              className="fm-instance-tabs__tab"
              data-tab-kind="session"
              title={`${current.name} — ${current.status}`}
              value={SESSION_TAB}
            >
              <span aria-hidden="true" className="fm-instance-tabs__dot" data-tone={sessionTone(current.status)} />
              <span className="fm-instance-tabs__name">{current.name || "Untitled simulation"}</span>
            </TabsTrigger>
          ) : null}
          {tabs.openPorts.map((port) => {
            const instance = instances.get(port);
            const session = instance?.sessions.find((entry) => entry.current);
            const unavailable = discoveryKnown && !instance;
            const label = instanceTabLabel(instance);
            return (
              <div className="fm-instance-tabs__item" key={port}>
                <TabsTrigger
                  className="fm-instance-tabs__tab"
                  data-instance-port={port}
                  data-tab-kind="instance"
                  data-unavailable={unavailable || undefined}
                  title={`${label} — port ${port}${session ? ` — ${session.status}` : ""}`}
                  value={`${INSTANCE_TAB_PREFIX}${port}`}
                >
                  <span
                    aria-hidden="true"
                    className="fm-instance-tabs__dot"
                    data-tone={unavailable ? "failed" : sessionTone(session?.status)}
                  />
                  <span className="fm-instance-tabs__name">{label}</span>
                  <span className="fm-instance-tabs__port">:{port}</span>
                </TabsTrigger>
                <Button
                  aria-label={`Close tab ${label} (port ${port})`}
                  className="fm-instance-tabs__close"
                  onClick={() => instanceTabs.close(port)}
                  size="icon"
                  type="button"
                  variant="ghost"
                >
                  <X aria-hidden="true" size={12} />
                </Button>
              </div>
            );
          })}
        </TabsList>
      </Tabs>
      {tabs.activePort !== null ? (
        // An instance older than tab support refuses to be framed; it can
        // still be opened on its own. The active port exists only after a
        // client-side activation, so the page location is available here.
        <a
          className="fm-instance-tabs__popout"
          href={`${instanceOrigin(tabs.activePort, window.location)}/workspace`}
          rel="noreferrer"
          target="_blank"
        >
          <ExternalLink aria-hidden="true" size={12} />
          Open in window
        </a>
      ) : null}
    </nav>
  );
}
