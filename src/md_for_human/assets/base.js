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
