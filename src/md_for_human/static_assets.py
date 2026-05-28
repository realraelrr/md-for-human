from __future__ import annotations

from pygments.formatters import HtmlFormatter


PYGMENTS_CSS = HtmlFormatter(style="native", cssclass="highlight").get_style_defs(  # type: ignore[no-untyped-call]
    ".article .highlight"
)

BASE_CSS = f"""
:root {{
  color-scheme: dark;
  --bg: #0f1720;
  --panel: #17212d;
  --panel-strong: #223142;
  --text: #eef4fb;
  --muted: #95a8bc;
  --accent: #7dd3fc;
  --accent-strong: #38bdf8;
  --border: rgba(148, 163, 184, 0.22);
  --code-bg: #0b1220;
  --code-border: rgba(125, 211, 252, 0.22);
  --code-text: #e5eef9;
  --table-head: rgba(34, 49, 66, 0.92);
  --shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
  --sidebar-item-hover-bg: rgba(56, 189, 248, 0.08);
  --sidebar-item-active-bg: rgba(56, 189, 248, 0.18);
  --sidebar-item-active-border: rgba(56, 189, 248, 0.52);
  --sidebar-item-active-text: var(--accent);
  --sidebar-item-inactive-text: var(--muted);
}}

* {{
  box-sizing: border-box;
}}

html, body {{
  margin: 0;
  min-height: 100%;
  background:
    radial-gradient(circle at top left, rgba(56, 189, 248, 0.18), transparent 28rem),
    linear-gradient(180deg, #0b1118 0%, var(--bg) 100%);
  color: var(--text);
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", serif;
}}

body {{
  line-height: 1.6;
}}

a {{
  color: var(--accent);
}}

.layout {{
  --sidebar-width: clamp(17rem, 24vw, 22rem);
  position: relative;
  min-height: 100vh;
  padding-left: var(--sidebar-width);
  transition: padding-left 300ms ease;
}}

.layout.is-sidebar-collapsed {{
  padding-left: 0;
}}

.sidebar {{
  position: fixed;
  inset: 0 auto 0 0;
  width: var(--sidebar-width);
  height: 100vh;
  padding: 1.5rem 1rem 2rem;
  overflow-x: hidden;
  overflow-y: auto;
  border-right: 1px solid var(--border);
  background: rgba(15, 23, 32, 0.84);
  backdrop-filter: blur(16px);
  transform: translateX(0);
  transition: transform 300ms ease;
  z-index: 20;
}}

.layout.is-sidebar-collapsed .sidebar {{
  transform: translateX(calc(-1 * var(--sidebar-width)));
}}

.sidebar-header {{
  display: flex;
  align-items: center;
  gap: 0.8rem;
  margin-bottom: 1.25rem;
}}

.sidebar-badge {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.1rem;
  height: 2.1rem;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(34, 49, 66, 0.7);
  color: var(--accent);
  font-family: "Avenir Next", "Helvetica Neue", sans-serif;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}}

.sidebar-header h1,
.sidebar-section h2 {{
  margin: 0;
  font-size: 0.92rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-family: "Avenir Next", "Helvetica Neue", sans-serif;
}}

.sidebar-scroll {{
  display: grid;
  min-width: 0;
  max-width: 100%;
  gap: 1rem;
  transition: opacity 140ms ease, transform 140ms ease;
}}

.sidebar-section {{
  min-width: 0;
  max-width: 100%;
  padding: 1rem;
  border: 1px solid var(--border);
  border-radius: 1rem;
  background: rgba(23, 33, 45, 0.62);
}}

.sidebar-section-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.8rem;
  margin-bottom: 0.8rem;
}}

.sidebar-section-content[hidden] {{
  display: none;
}}

.sidebar-action,
.sidebar-edge-toggle,
.page-toolbar-toggle {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text);
  border-radius: 999px;
  padding: 0.45rem 0.85rem;
  cursor: pointer;
  font: inherit;
}}

.sidebar-edge-toggle {{
  position: absolute;
  top: 1.5rem;
  right: 1rem;
  width: 2rem;
  height: 2rem;
  min-width: 0;
  padding: 0;
  font-family: "Avenir Next", "Helvetica Neue", sans-serif;
  font-size: 1.45rem;
  line-height: 1;
  z-index: 2;
  box-shadow: var(--shadow);
}}

.page-toolbar-toggle {{
  position: fixed;
  top: 1rem;
  left: 1rem;
  display: none;
  z-index: 30;
  box-shadow: var(--shadow);
}}

.layout.is-sidebar-collapsed .page-toolbar-toggle {{
  display: inline-flex;
}}

.layout.is-sidebar-collapsed .sidebar-edge-toggle {{
  display: none;
}}

.layout.is-sidebar-collapsed .sidebar-header h1,
.layout.is-sidebar-collapsed .sidebar-scroll {{
  opacity: 0;
  pointer-events: none;
  transform: translateX(-0.35rem);
}}

.layout.is-sidebar-collapsed .sidebar-scroll {{
  overflow: hidden;
}}

.nav-tree,
.nav-children {{
  list-style: none;
  margin: 0;
  padding: 0;
}}

.nav-item + .nav-item,
.nav-branch + .nav-item,
.nav-branch + .nav-branch {{
  margin-top: 0.4rem;
}}

.nav-link,
.nav-summary {{
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.45rem 0.6rem;
  border-radius: 0.65rem;
  color: inherit;
  text-decoration: none;
}}

.nav-link:hover,
.nav-summary:hover,
.page-toc a:hover {{
  background: var(--sidebar-item-hover-bg);
}}

.nav-link,
.nav-summary,
.page-toc a {{
  transition:
    background-color 180ms ease,
    border-color 180ms ease,
    color 180ms ease;
}}

.nav-summary {{
  cursor: pointer;
  color: var(--text);
  font-size: 0.95rem;
  font-weight: 600;
  list-style: none;
}}

.nav-summary::-webkit-details-marker {{
  display: none;
}}

.nav-summary::after {{
  content: ">";
  margin-left: auto;
  color: var(--muted);
  transition: transform 180ms ease, color 180ms ease;
}}

.nav-branch[open] > .nav-summary::after {{
  transform: rotate(90deg);
  color: var(--accent);
}}

.nav-kind {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 2.2rem;
  padding: 0.12rem 0.38rem;
  border-radius: 999px;
  border: 1px solid var(--border);
  font-family: "Avenir Next", "Helvetica Neue", sans-serif;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  line-height: 1.2;
  text-transform: uppercase;
}}

.nav-kind-folder {{
  background: rgba(251, 191, 36, 0.15);
  color: #fde68a;
}}

.nav-kind-file {{
  background: rgba(56, 189, 248, 0.16);
  color: var(--accent);
}}

.nav-label {{
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}

.nav-children {{
  margin-left: 1.1rem;
  padding-left: 0.85rem;
  border-left: 1px solid var(--border);
}}

.main {{
  padding: 2rem clamp(1.25rem, 3vw, 3rem) 4rem;
}}

.main-inner {{
  margin: 0 auto;
  max-width: 60rem;
}}

.page-toolbar {{
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}}

.page-meta {{
  margin: 0;
  color: var(--muted);
  font-family: "Avenir Next", "Helvetica Neue", sans-serif;
  font-size: 0.95rem;
}}

.page-toc {{
  margin: 0;
}}

.page-toc ul {{
  list-style: none;
  margin: 0;
  padding-left: 0;
}}

.page-toc li + li {{
  margin-top: 0.25rem;
}}

.page-toc li {{
  --toc-indent: 0.55rem;
}}

.page-toc .toc-level-1 {{
  --toc-indent: 0.55rem;
}}

.page-toc .toc-level-2 {{
  --toc-indent: 1.25rem;
}}

.page-toc .toc-level-3 {{
  --toc-indent: 2rem;
}}

.page-toc .toc-level-4,
.page-toc .toc-level-5,
.page-toc .toc-level-6 {{
  --toc-indent: 2.75rem;
}}

.page-toc a {{
  display: block;
  max-width: 100%;
  overflow: hidden;
  padding: 0.35rem 0.55rem 0.35rem var(--toc-indent);
  border-left: 2px solid transparent;
  border-radius: 0.55rem;
  color: var(--text);
  text-decoration: none;
  text-overflow: ellipsis;
  white-space: nowrap;
}}

.nav-link[aria-current="page"],
.page-toc a.is-toc-highlighted,
.page-toc a.is-active {{
  background: var(--sidebar-item-active-bg);
  border-color: var(--sidebar-item-active-border);
  color: var(--sidebar-item-active-text);
}}

.page-toc.is-scroll-spy-active a {{
  color: var(--sidebar-item-inactive-text);
}}

.page-toc.is-scroll-spy-active a.is-active {{
  color: var(--sidebar-item-active-text);
}}

.article .is-heading-highlighted {{
  animation: heading-highlight 2s ease-out;
  border-radius: 0.35rem;
}}

@keyframes heading-highlight {{
  0% {{
    background: rgba(125, 211, 252, 0.35);
    box-shadow: 0 0 0 0.35rem rgba(125, 211, 252, 0.18);
  }}
  100% {{
    background: transparent;
    box-shadow: 0 0 0 0 rgba(125, 211, 252, 0);
  }}
}}

.article {{
  position: relative;
  padding: clamp(1.25rem, 2vw, 2rem);
  border: 1px solid var(--border);
  border-radius: 1.5rem;
  background: rgba(23, 33, 45, 0.86);
  box-shadow: var(--shadow);
}}

.article-close {{
  position: absolute;
  top: 0.85rem;
  right: 0.85rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel);
  color: var(--text);
  font-family: "Avenir Next", "Helvetica Neue", sans-serif;
  font-size: 1.25rem;
  line-height: 1;
  text-decoration: none;
}}

.article-close:hover {{
  background: var(--sidebar-item-hover-bg);
  color: var(--accent);
}}

.article-content {{
  min-width: 0;
}}

.article img {{
  max-width: 100%;
}}

.article pre,
.article code {{
  font-family: "JetBrains Mono", "SFMono-Regular", monospace;
}}

.article code {{
  font-size: 0.95em;
}}

.article :not(pre) > code,
.article li code,
.article td code,
.article th code,
.article p code {{
  padding: 0.14rem 0.36rem;
  border-radius: 0.35rem;
  background: rgba(34, 49, 66, 0.8);
}}

.article .highlight {{
  margin: 1.25rem 0;
  overflow-x: auto;
  max-width: 100%;
  border: 1px solid var(--code-border);
  border-radius: 1rem;
  background: var(--code-bg);
  color: var(--code-text);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}}

.article .highlight pre {{
  margin: 0;
  min-width: max-content;
  padding: 1rem 1.1rem;
  background: transparent;
  color: var(--code-text);
}}

.article table {{
  width: 100%;
  margin: 1.5rem 0;
  border-collapse: collapse;
  border-spacing: 0;
}}

.article ul,
.article ol {{
  padding-left: 1.35rem;
}}

.article li::marker {{
  color: var(--accent-strong);
}}

.article th,
.article td {{
  padding: 0.75rem 0.9rem;
  text-align: left;
  vertical-align: top;
  border: 1px solid var(--border);
}}

.article th {{
  background: var(--table-head);
}}

.article tr:nth-child(even) td {{
  background: rgba(255, 255, 255, 0.02);
}}

.page-pager {{
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 1.5rem;
}}

.page-pager a {{
  flex: 1 1 0;
  padding: 0.9rem 1rem;
  border: 1px solid var(--border);
  border-radius: 1rem;
  background: rgba(23, 33, 45, 0.72);
  text-decoration: none;
}}

.page-pager a:last-child {{
  text-align: right;
}}

@media (max-width: 960px) {{
  .layout,
  .layout.is-sidebar-collapsed {{
    padding-left: 0;
  }}

  .sidebar {{
    width: min(85vw, 20rem);
    transform: translateX(-105%);
  }}

  .layout.is-sidebar-collapsed .sidebar {{
    transform: translateX(-105%);
  }}

  .sidebar.is-open,
  .layout.is-sidebar-collapsed .sidebar.is-open {{
    transform: translateX(0);
  }}

  .sidebar-edge-toggle {{
    display: none;
  }}

  .page-toolbar-toggle,
  .layout.is-sidebar-collapsed .page-toolbar-toggle {{
    position: static;
    display: inline-flex;
    box-shadow: none;
  }}

  .sidebar-header h1,
  .sidebar-scroll,
  .layout.is-sidebar-collapsed .sidebar-header h1,
  .layout.is-sidebar-collapsed .sidebar-scroll {{
    opacity: 1;
    pointer-events: auto;
    transform: none;
  }}
}}

@media (prefers-color-scheme: light) {{
  :root {{
    color-scheme: light;
    --bg: #eef4f8;
    --panel: #ffffff;
    --panel-strong: #dce7ef;
    --text: #0f1720;
    --muted: #4b5f73;
    --accent: #0f6ea7;
    --accent-strong: #0c4a6e;
    --border: rgba(15, 23, 32, 0.12);
    --code-bg: #f3f7fb;
    --code-border: rgba(15, 110, 167, 0.16);
    --code-text: #102033;
    --table-head: rgba(220, 231, 239, 0.9);
    --shadow: 0 20px 60px rgba(15, 23, 32, 0.1);
    --sidebar-item-hover-bg: rgba(15, 110, 167, 0.08);
    --sidebar-item-active-bg: rgba(15, 110, 167, 0.12);
    --sidebar-item-active-border: rgba(15, 110, 167, 0.42);
  }}

  html, body {{
    background:
      radial-gradient(circle at top left, rgba(14, 116, 144, 0.12), transparent 28rem),
      linear-gradient(180deg, #f8fbfd 0%, var(--bg) 100%);
  }}

  .sidebar,
  .article,
  .page-pager a {{
    background: rgba(255, 255, 255, 0.88);
  }}

.sidebar-section {{
    background: rgba(255, 255, 255, 0.7);
  }}

  .nav-kind-folder {{
    color: #92400e;
  }}

  .article tr:nth-child(even) td {{
    background: rgba(15, 23, 32, 0.03);
  }}
}}

{PYGMENTS_CSS}
""".strip()

