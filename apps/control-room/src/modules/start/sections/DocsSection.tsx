"use client";

import { ExternalLink, Search } from "lucide-react";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type FormEvent } from "react";

import { useTheme } from "@/design/theme/ThemeProvider";
import { Button } from "@/shared/ui/Button";

import {
  ONLINE_DOCS_URL,
  docsPageUrl,
  docsSearchUrl,
  onlineDocsUrl,
  parseDocsMessage,
  probeDocs,
  resolveFramedDocPath,
  themeMessage,
  type DocsAvailability,
  type DocsTheme,
} from "../model/docs";
import { startScreenStore } from "../model/startScreenState";

const EMBED_FALLBACK_STYLE_ID = "fullmag-embed-fallback-style";
const EMBED_FALLBACK_CSS = `
:root,
html[data-theme="light"] {
  color-scheme: light;
  --fm-docs-bg-app: #eff1f5;
  --fm-docs-bg-chrome: #e6e9ef;
  --fm-docs-bg-surface: #f7f8fb;
  --fm-docs-bg-elevated: #e6e9ef;
  --fm-docs-bg-hover: #dce0e8;
  --fm-docs-border-subtle: #ccd0da;
  --fm-docs-border-default: #bcc0cc;
  --fm-docs-text-primary: #4c4f69;
  --fm-docs-text-secondary: #525570;
  --fm-docs-text-muted: #585c71;
  --fm-docs-accent: #1e66f5;
  --fm-docs-accent-text: #044ee0;
  --fm-docs-accent-soft: #d3e5fd;
  --fm-docs-success: #40a02b;
  --fm-docs-success-text: #256b15;
  --fm-docs-info: #04a5e5;
  --fm-docs-info-text: #09676c;
  --fm-docs-warning: #df8e1d;
  --fm-docs-warning-text: #865006;
  --fm-docs-danger: #d20f39;
  --fm-docs-danger-text: #ba092f;
  --fm-docs-mauve-text: #771af0;
  --fm-docs-peach: #fe640b;
  --fm-docs-degraded-text: #a13b00;
  --root-bg: var(--fm-docs-bg-app);
  --color-base-100: var(--fm-docs-bg-app);
  --color-base-200: var(--fm-docs-border-subtle);
  --color-base-300: var(--fm-docs-border-default);
  --color-base-content: var(--fm-docs-text-primary);
  --color-primary: var(--fm-docs-bg-elevated);
  --color-primary-content: var(--fm-docs-text-primary);
  --color-secondary: var(--fm-docs-bg-surface);
  --color-secondary-content: var(--fm-docs-text-secondary);
  --color-accent: var(--fm-docs-accent-soft);
  --color-accent-content: var(--fm-docs-accent-text);
  --color-neutral: var(--fm-docs-text-primary);
  --color-neutral-content: var(--fm-docs-bg-app);
  --color-info: var(--fm-docs-info);
  --color-info-content: var(--fm-docs-info-text);
  --color-success: var(--fm-docs-success);
  --color-success-content: var(--fm-docs-success-text);
  --color-warning: var(--fm-docs-warning);
  --color-warning-content: var(--fm-docs-warning-text);
  --color-error: var(--fm-docs-danger);
  --color-error-content: var(--fm-docs-danger-text);
  --article-heading--color: var(--fm-docs-text-primary);
  --article-text--color: var(--fm-docs-text-secondary);
  --article-mono--color: var(--fm-docs-mauve-text);
}

html[data-theme="dark"] {
  color-scheme: dark;
  --fm-docs-bg-app: #1e1e2e;
  --fm-docs-bg-chrome: #181825;
  --fm-docs-bg-surface: #242438;
  --fm-docs-bg-elevated: #313244;
  --fm-docs-bg-hover: #3b3c4f;
  --fm-docs-border-subtle: #313244;
  --fm-docs-border-default: #45475a;
  --fm-docs-text-primary: #cdd6f4;
  --fm-docs-text-secondary: #bac2de;
  --fm-docs-text-muted: #a6adc8;
  --fm-docs-accent: #89b4fa;
  --fm-docs-accent-text: #89b4fa;
  --fm-docs-accent-soft: #2a2d52;
  --fm-docs-success: #a6e3a1;
  --fm-docs-success-text: #a6e3a1;
  --fm-docs-info: #89dceb;
  --fm-docs-info-text: #89dceb;
  --fm-docs-warning: #f9e2af;
  --fm-docs-warning-text: #f9e2af;
  --fm-docs-danger: #f38ba8;
  --fm-docs-danger-text: #f592ad;
  --fm-docs-mauve-text: #cba6f7;
  --fm-docs-peach: #fab387;
  --fm-docs-degraded-text: #fab387;
  --root-bg: var(--fm-docs-bg-app);
  --color-base-100: var(--fm-docs-bg-app);
  --color-base-200: var(--fm-docs-border-subtle);
  --color-base-300: var(--fm-docs-border-default);
  --color-base-content: var(--fm-docs-text-primary);
  --color-primary: var(--fm-docs-bg-elevated);
  --color-primary-content: var(--fm-docs-text-primary);
  --color-secondary: var(--fm-docs-bg-surface);
  --color-secondary-content: var(--fm-docs-text-secondary);
  --color-accent: var(--fm-docs-accent-soft);
  --color-accent-content: var(--fm-docs-accent-text);
  --color-neutral: var(--fm-docs-text-primary);
  --color-neutral-content: var(--fm-docs-bg-app);
  --color-info: var(--fm-docs-info);
  --color-info-content: var(--fm-docs-info-text);
  --color-success: var(--fm-docs-success);
  --color-success-content: var(--fm-docs-success-text);
  --color-warning: var(--fm-docs-warning);
  --color-warning-content: var(--fm-docs-warning-text);
  --color-error: var(--fm-docs-danger);
  --color-error-content: var(--fm-docs-danger-text);
  --article-heading--color: var(--fm-docs-text-primary);
  --article-text--color: var(--fm-docs-text-secondary);
  --article-mono--color: var(--fm-docs-mauve-text);
}

html,
body,
.bg-base-100 {
  background-color: var(--fm-docs-bg-app) !important;
  color: var(--fm-docs-text-primary);
}

html[data-fullmag-embedded] .fm-header-build-stamp,
html[data-fullmag-embedded] .mode-select,
html[data-fullmag-embedded] #announcement,
html[data-fullmag-embedded] .announcement {
  display: none !important;
}

html[data-fullmag-embedded] #main-header {
  background-color: var(--fm-docs-bg-app) !important;
  border-bottom: 1px solid var(--fm-docs-border-subtle);
}

article > main div.highlight,
article > main pre {
  background-color: var(--fm-docs-bg-surface) !important;
  border-color: var(--fm-docs-border-subtle);
  color: var(--fm-docs-text-primary);
}

.highlighted {
  background-color: color-mix(in srgb, var(--fm-docs-warning) 22%, transparent);
  border-color: color-mix(in srgb, var(--fm-docs-warning) 55%, transparent);
  color: var(--fm-docs-text-primary);
}
`;

