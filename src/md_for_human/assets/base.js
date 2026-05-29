(() => {
  const THEME_STORAGE_KEY = "mdfh-theme";
  const LOCALE_STORAGE_KEY = "mdfh-locale";
  const DEFAULT_LOCALE = "en";
  const SUPPORTED_THEMES = new Set(["light", "dark"]);
  const SUPPORTED_LOCALES = new Set(["en", "zh-CN", "zh-TW"]);
  const MESSAGES = {
    en: {
      contents: "Contents",
      siteNavigation: "Site navigation",
      onThisPage: "On this page",
      hide: "Hide",
      show: "Show",
      menu: "Menu",
      close: "Close",
      collapseSidebar: "Collapse sidebar",
      expandSidebar: "Expand sidebar",
      pageNavigation: "Page navigation",
      previous: "Previous",
      next: "Next",
      language: "Language",
      themeDark: "Dark",
      themeLight: "Light",
      switchToDark: "Switch to dark mode",
      switchToLight: "Switch to light mode",
      source: "Source",
      reviewComments: "Review comments",
      reviewComment: "Comment",
      reviewEdit: "Edit",
      reviewSave: "Save",
      reviewDelete: "Delete",
      reviewCancel: "Cancel",
      reviewDocumentComment: "Document comment",
      reviewPageComments: "Page comments",
      reviewUnplacedHelp: "These comments are saved for this page; the exact underline is not available.",
      reviewPlaceholder: "Write the requested change and why it matters.",
      reviewLoading: "Still loading comments.",
      reviewNeedComment: "Write a comment before saving.",
      reviewSaved: "Saved.",
      reviewDeleted: "Deleted.",
      reviewRequestFailed: "Request failed",
      reviewErrorPrefix: "Error",
      reviewUnderlineUnavailable: "Exact underline is unavailable.",
      reviewUnderlineAmbiguous: "Exact underline is ambiguous.",
      reviewQuoteUnresolved: "Quote location could not be resolved.",
    },
    "zh-CN": {
      contents: "目录",
      siteNavigation: "站点导航",
      onThisPage: "本页内容",
      hide: "隐藏",
      show: "显示",
      menu: "菜单",
      close: "关闭",
      collapseSidebar: "收起导航",
      expandSidebar: "展开导航",
      pageNavigation: "页面导航",
      previous: "上一页",
      next: "下一页",
      language: "语言",
      themeDark: "深色",
      themeLight: "浅色",
      switchToDark: "切换到深色模式",
      switchToLight: "切换到浅色模式",
      source: "原文",
      reviewComments: "审查评论",
      reviewComment: "评论",
      reviewEdit: "编辑",
      reviewSave: "保存",
      reviewDelete: "删除",
      reviewCancel: "取消",
      reviewDocumentComment: "整页评论",
      reviewPageComments: "页面评论",
      reviewUnplacedHelp: "这些评论已保存到本页；精确下划线位置当前不可用。",
      reviewPlaceholder: "写下需要修改的内容，以及为什么重要。",
      reviewLoading: "评论仍在加载。",
      reviewNeedComment: "保存前请先填写评论。",
      reviewSaved: "已保存。",
      reviewDeleted: "已删除。",
      reviewRequestFailed: "请求失败",
      reviewErrorPrefix: "错误",
      reviewUnderlineUnavailable: "无法定位精确下划线。",
      reviewUnderlineAmbiguous: "精确下划线位置不唯一。",
      reviewQuoteUnresolved: "无法解析引用位置。",
    },
    "zh-TW": {
      contents: "目錄",
      siteNavigation: "站點導覽",
      onThisPage: "本頁內容",
      hide: "隱藏",
      show: "顯示",
      menu: "選單",
      close: "關閉",
      collapseSidebar: "收合導覽",
      expandSidebar: "展開導覽",
      pageNavigation: "頁面導覽",
      previous: "上一頁",
      next: "下一頁",
      language: "語言",
      themeDark: "深色",
      themeLight: "淺色",
      switchToDark: "切換到深色模式",
      switchToLight: "切換到淺色模式",
      source: "原文",
      reviewComments: "審查評論",
      reviewComment: "評論",
      reviewEdit: "編輯",
      reviewSave: "儲存",
      reviewDelete: "刪除",
      reviewCancel: "取消",
      reviewDocumentComment: "整頁評論",
      reviewPageComments: "頁面評論",
      reviewUnplacedHelp: "這些評論已儲存到本頁；精確底線位置目前不可用。",
      reviewPlaceholder: "寫下需要修改的內容，以及為什麼重要。",
      reviewLoading: "評論仍在載入。",
      reviewNeedComment: "儲存前請先填寫評論。",
      reviewSaved: "已儲存。",
      reviewDeleted: "已刪除。",
      reviewRequestFailed: "請求失敗",
      reviewErrorPrefix: "錯誤",
      reviewUnderlineUnavailable: "無法定位精確底線。",
      reviewUnderlineAmbiguous: "精確底線位置不唯一。",
      reviewQuoteUnresolved: "無法解析引用位置。",
    },
  };

  let currentLocale = initialLocale();

  function readStorage(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (_error) {
      return null;
    }
  }

  function writeStorage(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (_error) {
      // Storage is optional for local static files and strict browser modes.
    }
  }

  function normalizeTheme(value) {
    return SUPPORTED_THEMES.has(value) ? value : "";
  }

  function normalizeLocale(value) {
    if (SUPPORTED_LOCALES.has(value)) {
      return value;
    }
    if (value && value.toLowerCase() === "zh-cn") {
      return "zh-CN";
    }
    if (value && ["zh-tw", "zh-hk", "zh-mo", "zh-hant"].includes(value.toLowerCase())) {
      return "zh-TW";
    }
    return "";
  }

  function initialLocale() {
    return (
      normalizeLocale(readStorage(LOCALE_STORAGE_KEY)) ||
      normalizeLocale(document.documentElement.lang) ||
      DEFAULT_LOCALE
    );
  }

  function t(key) {
    const messages = MESSAGES[currentLocale] || MESSAGES[DEFAULT_LOCALE];
    return messages[key] || MESSAGES[DEFAULT_LOCALE][key] || key;
  }

  function elementsMatching(root, selector) {
    const elements = [];
    if (root instanceof Element && root.matches(selector)) {
      elements.push(root);
    }
    if (root.querySelectorAll) {
      elements.push(...root.querySelectorAll(selector));
    }
    return elements;
  }

  function isUiTranslationElement(element) {
    const markdownContent = element.closest("[data-mdfh-content='1']");
    return !markdownContent || Boolean(element.closest("[data-mdfh-ui]"));
  }

  function applyTranslations(root = document) {
    elementsMatching(root, "[data-i18n]").filter(isUiTranslationElement).forEach((element) => {
      element.textContent = t(element.dataset.i18n);
      element.setAttribute("lang", currentLocale);
    });
    elementsMatching(root, "[data-i18n-aria-label]").filter(isUiTranslationElement).forEach((element) => {
      element.setAttribute("aria-label", t(element.dataset.i18nAriaLabel));
      element.setAttribute("lang", currentLocale);
    });
    elementsMatching(root, "[data-i18n-title]").filter(isUiTranslationElement).forEach((element) => {
      element.setAttribute("title", t(element.dataset.i18nTitle));
      element.setAttribute("lang", currentLocale);
    });
    elementsMatching(root, "[data-i18n-placeholder]").filter(isUiTranslationElement).forEach((element) => {
      element.setAttribute("placeholder", t(element.dataset.i18nPlaceholder));
      element.setAttribute("lang", currentLocale);
    });
  }

  function setLocale(locale, { persist = true } = {}) {
    const normalizedLocale = normalizeLocale(locale) || DEFAULT_LOCALE;
    currentLocale = normalizedLocale;
    if (persist) {
      writeStorage(LOCALE_STORAGE_KEY, normalizedLocale);
    }
    syncLocaleSelect();
    applyTranslations(document);
    syncThemeToggle();
    window.dispatchEvent(new CustomEvent("mdfh:localechange", {
      detail: { locale: normalizedLocale },
    }));
  }

  function syncLocaleSelect() {
    const localeSelect = document.querySelector("[data-locale-select]");
    if (localeSelect) {
      localeSelect.value = currentLocale;
    }
  }

  function effectiveTheme() {
    const explicitTheme = normalizeTheme(document.documentElement.dataset.theme || readStorage(THEME_STORAGE_KEY));
    if (explicitTheme) {
      return explicitTheme;
    }
    if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }
    return "light";
  }

  function applyStoredTheme() {
    const storedTheme = normalizeTheme(readStorage(THEME_STORAGE_KEY));
    if (storedTheme) {
      document.documentElement.dataset.theme = storedTheme;
    } else {
      delete document.documentElement.dataset.theme;
    }
    syncThemeToggle();
  }

  function setTheme(theme) {
    const normalizedTheme = normalizeTheme(theme) || "light";
    document.documentElement.dataset.theme = normalizedTheme;
    writeStorage(THEME_STORAGE_KEY, normalizedTheme);
    syncThemeToggle();
  }

  function syncThemeToggle() {
    const toggle = document.querySelector("[data-theme-toggle]");
    if (!toggle) {
      return;
    }
    const isDark = effectiveTheme() === "dark";
    const labelKey = isDark ? "themeLight" : "themeDark";
    const actionKey = isDark ? "switchToLight" : "switchToDark";
    toggle.textContent = t(labelKey);
    toggle.setAttribute("aria-label", t(actionKey));
    toggle.setAttribute("title", t(actionKey));
    toggle.setAttribute("lang", currentLocale);
  }

  window.mdfhI18n = {
    apply: applyTranslations,
    locale: () => currentLocale,
    t,
  };

  document.addEventListener("DOMContentLoaded", () => {
    const layout = document.querySelector("[data-layout]");
    const sidebar = document.querySelector("[data-sidebar]");
    const toggles = Array.from(document.querySelectorAll("[data-sidebar-toggle]"));
    const tocToggle = document.querySelector("[data-toc-toggle]");
    const tocContent = document.querySelector("[data-toc-content]");
    const siteNavToggle = document.querySelector("[data-site-nav-toggle]");
    const siteNavContent = document.querySelector("[data-site-nav-content]");
    const localeSelect = document.querySelector("[data-locale-select]");
    const themeToggle = document.querySelector("[data-theme-toggle]");
    const themeMediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const isMobileViewport = () => window.matchMedia("(max-width: 960px)").matches;

    const sidebarLabel = (expanded) => {
      if (isMobileViewport()) {
        return expanded ? t("close") : t("menu");
      }
      return expanded ? t("collapseSidebar") : t("expandSidebar");
    };

    const syncSidebarState = (expanded) => {
      const label = sidebarLabel(expanded);
      toggles.forEach((toggle) => {
        const isToolbarToggle = toggle.classList.contains("page-toolbar-toggle");
        const isEdgeToggle = toggle.hasAttribute("data-sidebar-edge-toggle");

        toggle.setAttribute("aria-expanded", String(expanded));
        toggle.setAttribute("aria-label", label);

        if (isEdgeToggle && !isMobileViewport()) {
          toggle.textContent = expanded ? "‹" : ">";
          toggle.title = label;
          return;
        }

        if (isToolbarToggle && !isMobileViewport()) {
          toggle.textContent = t("menu");
          toggle.title = label;
          return;
        }

        if (isToolbarToggle) {
          toggle.textContent = t("menu");
        } else {
          toggle.textContent = label;
        }
      });
    };

    applyStoredTheme();
    setLocale(currentLocale, { persist: false });

    if (themeToggle) {
      themeToggle.addEventListener("click", () => {
        setTheme(effectiveTheme() === "dark" ? "light" : "dark");
      });
    }

    if (themeMediaQuery.addEventListener) {
      themeMediaQuery.addEventListener("change", () => {
        if (!normalizeTheme(readStorage(THEME_STORAGE_KEY))) {
          syncThemeToggle();
        }
      });
    }

    if (localeSelect) {
      localeSelect.addEventListener("change", () => {
        setLocale(localeSelect.value);
      });
    }

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
        siteNavToggle.textContent = expanded ? t("hide") : t("show");
        siteNavContent.hidden = !expanded;
      };

      syncSiteNavState(true);
      siteNavToggle.addEventListener("click", () => {
        syncSiteNavState(siteNavContent.hidden);
      });
      window.addEventListener("mdfh:localechange", () => {
        syncSiteNavState(!siteNavContent.hidden);
      });
    }

    if (tocToggle && tocContent) {
      const syncTocState = (expanded) => {
        tocToggle.setAttribute("aria-expanded", String(expanded));
        tocToggle.textContent = expanded ? t("hide") : t("show");
        tocContent.hidden = !expanded;
      };

      syncTocState(true);
      tocToggle.addEventListener("click", () => {
        syncTocState(tocContent.hidden);
      });
      window.addEventListener("mdfh:localechange", () => {
        syncTocState(!tocContent.hidden);
      });
    }

    window.addEventListener("mdfh:localechange", () => {
      if (layout && sidebar && toggles.length > 0) {
        const expanded = isMobileViewport()
          ? sidebar.classList.contains("is-open")
          : !layout.classList.contains("is-sidebar-collapsed");
        syncSidebarState(expanded);
      }
    });

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
})();