BASE_JS = """
document.addEventListener("DOMContentLoaded", () => {
  const layout = document.querySelector("[data-layout]");
  const sidebar = document.querySelector("[data-sidebar]");
  const toggles = Array.from(document.querySelectorAll("[data-sidebar-toggle]"));
  const tocToggle = document.querySelector("[data-toc-toggle]");
  const tocContent = document.querySelector("[data-toc-content]");
  const siteNavToggle = document.querySelector("[data-site-nav-toggle]");
  const siteNavContent = document.querySelector("[data-site-nav-content]");
  const isMobileViewport = () => window.matchMedia("(max-width: 960px)").matches;

  const syncSidebarState = (expanded) => {
    toggles.forEach((toggle) => {
      const isToolbarToggle = toggle.classList.contains("page-toolbar-toggle");
      const isEdgeToggle = toggle.hasAttribute("data-sidebar-edge-toggle");
      const label = isMobileViewport()
        ? (expanded ? "Close" : "Menu")
        : (isToolbarToggle && !expanded ? "Expand sidebar" : expanded ? "Collapse sidebar" : "Expand sidebar");

      toggle.setAttribute("aria-expanded", String(expanded));
      toggle.setAttribute("aria-label", label);

      if (isEdgeToggle && !isMobileViewport()) {
        toggle.textContent = expanded ? "‹" : ">";
        toggle.title = label;
        return;
      }

      if (isToolbarToggle && !isMobileViewport()) {
        toggle.textContent = expanded ? "Menu" : ">";
        toggle.title = label;
        return;
      }

      toggle.textContent = isToolbarToggle ? "Menu" : label;
    });
  };

  if (sidebar) {
    sidebar.querySelectorAll(".is-active-branch").forEach((branch) => {
      if (branch.tagName === "DETAILS") {
        branch.open = true;
      }
    });
  }

  if (layout && sidebar && toggles.length > 0) {
    const initialExpanded = isMobileViewport()
      ? sidebar.classList.contains("is-open")
      : !layout.classList.contains("is-sidebar-collapsed");
    syncSidebarState(initialExpanded);
    toggles.forEach((toggle) => {
      toggle.addEventListener("click", () => {
        if (isMobileViewport()) {
          const isOpen = sidebar.classList.toggle("is-open");
          syncSidebarState(isOpen);
          return;
        }
        const isCollapsed = layout.classList.toggle("is-sidebar-collapsed");
        syncSidebarState(!isCollapsed);
      });
    });
    window.addEventListener("resize", () => {
      if (!isMobileViewport()) {
        sidebar.classList.remove("is-open");
      }
      const expanded = isMobileViewport()
        ? sidebar.classList.contains("is-open")
        : !layout.classList.contains("is-sidebar-collapsed");
      syncSidebarState(expanded);
    });
  }

  if (siteNavToggle && siteNavContent) {
    const syncSiteNavState = (expanded) => {
      siteNavToggle.setAttribute("aria-expanded", String(expanded));
      siteNavToggle.textContent = expanded ? "Hide" : "Show";
      siteNavContent.hidden = !expanded;
    };

    syncSiteNavState(true);
    siteNavToggle.addEventListener("click", () => {
      syncSiteNavState(siteNavContent.hidden);
    });
  }

  if (tocToggle && tocContent) {
    const syncTocState = (expanded) => {
      tocToggle.setAttribute("aria-expanded", String(expanded));
      tocToggle.textContent = expanded ? "Hide" : "Show";
      tocContent.hidden = !expanded;
    };

    syncTocState(true);
    tocToggle.addEventListener("click", () => {
      syncTocState(tocContent.hidden);
    });
  }

  const tocLinks = Array.from(document.querySelectorAll("[data-toc-content] a[href^='#']"));
  const tocNav = tocContent ? tocContent.querySelector(".page-toc") : null;
  const tocTargets = tocLinks
    .map((link) => {
      const targetId = decodeURIComponent(link.hash.slice(1));
      const target = targetId ? document.getElementById(targetId) : null;
      return target ? { link, target } : null;
    })
    .filter(Boolean);

  const setActiveTocLink = (activeLink) => {
    tocLinks.forEach((link) => {
      link.classList.toggle("is-active", link === activeLink);
    });

    if (tocNav) {
      tocNav.classList.toggle("is-scroll-spy-active", Boolean(activeLink));
    }

    if (activeLink && tocContent) {
      activeLink.scrollIntoView({ block: "nearest" });
    }
  };

  const clearHighlight = (element, className) => {
    if (!element) {
      return;
    }
    element.classList.remove(className);
    void element.offsetWidth;
    element.classList.add(className);
    window.setTimeout(() => {
      element.classList.remove(className);
    }, 2000);
  };

  tocTargets.forEach(({ link, target }) => {
    link.addEventListener("click", () => {
      setActiveTocLink(link);
      clearHighlight(link, "is-toc-highlighted");
      clearHighlight(target, "is-heading-highlighted");
    });
  });

  if (tocTargets.length > 0 && "IntersectionObserver" in window) {
    let isSpyUpdateQueued = false;

    const findCurrentTocTarget = () => {
      const activationOffset = window.innerHeight * 0.28;
      let current = tocTargets[0];

      tocTargets.forEach((entry) => {
        if (entry.target.getBoundingClientRect().top <= activationOffset) {
          current = entry;
        }
      });

      return current;
    };

    const scheduleSpyUpdate = () => {
      if (isSpyUpdateQueued) {
        return;
      }

      isSpyUpdateQueued = true;
      window.requestAnimationFrame(() => {
        isSpyUpdateQueued = false;
        setActiveTocLink(findCurrentTocTarget().link);
      });
    };

    const tocObserver = new IntersectionObserver(scheduleSpyUpdate, {
      rootMargin: "-20% 0px -65% 0px",
      threshold: [0, 1],
    });

    tocTargets.forEach(({ target }) => {
      tocObserver.observe(target);
    });

    scheduleSpyUpdate();
  }
});
""".strip()