function syncSameOriginDocsDocument(
  frame: HTMLIFrameElement | null,
  theme: DocsTheme,
): string | null {
  if (!frame) return null;
  try {
    const doc = frame.contentDocument;
    const win = frame.contentWindow;
    if (!doc || !win || !doc.documentElement) return null;

    const root = doc.documentElement;
    root.dataset.fullmagEmbedded = "";
    root.dataset.theme = theme;
    root.style.colorScheme = theme;

    const pygmentsDark = doc.getElementById("pygments_dark_css") as HTMLLinkElement | null;
    if (pygmentsDark) {
      pygmentsDark.removeAttribute("media");
      pygmentsDark.disabled = theme !== "dark";
    }

    if (doc.head && !doc.getElementById(EMBED_FALLBACK_STYLE_ID)) {
      const style = doc.createElement("style");
      style.id = EMBED_FALLBACK_STYLE_ID;
      style.textContent = EMBED_FALLBACK_CSS;
      doc.head.appendChild(style);
    }

    doc.querySelectorAll<HTMLAnchorElement>("a[href]").forEach((anchor) => {
      const rawHref = anchor.getAttribute("href");
      if (
        !rawHref ||
        rawHref.startsWith("#") ||
        rawHref.startsWith("mailto:") ||
        rawHref.startsWith("tel:") ||
        rawHref.startsWith("javascript:")
      ) {
        return;
      }
      try {
        const resolvedUrl = new URL(rawHref, win.location.href);
        if (
          (resolvedUrl.protocol === "http:" || resolvedUrl.protocol === "https:") &&
          resolvedUrl.origin !== win.location.origin
        ) {
          anchor.setAttribute("target", "_blank");
          anchor.setAttribute("rel", "noopener noreferrer");
        }
      } catch {
        // Ignore malformed relative hrefs.
      }
    });

    if (win.location.pathname && win.location.pathname !== "about:blank") {
      return resolveFramedDocPath(win.location.pathname, win.location.search);
    }
  } catch {
    // Ignore cross-origin or uninitialized frame errors.
  }
  return null;
}

/**
 * The documentation inside the app. The query box drives Sphinx's own search
 * page in the frame, so results, stemming and highlighting are the docs' own and
 * work offline.
 */
export function DocsSection() {
  const [availability, setAvailability] = useState<DocsAvailability>("checking");
  const [query, setQuery] = useState("");
  // A page requested before this section mounted (Help → Reference) is the
  // starting page; one requested while it is open replaces the current page.
  const { docsRequest } = useSyncExternalStore(
    startScreenStore.subscribe,
    startScreenStore.getSnapshot,
    startScreenStore.getServerSnapshot,
  );
  const [src, setSrc] = useState(() => docsPageUrl(docsRequest?.page));
  const handledRequest = useRef(docsRequest?.seq ?? 0);
  // Reading moves the frame without touching `src`, so a request for the page the
  // state already names must still bring the frame back; a new key reloads it.
  const [frameKey, setFrameKey] = useState(0);
  const [pagePath, setPagePath] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);
  const { theme } = useTheme();

  // The framed site is same-origin; address it explicitly rather than with "*".
  const sendTheme = useCallback(() => {
    const resolvedPath = syncSameOriginDocsDocument(frameRef.current, theme);
    if (resolvedPath) {
      setPagePath(resolvedPath);
    }
    frameRef.current?.contentWindow?.postMessage(themeMessage(theme), window.location.origin);
  }, [theme]);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      // Only the frame this component owns, on this origin, is listened to.
      if (event.origin !== window.location.origin) return;
      if (event.source !== frameRef.current?.contentWindow) return;
      const message = parseDocsMessage(event.data);
      if (!message) return;
      if (message.type === "ready") sendTheme();
      else setPagePath(message.path);
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [sendTheme]);

  // A theme change after the page is up reaches it without a reload.
  useEffect(() => {
    sendTheme();
  }, [sendTheme]);

  useEffect(() => {
    let cancelled = false;
    void probeDocs().then((result) => {
      if (!cancelled) setAvailability(result);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!docsRequest || docsRequest.seq === handledRequest.current) return;
    handledRequest.current = docsRequest.seq;
    setSrc(docsPageUrl(docsRequest.page));
    setFrameKey((key) => key + 1);
  }, [docsRequest]);

  useEffect(() => {
    if (availability === "available") inputRef.current?.focus();
  }, [availability]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSrc(docsSearchUrl(query));
    setFrameKey((key) => key + 1);
  };

  return (
    <div className="fm-start-docs">
      <div className="fm-start-docs__bar">
        <form className="fm-start-search" onSubmit={submit} role="search">
          <Search aria-hidden="true" size={14} />
          <input
            aria-label="Search the documentation"
            disabled={availability !== "available"}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search the documentation"
            ref={inputRef}
            type="search"
            value={query}
          />
        </form>
        <Button
          disabled={availability !== "available"}
          onClick={() => {
            setQuery("");
            setSrc(docsPageUrl());
            setFrameKey((key) => key + 1);
          }}
          size="sm"
          type="button"
          variant="secondary"
        >
          Contents
        </Button>
        <a
          className="fm-start-link fm-start-docs__online"
          href={pagePath ? onlineDocsUrl(pagePath) : ONLINE_DOCS_URL}
          rel="noreferrer"
          target="_blank"
        >
          Open online <ExternalLink aria-hidden="true" size={12} />
        </a>
      </div>

      {availability === "available" ? (
        <iframe
          className="fm-start-docs__frame"
          key={frameKey}
          onLoad={sendTheme}
          ref={frameRef}
          referrerPolicy="no-referrer"
          src={src}
          title="Fullmag documentation"
        />
      ) : availability === "checking" ? (
        <p className="fm-start-inspector__note" role="status">
          Opening the documentation…
        </p>
      ) : (
        <div className="fm-start-notice fm-start-notice--warning" role="status">
          The documentation is not bundled with this build. It is available online at{" "}
          <a className="fm-start-link" href={ONLINE_DOCS_URL} rel="noreferrer" target="_blank">
            {ONLINE_DOCS_URL}
          </a>
          . To bundle it for offline use, build the Sphinx site and run{" "}
          <code>pnpm --dir apps/control-room docs:bundle</code>.
        </div>
      )}
    </div>
  );
}
