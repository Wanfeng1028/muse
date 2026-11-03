"use strict";

// electron/preview/picker/picker-locale.ts
var currentLocale = {};
function setPickerLocale(locale) {
  currentLocale = locale;
}
function getPickerLocale() {
  return currentLocale;
}

// electron/preview/picker/comment-popover.ts
var POPOVER_ID = "__onevium-comment-popover";
var FALLBACK_PALETTE = {
  surface: "#ffffff",
  outline: "none",
  border: "rgba(0, 0, 0, 0.08)",
  shadow: "0 12px 32px rgba(0, 0, 0, 0.14), 0 2px 8px rgba(0, 0, 0, 0.08)",
  text: "#171717",
  textareaBg: "#ffffff",
  textareaBorder: "rgba(0, 0, 0, 0.10)",
  primaryBg: "#171717",
  primaryText: "#ffffff",
  ghostText: "#444444",
  ghostBorder: "rgba(0, 0, 0, 0.10)"
};
function getLocale() {
  const injected = getPickerLocale();
  const p = injected.palette ?? {};
  return {
    popoverPlaceholder: injected.popoverPlaceholder ?? "Add a note about this element\u2026",
    popoverCancel: injected.popoverCancel ?? "Cancel",
    popoverSubmit: injected.popoverSubmit ?? "Add",
    popoverCancelKey: injected.popoverCancelKey,
    popoverSubmitKey: injected.popoverSubmitKey,
    commentKeys: injected.commentKeys ?? "Enter to save \xB7 Shift+Enter for a new line \xB7 Esc to cancel",
    palette: {
      surface: p.surface ?? FALLBACK_PALETTE.surface,
      outline: p.outline ?? FALLBACK_PALETTE.outline,
      border: p.border ?? FALLBACK_PALETTE.border,
      shadow: p.shadow ?? FALLBACK_PALETTE.shadow,
      text: p.text ?? FALLBACK_PALETTE.text,
      textareaBg: p.textareaBg ?? FALLBACK_PALETTE.textareaBg,
      textareaBorder: p.textareaBorder ?? FALLBACK_PALETTE.textareaBorder,
      primaryBg: p.primaryBg ?? FALLBACK_PALETTE.primaryBg,
      primaryText: p.primaryText ?? FALLBACK_PALETTE.primaryText,
      ghostText: p.ghostText ?? FALLBACK_PALETTE.ghostText,
      ghostBorder: p.ghostBorder ?? FALLBACK_PALETTE.ghostBorder
    }
  };
}
var activeResolver = null;
var activeCleanup = null;
function dismiss(reason, payload) {
  activeCleanup?.();
  activeCleanup = null;
  const node = document.getElementById(POPOVER_ID);
  if (node) node.remove();
  const r = activeResolver;
  activeResolver = null;
  if (!r) return;
  r(reason === "submit" && payload ? payload : null);
}
function getPopoverPalette() {
  return getLocale().palette;
}
function showCommentPopover(anchor) {
  if (activeResolver) dismiss("cancel");
  const locale = getLocale();
  const palette = locale.palette;
  return new Promise((resolve) => {
    activeResolver = resolve;
    const root = document.createElement("div");
    root.id = POPOVER_ID;
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-label", locale.popoverPlaceholder);
    Object.assign(root.style, {
      position: "fixed",
      zIndex: "2147483647",
      width: `${Math.max(0, Math.min(360, window.innerWidth - 16))}px`,
      maxHeight: "calc(100vh - 16px)",
      overflowY: "auto",
      display: "flex",
      alignItems: "center",
      gap: "10px",
      boxSizing: "border-box",
      padding: "8px 8px 8px 18px",
      background: palette.surface,
      border: "none",
      outline: palette.outline,
      borderRadius: "26px",
      boxShadow: palette.shadow,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
      fontSize: "14px",
      color: palette.text,
      lineHeight: "20px",
      pointerEvents: "auto"
    });
    const textarea = document.createElement("textarea");
    textarea.rows = 1;
    Object.assign(textarea.style, {
      flex: "1",
      minWidth: "0",
      width: "100%",
      height: "28px",
      minHeight: "28px",
      maxHeight: "min(160px, 40vh)",
      padding: "4px 0",
      margin: "0",
      border: "none",
      borderRadius: "0",
      boxShadow: "none",
      resize: "none",
      fontFamily: "inherit",
      fontSize: "14px",
      lineHeight: "20px",
      color: palette.text,
      background: "transparent",
      outline: "none",
      boxSizing: "border-box"
    });
    textarea.placeholder = locale.popoverPlaceholder;
    textarea.setAttribute("aria-label", locale.popoverPlaceholder);
    textarea.title = locale.commentKeys;
    textarea.value = anchor.initial ?? "";
    const submitBtn = document.createElement("button");
    submitBtn.type = "button";
    submitBtn.setAttribute("aria-label", locale.popoverSubmit);
    submitBtn.title = `${locale.popoverSubmit} \xB7 ${locale.commentKeys}`;
    submitBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 12 4 4 8-9"/></svg>';
    Object.assign(submitBtn.style, {
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      flex: "0 0 32px",
      width: "32px",
      height: "32px",
      padding: "0",
      margin: "0",
      border: "none",
      borderRadius: "50%",
      background: palette.primaryBg,
      color: palette.primaryText,
      cursor: "pointer",
      boxShadow: "none"
    });
    const styles = document.createElement("style");
    styles.textContent = `#${POPOVER_ID} button:hover { filter: brightness(.9); }
      #${POPOVER_ID} button:focus-visible { outline: 2px solid ${palette.text}; outline-offset: 3px; }
      #${POPOVER_ID} textarea::placeholder { color: ${palette.ghostText}; opacity: 1; }`;
    root.append(styles, textarea, submitBtn);
    const submit = () => dismiss("submit", { comment: textarea.value.trim() });
    submitBtn.addEventListener("click", submit);
    root.addEventListener("keydown", (e) => {
      if (e.isComposing || e.keyCode === 229) return;
      if (e.key === "Escape") {
        e.preventDefault();
        dismiss("cancel");
      } else if (e.target === textarea && e.key === "Enter" && (!e.shiftKey || e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        submit();
      } else if (e.key === "Tab") {
        e.preventDefault();
        (document.activeElement === textarea ? submitBtn : textarea).focus();
      }
    });
    document.documentElement.appendChild(root);
    const position2 = () => {
      root.style.width = `${Math.max(0, Math.min(360, window.innerWidth - 16))}px`;
      const { width, height } = root.getBoundingClientRect();
      const targetLeft = anchor.rect.x - window.scrollX;
      const targetTop = anchor.rect.y - window.scrollY;
      const right = targetLeft + anchor.rect.width + 10;
      const beside = anchor.preferred !== "below" && right + width <= window.innerWidth - 8;
      const below = targetTop + anchor.rect.height + 8;
      const desiredTop = beside ? targetTop + (anchor.rect.height - height) / 2 : below + height <= window.innerHeight - 8 ? below : targetTop - height - 8;
      const left = Math.max(8, Math.min(window.innerWidth - width - 8, beside ? right : targetLeft));
      const top = Math.max(8, Math.min(window.innerHeight - height - 8, desiredTop));
      Object.assign(root.style, { top: `${top}px`, left: `${left}px` });
    };
    const fitText = () => {
      position2();
      textarea.style.height = "28px";
      textarea.style.height = `${Math.max(28, Math.min(160, window.innerHeight * 0.4, textarea.scrollHeight))}px`;
      textarea.style.overflowY = textarea.scrollHeight > textarea.clientHeight ? "auto" : "hidden";
      const multiline = textarea.clientHeight > 36;
      root.style.borderRadius = multiline ? "18px" : "26px";
      submitBtn.style.alignSelf = multiline ? "flex-end" : "center";
      position2();
    };
    textarea.addEventListener("input", fitText);
    fitText();
    window.addEventListener("resize", fitText);
    window.addEventListener("scroll", position2, true);
    const resizeObserver = new ResizeObserver(position2);
    resizeObserver.observe(root);
    const focusFrame = requestAnimationFrame(() => textarea.focus({ preventScroll: true }));
    activeCleanup = () => {
      window.removeEventListener("resize", fitText);
      window.removeEventListener("scroll", position2, true);
      resizeObserver.disconnect();
      cancelAnimationFrame(focusFrame);
    };
  });
}
function isPopoverOpen() {
  return activeResolver !== null;
}
function dismissPopover() {
  if (activeResolver) dismiss("cancel");
}

// electron/preview/picker/hover-info.ts
var HoverInfo = class {
  constructor() {
    this.root = null;
    this.target = null;
    this.timer = null;
  }
  show(target) {
    if (this.target === target) return;
    this.hide();
    this.target = target;
    this.timer = setTimeout(() => {
      this.timer = null;
      if (!target.isConnected) return;
      const palette = getPopoverPalette();
      const locale = getPickerLocale();
      const rect = target.getBoundingClientRect();
      const css = window.getComputedStyle(target);
      const root = this.root ?? document.createElement("div");
      this.root = root;
      root.id = "__onevium-hover-info";
      root.setAttribute("aria-hidden", "true");
      Object.assign(root.style, {
        position: "fixed",
        zIndex: "2147483647",
        pointerEvents: "none",
        display: "block",
        width: `${Math.max(0, Math.min(272, window.innerWidth - 16))}px`,
        boxSizing: "border-box",
        padding: "10px 12px",
        borderRadius: "12px",
        background: palette.surface,
        color: palette.text,
        border: "none",
        outline: palette.outline,
        boxShadow: palette.shadow,
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
        fontSize: "12px",
        fontWeight: "400",
        lineHeight: "18px",
        textAlign: "left",
        maxHeight: "calc(100vh - 16px)",
        overflow: "hidden"
      });
      const hint = document.createElement("div");
      hint.textContent = locale.hoverHint ?? "Hold Alt and click to comment";
      Object.assign(hint.style, { color: palette.ghostText, fontSize: "11px", marginBottom: "6px" });
      root.replaceChildren(hint);
      const addRow = (label, value, primary = false) => {
        const row = document.createElement("div");
        Object.assign(row.style, { display: "flex", gap: "12px", justifyContent: "space-between" });
        const name = document.createElement("span");
        name.textContent = label;
        Object.assign(name.style, { color: primary ? palette.text : palette.ghostText, flexShrink: "0" });
        const detail = document.createElement("span");
        detail.textContent = value;
        Object.assign(detail.style, { minWidth: "0", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textAlign: "right" });
        row.append(name, detail);
        root.append(row);
      };
      addRow(target.tagName.toLowerCase(), `${Math.round(rect.width)} \xD7 ${Math.round(rect.height)}`, true);
      addRow(locale.colorLabel ?? "Color", readableColor(css.color));
      addRow(locale.fontLabel ?? "Font", `${css.fontSize} ${css.fontFamily.split(",")[0].trim().replace(/^['"]|['"]$/g, "")}`);
      document.documentElement.append(root);
      const { width, height } = root.getBoundingClientRect();
      const top = rect.top - height - 10 >= 8 ? rect.top - height - 10 : rect.bottom + 10;
      Object.assign(root.style, {
        left: `${Math.max(8, Math.min(window.innerWidth - width - 8, rect.left))}px`,
        top: `${Math.max(8, Math.min(window.innerHeight - height - 8, top))}px`
      });
    }, 140);
  }
  hide() {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.target = null;
    if (this.root) this.root.style.display = "none";
  }
  destroy() {
    this.hide();
    this.root?.remove();
    this.root = null;
  }
};
function readableColor(color) {
  const match = /^rgb\(\s*(\d+),\s*(\d+),\s*(\d+)\s*\)$/.exec(color);
  return match ? "#" + match.slice(1).map((channel) => Number(channel).toString(16).padStart(2, "0")).join("").toUpperCase() : color;
}

// electron/preview/picker/highlight-overlay.ts
var HighlightOverlay = class {
  constructor() {
    this.info = new HoverInfo();
    this.mounted = false;
    this.selectedRect = null;
    this.el = document.createElement("div");
    this.el.id = "__onevium-highlight-overlay";
    this.el.setAttribute("aria-hidden", "true");
    Object.assign(this.el.style, {
      position: "absolute",
      pointerEvents: "none",
      zIndex: "2147483646",
      border: "2px solid rgb(50, 151, 255)",
      background: "rgba(50, 151, 255, 0.04)",
      borderRadius: "5px",
      transition: "background 120ms ease-out",
      display: "none",
      boxSizing: "border-box"
    });
  }
  mount() {
    if (this.mounted) return;
    document.documentElement.appendChild(this.el);
    this.mounted = true;
  }
  /** Hover mode — viewport-coords (the page can scroll under it). */
  show(target) {
    if (this.selectedRect) return;
    this.mount();
    const rect = target.getBoundingClientRect();
    Object.assign(this.el.style, {
      display: "block",
      // Switch to page coords here too so we don't have to swap modes mid-flight.
      top: `${rect.top + window.scrollY}px`,
      left: `${rect.left + window.scrollX}px`,
      width: `${rect.width}px`,
      height: `${rect.height}px`,
      borderStyle: "solid",
      background: "rgba(50, 151, 255, 0.04)"
    });
    this.info.show(target);
  }
  hide() {
    this.info.hide();
    if (this.selectedRect) return;
    this.el.style.display = "none";
  }
  /**
   * Pin a "you picked this" rectangle to a specific page-coord rect. While a
   * selection is active, hover show/hide are no-ops — the picked element
   * remains visually anchored throughout comment authoring.
   */
  setSelected(rect) {
    this.mount();
    this.selectedRect = { ...rect };
    Object.assign(this.el.style, {
      display: "block",
      top: `${rect.y}px`,
      left: `${rect.x}px`,
      width: `${rect.width}px`,
      height: `${rect.height}px`,
      borderStyle: "solid",
      background: "rgba(50, 151, 255, 0.08)"
    });
    this.info.hide();
  }
  clearSelected() {
    this.info.hide();
    this.selectedRect = null;
    this.el.style.display = "none";
  }
  destroy() {
    this.info.destroy();
    this.el.remove();
    this.mounted = false;
    this.selectedRect = null;
  }
};
var DragRectOverlay = class {
  constructor() {
    this.mounted = false;
    this.el = document.createElement("div");
    Object.assign(this.el.style, {
      position: "fixed",
      pointerEvents: "none",
      zIndex: "2147483646",
      border: "1.5px dashed rgb(50, 151, 255)",
      background: "rgba(50, 151, 255, 0.04)",
      display: "none",
      boxSizing: "border-box"
    });
  }
  mount() {
    if (this.mounted) return;
    document.documentElement.appendChild(this.el);
    this.mounted = true;
  }
  show(rect) {
    this.mount();
    Object.assign(this.el.style, {
      display: "block",
      top: `${rect.y}px`,
      left: `${rect.x}px`,
      width: `${rect.width}px`,
      height: `${rect.height}px`
    });
  }
  hide() {
    this.el.style.display = "none";
  }
  destroy() {
    this.el.remove();
    this.mounted = false;
  }
};
function installPickerCursor() {
  const cursorSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32"><path d="M4 27V14a12 12 0 1 1 12 12H4Z" fill="#3297ff" stroke="white" stroke-width="2" stroke-linejoin="round"/></svg>';
  const cursorUrl = `data:image/svg+xml,${encodeURIComponent(cursorSvg)}`;
  const style = document.createElement("style");
  style.id = "__onevium-picker-cursor";
  style.textContent = `
    html.__onevium-picking,
    html.__onevium-picking * {
      cursor: url("${cursorUrl}") 4 27, auto !important;
    }
    html.__onevium-picking.__onevium-picking-region,
    html.__onevium-picking.__onevium-picking-region * {
      cursor: crosshair !important;
    }
    html.__onevium-picking #__onevium-comment-popover,
    html.__onevium-picking #__onevium-comment-popover * {
      cursor: auto !important;
    }
    html.__onevium-picking #__onevium-comment-popover textarea,
    html.__onevium-picking #__onevium-comment-popover input {
      cursor: text !important;
    }
    html.__onevium-picking #__onevium-comment-popover button,
    html.__onevium-picking #__onevium-comment-popover button * {
      cursor: pointer !important;
    }
    html.__onevium-picking #__onevium-pin-overlay,
    html.__onevium-picking #__onevium-pin-overlay * {
      cursor: pointer !important;
    }
    html.__onevium-picking #__onevium-hover-badge,
    html.__onevium-picking #__onevium-hover-badge * {
      cursor: pointer !important;
    }
  `;
  document.documentElement.appendChild(style);
  document.documentElement.classList.add("__onevium-picking");
  return () => {
    document.documentElement.classList.remove("__onevium-picking");
    document.documentElement.classList.remove("__onevium-picking-region");
    style.remove();
  };
}

// node_modules/@medv/finder/finder.js
var acceptedAttrNames = /* @__PURE__ */ new Set(["role", "name", "aria-label", "rel", "href"]);
function attr(name, value) {
  let nameIsOk = acceptedAttrNames.has(name);
  nameIsOk ||= name.startsWith("data-") && wordLike(name);
  let valueIsOk = wordLike(value) && value.length < 100;
  valueIsOk ||= value.startsWith("#") && wordLike(value.slice(1));
  return nameIsOk && valueIsOk;
}
function idName(name) {
  return wordLike(name);
}
function className(name) {
  return wordLike(name);
}
function tagName(name) {
  return true;
}
function finder(input, options) {
  if (input.nodeType !== Node.ELEMENT_NODE) {
    throw new Error(`Can't generate CSS selector for non-element node type.`);
  }
  if (input.tagName.toLowerCase() === "html") {
    return "html";
  }
  const defaults = {
    root: document.body,
    idName,
    className,
    tagName,
    attr,
    timeoutMs: 1e3,
    seedMinLength: 3,
    optimizedMinLength: 2,
    maxNumberOfPathChecks: Infinity
  };
  const startTime = /* @__PURE__ */ new Date();
  const config = { ...defaults, ...options };
  const rootDocument = findRootDocument(config.root, defaults);
  let foundPath;
  let count = 0;
  for (const candidate of search(input, config, rootDocument)) {
    const elapsedTimeMs = (/* @__PURE__ */ new Date()).getTime() - startTime.getTime();
    if (elapsedTimeMs > config.timeoutMs || count >= config.maxNumberOfPathChecks) {
      const fPath = fallback(input, rootDocument);
      if (!fPath) {
        throw new Error(`Timeout: Can't find a unique selector after ${config.timeoutMs}ms`);
      }
      return selector(fPath);
    }
    count++;
    if (unique(candidate, rootDocument)) {
      foundPath = candidate;
      break;
    }
  }
  if (!foundPath) {
    throw new Error(`Selector was not found.`);
  }
  const optimized = [
    ...optimize(foundPath, input, config, rootDocument, startTime)
  ];
  optimized.sort(byPenalty);
  if (optimized.length > 0) {
    return selector(optimized[0]);
  }
  return selector(foundPath);
}
function* search(input, config, rootDocument) {
  const stack = [];
  let paths = [];
  let current = input;
  let i = 0;
  while (current && current !== rootDocument) {
    const level = tie(current, config);
    for (const node of level) {
      node.level = i;
    }
    stack.push(level);
    current = current.parentElement;
    i++;
    paths.push(...combinations(stack));
    if (i >= config.seedMinLength) {
      paths.sort(byPenalty);
      for (const candidate of paths) {
        yield candidate;
      }
      paths = [];
    }
  }
  paths.sort(byPenalty);
  for (const candidate of paths) {
    yield candidate;
  }
}
function wordLike(name) {
  if (/^[a-z\-]{3,}$/i.test(name)) {
    const words = name.split(/-|[A-Z]/);
    for (const word of words) {
      if (word.length <= 2) {
        return false;
      }
      if (/[^aeiou]{4,}/i.test(word)) {
        return false;
      }
    }
    return true;
  }
  return false;
}
function tie(element, config) {
  const level = [];
  const elementId = element.getAttribute("id");
  if (elementId && config.idName(elementId)) {
    level.push({
      name: "#" + CSS.escape(elementId),
      penalty: 0
    });
  }
  for (let i = 0; i < element.classList.length; i++) {
    const name = element.classList[i];
    if (config.className(name)) {
      level.push({
        name: "." + CSS.escape(name),
        penalty: 1
      });
    }
  }
  for (let i = 0; i < element.attributes.length; i++) {
    const attr2 = element.attributes[i];
    if (config.attr(attr2.name, attr2.value)) {
      level.push({
        name: `[${CSS.escape(attr2.name)}="${CSS.escape(attr2.value)}"]`,
        penalty: 2
      });
    }
  }
  const tagName2 = element.tagName.toLowerCase();
  if (config.tagName(tagName2)) {
    level.push({
      name: tagName2,
      penalty: 5
    });
    const index = indexOf(element, tagName2);
    if (index !== void 0) {
      level.push({
        name: nthOfType(tagName2, index),
        penalty: 10
      });
    }
  }
  const nth = indexOf(element);
  if (nth !== void 0) {
    level.push({
      name: nthChild(tagName2, nth),
      penalty: 50
    });
  }
  return level;
}
function selector(path) {
  let node = path[0];
  let query = node.name;
  for (let i = 1; i < path.length; i++) {
    const level = path[i].level || 0;
    if (node.level === level - 1) {
      query = `${path[i].name} > ${query}`;
    } else {
      query = `${path[i].name} ${query}`;
    }
    node = path[i];
  }
  return query;
}
function penalty(path) {
  return path.map((node) => node.penalty).reduce((acc, i) => acc + i, 0);
}
function byPenalty(a, b) {
  return penalty(a) - penalty(b);
}
function indexOf(input, tagName2) {
  const parent = input.parentNode;
  if (!parent) {
    return void 0;
  }
  let child = parent.firstChild;
  if (!child) {
    return void 0;
  }
  let i = 0;
  while (child) {
    if (child.nodeType === Node.ELEMENT_NODE && (tagName2 === void 0 || child.tagName.toLowerCase() === tagName2)) {
      i++;
    }
    if (child === input) {
      break;
    }
    child = child.nextSibling;
  }
  return i;
}
function fallback(input, rootDocument) {
  let i = 0;
  let current = input;
  const path = [];
  while (current && current !== rootDocument) {
    const tagName2 = current.tagName.toLowerCase();
    const index = indexOf(current, tagName2);
    if (index === void 0) {
      return;
    }
    path.push({
      name: nthOfType(tagName2, index),
      penalty: NaN,
      level: i
    });
    current = current.parentElement;
    i++;
  }
  if (unique(path, rootDocument)) {
    return path;
  }
}
function nthChild(tagName2, index) {
  if (tagName2 === "html") {
    return "html";
  }
  return `${tagName2}:nth-child(${index})`;
}
function nthOfType(tagName2, index) {
  if (tagName2 === "html") {
    return "html";
  }
  return `${tagName2}:nth-of-type(${index})`;
}
function* combinations(stack, path = []) {
  if (stack.length > 0) {
    for (let node of stack[0]) {
      yield* combinations(stack.slice(1, stack.length), path.concat(node));
    }
  } else {
    yield path;
  }
}
function findRootDocument(rootNode, defaults) {
  if (rootNode.nodeType === Node.DOCUMENT_NODE) {
    return rootNode;
  }
  if (rootNode === defaults.root) {
    return rootNode.ownerDocument;
  }
  return rootNode;
}
function unique(path, rootDocument) {
  const css = selector(path);
  switch (rootDocument.querySelectorAll(css).length) {
    case 0:
      throw new Error(`Can't select any node with this selector: ${css}`);
    case 1:
      return true;
    default:
      return false;
  }
}
function* optimize(path, input, config, rootDocument, startTime) {
  if (path.length > 2 && path.length > config.optimizedMinLength) {
    for (let i = 1; i < path.length - 1; i++) {
      const elapsedTimeMs = (/* @__PURE__ */ new Date()).getTime() - startTime.getTime();
      if (elapsedTimeMs > config.timeoutMs) {
        return;
      }
      const newPath = [...path];
      newPath.splice(i, 1);
      if (unique(newPath, rootDocument) && rootDocument.querySelector(selector(newPath)) === input) {
        yield newPath;
        yield* optimize(newPath, input, config, rootDocument, startTime);
      }
    }
  }
}

// electron/preview/picker/finder-wrapper.ts
function generateSelector(el) {
  const root = el.getRootNode();
  const inShadowDom = root instanceof ShadowRoot;
  let selector2 = "";
  try {
    if (inShadowDom) {
      const host = root.host;
      const inner = safeFinder(el, root);
      const hostSel = safeFinder(host, host.getRootNode());
      selector2 = `${hostSel} >>> ${inner}`;
    } else {
      selector2 = safeFinder(el, document);
    }
  } catch {
    selector2 = fallbackSelector(el);
  }
  return {
    selector: selector2,
    xpath: getXPath(el),
    inShadowDom
  };
}
function safeFinder(el, root) {
  if (root === document) {
    return finder(el, {
      className: (cls) => !cls.startsWith("css-") && !/^[_-]?[a-z0-9]{6,}$/i.test(cls),
      timeoutMs: 800
    });
  }
  return finder(el, {
    root,
    className: (cls) => !cls.startsWith("css-") && !/^[_-]?[a-z0-9]{6,}$/i.test(cls),
    timeoutMs: 800
  });
}
function fallbackSelector(el) {
  const parts = [];
  let node = el;
  while (node && node.nodeType === 1 && parts.length < 12) {
    const current = node;
    const tag = current.tagName.toLowerCase();
    const parent = current.parentElement;
    if (!parent) {
      parts.unshift(tag);
      break;
    }
    const siblings = [...parent.children].filter((s) => s.tagName === current.tagName);
    if (siblings.length === 1) {
      parts.unshift(tag);
    } else {
      const idx = siblings.indexOf(current) + 1;
      parts.unshift(`${tag}:nth-of-type(${idx})`);
    }
    node = parent;
  }
  return parts.join(" > ");
}
function getXPath(el) {
  const parts = [];
  let node = el;
  while (node && node.nodeType === 1) {
    const tag = node.nodeName.toLowerCase();
    const parent = node.parentElement;
    if (!parent) {
      parts.unshift(`/${tag}`);
      break;
    }
    const same = [...parent.children].filter((c) => c.nodeName === node.nodeName);
    const idx = same.indexOf(node) + 1;
    parts.unshift(same.length > 1 ? `${tag}[${idx}]` : tag);
    node = parent;
  }
  return parts.length ? "/" + parts.join("/") : "";
}
function elementFromComposedPath(e) {
  const path = e.composedPath();
  for (const node of path) {
    if (node instanceof Element) return node;
  }
  return null;
}

// electron/browser-runtime/secret-redaction.ts
var SECRET_PATTERNS = [
  "access_token",
  "auth_token",
  "api_key",
  "api-key",
  "apikey",
  "client_secret",
  "oauth_state",
  "x-amz-",
  "session_id",
  "sessionid",
  "csrf",
  "secret",
  "password",
  "passwd",
  "authorization",
  "bearer"
];
var REDACTED = "[redacted]";
function containsSecret(value) {
  if (!value) return false;
  const lower = value.toLowerCase();
  return SECRET_PATTERNS.some((p) => lower.includes(p));
}
function redactValue(value) {
  return containsSecret(value) ? REDACTED : value;
}
var SENSITIVE_INPUT_TYPES = /* @__PURE__ */ new Set(["password", "hidden"]);
var ATTR_RE = /([a-zA-Z-]+)=("([^"]*)"|'([^']*)')/g;
function redactHtml(html) {
  return html.replace(/<[a-zA-Z][a-zA-Z0-9-]*\s[^<>]*>/g, (tag) => {
    const attrs = [];
    let m;
    ATTR_RE.lastIndex = 0;
    while (m = ATTR_RE.exec(tag)) {
      const [, attrName, , dq, sq] = m;
      attrs.push({ attrName, value: dq ?? sq ?? "", quote: dq !== void 0 ? '"' : "'" });
    }
    const typeAttr = attrs.find((a) => a.attrName.toLowerCase() === "type")?.value.toLowerCase();
    const nameOrIdMatches = attrs.some(
      (a) => (a.attrName.toLowerCase() === "name" || a.attrName.toLowerCase() === "id") && containsSecret(a.value)
    );
    const valueImpliedSensitive = !!typeAttr && SENSITIVE_INPUT_TYPES.has(typeAttr) && nameOrIdMatches;
    let result = tag;
    for (const { attrName, value, quote } of attrs) {
      const lowerName = attrName.toLowerCase();
      if (!value) continue;
      const shouldRedact = containsSecret(attrName) || containsSecret(value) || lowerName === "value" && valueImpliedSensitive;
      if (!shouldRedact) continue;
      result = result.replace(
        `${attrName}=${quote}${value}${quote}`,
        `${attrName}=${quote}${REDACTED}${quote}`
      );
    }
    return result;
  });
}

// electron/preview/picker/element-extractor.ts
var OUTER_HTML_MAX = 2048;
var TEXT_SNIPPET_MAX = 200;
function extractElementInfo(el) {
  const sel = generateSelector(el);
  const tagName2 = el.tagName.toLowerCase();
  const id = el.id || null;
  const className2 = el.getAttribute("class");
  const html = el.outerHTML;
  const truncated = html.length > OUTER_HTML_MAX ? html.slice(0, OUTER_HTML_MAX) + "\n<!-- truncated -->" : html;
  const redactedHtml = redactHtml(truncated);
  const text = (el.textContent || "").replace(/\s+/g, " ").trim();
  const textSnippet = text ? redactValue(text.length > TEXT_SNIPPET_MAX ? text.slice(0, TEXT_SNIPPET_MAX) + "\u2026" : text) : null;
  const cs = window.getComputedStyle(el);
  const computedStyle = {
    color: cs.color,
    backgroundColor: cs.backgroundColor,
    fontSize: cs.fontSize,
    fontWeight: cs.fontWeight,
    display: cs.display,
    position: cs.position,
    width: cs.width,
    height: cs.height
  };
  const role = el.getAttribute("role") || implicitRole(el);
  const ariaLabel = el.getAttribute("aria-label") ? redactValue(el.getAttribute("aria-label")) : null;
  const accessibleName = ariaLabel || el.getAttribute("title") || textSnippet;
  const inIframe = window.self !== window.top;
  const iframeSrc = inIframe ? window.location.href : null;
  return {
    selector: sel.selector,
    xpath: sel.xpath,
    outerHTML: redactedHtml,
    tagName: tagName2,
    id,
    className: className2,
    textSnippet,
    computedStyle,
    accessibility: {
      role,
      ariaLabel,
      accessibleName
    },
    inShadowDom: sel.inShadowDom,
    inIframe,
    iframeSrc
  };
}
function implicitRole(el) {
  const map = {
    a: "link",
    button: "button",
    input: "textbox",
    textarea: "textbox",
    select: "combobox",
    img: "img",
    nav: "navigation",
    header: "banner",
    footer: "contentinfo",
    main: "main",
    aside: "complementary",
    h1: "heading",
    h2: "heading",
    h3: "heading",
    h4: "heading",
    h5: "heading",
    h6: "heading"
  };
  return map[el.tagName.toLowerCase()] || null;
}

// electron/preview/picker/gesture-handler.ts
var DRAG_MIN_PX = 6;
var GestureHandler = class {
  constructor(cb) {
    this.active = false;
    this.dragState = null;
    this.highlight = new HighlightOverlay();
    this.dragRect = new DragRectOverlay();
    this.uninstallCursor = null;
    this.onMouseMove = (e) => {
      if (!this.active) return;
      if (this.dragState) {
        e.preventDefault();
        const rect = computeViewportRect(this.dragState, { x: e.clientX, y: e.clientY });
        if (rect.width >= DRAG_MIN_PX || rect.height >= DRAG_MIN_PX) {
          this.dragRect.show(rect);
        }
        return;
      }
      if (isPopoverOpen()) {
        this.highlight.hide();
        return;
      }
      const target = elementFromComposedPath(e);
      if (!target) {
        this.highlight.hide();
        return;
      }
      if (isOurOverlay(target)) {
        return;
      }
      if (!isAnnotatableTarget(target)) {
        this.highlight.hide();
        return;
      }
      this.highlight.show(target);
    };
    this.onMouseDown = (e) => {
      if (!this.active) return;
      if (e.button !== 0) return;
      const target = elementFromComposedPath(e);
      const targetIsOurs = !!target && isOurOverlay(target);
      if (isPopoverOpen() && isInPopover(e.target)) {
        return;
      }
      if (isPopoverOpen()) {
        if (targetIsOurs) {
          dismissPopover();
          return;
        }
        dismissPopover();
      }
      if (targetIsOurs) return;
      if (e.shiftKey) {
        e.preventDefault();
        e.stopPropagation();
        this.dragState = {
          startX: e.clientX,
          startY: e.clientY,
          startScrollX: window.scrollX,
          startScrollY: window.scrollY
        };
        document.documentElement.classList.add("__onevium-picking-region");
        this.highlight.hide();
        return;
      }
      if (e.altKey) {
        e.preventDefault();
        e.stopPropagation();
        if (!target || !isAnnotatableTarget(target)) {
          this.highlight.hide();
          return;
        }
        void this.startPickWithPopover(target);
        return;
      }
    };
    this.onMouseUp = (e) => {
      if (!this.active) return;
      if (isPopoverOpen() && isInPopover(e.target)) return;
      if (this.dragState) {
        e.preventDefault();
        e.stopPropagation();
        document.documentElement.classList.remove("__onevium-picking-region");
        const rect = computeViewportRect(this.dragState, { x: e.clientX, y: e.clientY });
        this.dragRect.hide();
        if (rect.width >= DRAG_MIN_PX && rect.height >= DRAG_MIN_PX) {
          const pageRect = viewportToPageRect(rect, this.dragState);
          this.dragState = null;
          void (async () => {
            this.highlight.setSelected({ x: pageRect.x, y: pageRect.y, width: pageRect.width, height: pageRect.height });
            let result = null;
            try {
              result = await showCommentPopover({
                rect: { x: pageRect.x, y: pageRect.y, width: pageRect.width, height: pageRect.height }
              });
            } finally {
              this.highlight.clearSelected();
            }
            if (!result) return;
            this.cb.onRegionPicked({
              rect: pageRect,
              url: window.location.href,
              comment: result.comment
            });
          })();
          return;
        }
        this.dragState = null;
      }
    };
    /**
     * Swallow click / dblclick / auxclick that came from an annotation gesture,
     * so the underlying page doesn't ALSO fire its handlers. mousedown's
     * preventDefault doesn't prevent the synthesized click event that follows,
     * which is why this capture-phase swallow exists.
     *
     * Coexistence rule: only swallow clicks that carry one of OUR annotation
     * modifiers (Alt for popover, Shift for region drag). Plain clicks, and
     * Cmd/Ctrl clicks, MUST pass through untouched so ordinary page
     * interactions (links, buttons, tabs) and macOS' native Ctrl+Click context
     * menu keep working while the picker is enabled.
     *
     * The popover and our own overlays (pin) are also exempt — they have
     * legitimate click handlers that must survive.
     */
    this.onClickSwallow = (e) => {
      if (!this.active) return;
      if (isInPopover(e.target)) return;
      const target = elementFromComposedPath(e);
      if (target && isOurOverlay(target)) return;
      const hasAnnotationModifier = e.altKey || e.shiftKey;
      if (!hasAnnotationModifier) return;
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
    };
    this.onKeyDown = (e) => {
      if (!this.active) return;
      if (isPopoverOpen()) return;
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        this.dragState = null;
        this.dragRect.hide();
        document.documentElement.classList.remove("__onevium-picking-region");
        this.cb.onCancelled();
      }
    };
    this.onBlur = () => {
      this.highlight.hide();
      if (this.dragState) {
        this.dragState = null;
        document.documentElement.classList.remove("__onevium-picking-region");
        this.dragRect.hide();
      }
    };
    this.onMouseOut = (e) => {
      if (!e.relatedTarget) this.highlight.hide();
    };
    this.onScroll = () => {
      this.highlight.hide();
    };
    this.cb = cb;
  }
  setActive(active) {
    if (this.active === active) return;
    this.active = active;
    if (active) {
      this.uninstallCursor = installPickerCursor();
      document.addEventListener("mousemove", this.onMouseMove, true);
      document.addEventListener("mousedown", this.onMouseDown, true);
      document.addEventListener("mouseup", this.onMouseUp, true);
      document.addEventListener("click", this.onClickSwallow, true);
      document.addEventListener("dblclick", this.onClickSwallow, true);
      document.addEventListener("auxclick", this.onClickSwallow, true);
      document.addEventListener("keydown", this.onKeyDown, true);
      document.addEventListener("mouseout", this.onMouseOut, true);
      window.addEventListener("scroll", this.onScroll, true);
      window.addEventListener("blur", this.onBlur, true);
      window.addEventListener("resize", this.onScroll);
    } else {
      this.uninstallCursor?.();
      this.uninstallCursor = null;
      document.removeEventListener("mousemove", this.onMouseMove, true);
      document.removeEventListener("mousedown", this.onMouseDown, true);
      document.removeEventListener("mouseup", this.onMouseUp, true);
      document.removeEventListener("click", this.onClickSwallow, true);
      document.removeEventListener("dblclick", this.onClickSwallow, true);
      document.removeEventListener("auxclick", this.onClickSwallow, true);
      document.removeEventListener("keydown", this.onKeyDown, true);
      document.removeEventListener("mouseout", this.onMouseOut, true);
      window.removeEventListener("scroll", this.onScroll, true);
      window.removeEventListener("blur", this.onBlur, true);
      window.removeEventListener("resize", this.onScroll);
      dismissPopover();
      this.highlight.clearSelected();
      this.dragRect.hide();
      this.dragState = null;
    }
  }
  destroy() {
    this.setActive(false);
    this.highlight.destroy();
    this.dragRect.destroy();
  }
  async startPickWithPopover(target) {
    const info = extractElementInfo(target);
    const r = target.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const rect = {
      x: r.left + window.scrollX,
      y: r.top + window.scrollY,
      width: r.width,
      height: r.height,
      devicePixelRatio: dpr
    };
    this.highlight.setSelected({ x: rect.x, y: rect.y, width: rect.width, height: rect.height });
    let result = null;
    try {
      result = await showCommentPopover({ rect });
    } finally {
      this.highlight.clearSelected();
    }
    if (!result) return;
    this.cb.onElementPicked({
      gesture: "click",
      element: info,
      rect,
      url: window.location.href,
      comment: result.comment
    });
  }
};
function isAnnotatableTarget(target) {
  const tag = target.tagName.toLowerCase();
  if (tag === "html" || tag === "body") return false;
  const rect = target.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return false;
  if (target.matches('a, button, input, textarea, select, img, svg, canvas, video, iframe, [contenteditable]:not([contenteditable="false"]), [role="button"], [role="textbox"], [role="slider"]')) return true;
  const visibleWidth = Math.min(rect.right, window.innerWidth) - Math.max(rect.left, 0);
  const visibleHeight = Math.min(rect.bottom, window.innerHeight) - Math.max(rect.top, 0);
  const hasOwnText = Array.from(target.childNodes).some((node) => node.nodeType === Node.TEXT_NODE && !!node.textContent?.trim());
  return hasOwnText || visibleWidth < window.innerWidth * 0.9 || visibleHeight < window.innerHeight * 0.7;
}
function computeViewportRect(start, current) {
  const x = Math.min(start.startX, current.x);
  const y = Math.min(start.startY, current.y);
  const width = Math.abs(current.x - start.startX);
  const height = Math.abs(current.y - start.startY);
  return { x, y, width, height };
}
function viewportToPageRect(vp, start) {
  return {
    x: vp.x + start.startScrollX,
    y: vp.y + start.startScrollY,
    width: vp.width,
    height: vp.height,
    devicePixelRatio: window.devicePixelRatio || 1
  };
}
function isOurOverlay(el) {
  let node = el;
  while (node) {
    const id = node.id || "";
    if (id === "__onevium-badge-container" || id === "__onevium-pin-overlay" || id === "__onevium-comment-popover" || id === "__onevium-highlight-overlay") return true;
    if (node.tagName.toLowerCase() === "html" || node.tagName.toLowerCase() === "body") return false;
    node = node.parentElement;
  }
  return false;
}
function isInPopover(target) {
  if (!target || !(target instanceof Node)) return false;
  const pop = document.getElementById("__onevium-comment-popover");
  return !!(pop && pop.contains(target));
}

// electron/preview/picker/badge-overlay.ts
var BADGE_CONTAINER_ID = "__onevium-badge-container";
function injectBadges(badges) {
  removeBadges();
  const container = document.createElement("div");
  container.id = BADGE_CONTAINER_ID;
  container.setAttribute("aria-hidden", "true");
  Object.assign(container.style, {
    position: "absolute",
    top: "0",
    left: "0",
    width: "0",
    height: "0",
    zIndex: "2147483647",
    pointerEvents: "none"
  });
  for (const b of badges) {
    const pin = document.createElement("div");
    Object.assign(pin.style, {
      position: "absolute",
      // Anchor at top-right of the element rect for consistent visual scan.
      top: `${b.rect.y - 12}px`,
      left: `${b.rect.x + b.rect.width - 12}px`,
      width: "24px",
      height: "24px",
      borderRadius: "999px",
      background: "rgb(50, 151, 255)",
      color: "white",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif',
      fontSize: "12px",
      fontWeight: "700",
      boxShadow: "0 2px 8px rgba(0, 0, 0, 0.25)"
    });
    pin.textContent = String(b.ordinal);
    container.appendChild(pin);
    const outline = document.createElement("div");
    Object.assign(outline.style, {
      position: "absolute",
      top: `${b.rect.y}px`,
      left: `${b.rect.x}px`,
      width: `${b.rect.width}px`,
      height: `${b.rect.height}px`,
      border: "2px solid rgba(50, 151, 255, 0.85)",
      borderRadius: "2px",
      boxSizing: "border-box"
    });
    container.appendChild(outline);
  }
  document.documentElement.appendChild(container);
}
function removeBadges() {
  const existing = document.getElementById(BADGE_CONTAINER_ID);
  if (existing) existing.remove();
}

// electron/preview/picker/pin-overlay.ts
var PIN_CONTAINER_ID = "__onevium-pin-overlay";
function getPinDeleteLabel() {
  return getPickerLocale().deletePin || "Delete annotation";
}
var onClickHandler = null;
var onDeleteHandler = null;
var activePins = [];
var scrollListenerAttached = false;
var projectionRaf = 0;
function setPinHandlers(opts) {
  onClickHandler = opts.onClick;
  onDeleteHandler = opts.onDelete;
}
function syncPins(pins) {
  ensureContainer();
  ensureScrollListener();
  const container = document.getElementById(PIN_CONTAINER_ID);
  activePins = pins.slice();
  const incomingIds = new Set(pins.map((p) => p.id));
  for (const child of Array.from(container.children)) {
    const el = child;
    const id = el.dataset.pinId;
    if (!id || !incomingIds.has(id)) el.remove();
  }
  for (const pin of pins) {
    const existing = container.querySelector(`[data-pin-id="${cssEscape(pin.id)}"]`);
    if (existing) {
      updatePin(existing, pin);
    } else {
      const wrap = makePin(
        pin,
        /*animate*/
        true
      );
      container.appendChild(wrap);
    }
  }
  projectAll();
}
function clearPins() {
  activePins = [];
  window.removeEventListener("scroll", scheduleProjection, true);
  window.removeEventListener("resize", scheduleProjection);
  scrollListenerAttached = false;
  if (projectionRaf) cancelAnimationFrame(projectionRaf);
  projectionRaf = 0;
  const node = document.getElementById(PIN_CONTAINER_ID);
  if (node) node.remove();
}
function ensureContainer() {
  let container = document.getElementById(PIN_CONTAINER_ID);
  if (container) return container;
  container = document.createElement("div");
  container.id = PIN_CONTAINER_ID;
  Object.assign(container.style, {
    position: "fixed",
    top: "0",
    left: "0",
    width: "0",
    height: "0",
    pointerEvents: "none",
    zIndex: "2147483645",
    overflow: "visible"
  });
  document.documentElement.appendChild(container);
  return container;
}
function ensureScrollListener() {
  if (scrollListenerAttached) return;
  scrollListenerAttached = true;
  window.addEventListener("scroll", scheduleProjection, { passive: true, capture: true });
  window.addEventListener("resize", scheduleProjection, { passive: true });
}
function scheduleProjection() {
  if (projectionRaf) return;
  projectionRaf = requestAnimationFrame(() => {
    projectionRaf = 0;
    projectAll();
  });
}
function resolveLiveRect(pin) {
  if (pin.selector) {
    try {
      const el = document.querySelector(pin.selector);
      if (el) {
        const r = el.getBoundingClientRect();
        if (r.width > 0 || r.height > 0) {
          return { x: r.left, y: r.top, w: r.width, h: r.height };
        }
      }
    } catch (err) {
      console.warn("[onevium-picker] pin selector rejected by querySelector:", pin.selector, err);
    }
  }
  return {
    x: pin.rect.x - window.scrollX,
    y: pin.rect.y - window.scrollY,
    w: pin.rect.width,
    h: pin.rect.height
  };
}
function projectAll() {
  const container = document.getElementById(PIN_CONTAINER_ID);
  if (!container) return;
  for (const pin of activePins) {
    const el = container.querySelector(`[data-pin-id="${cssEscape(pin.id)}"]`);
    if (!el) continue;
    const live = resolveLiveRect(pin);
    if (!live || live.x + live.w < 0 || live.y + live.h < 0 || live.x > window.innerWidth || live.y > window.innerHeight) {
      el.style.display = "none";
      continue;
    }
    el.style.display = "block";
    el.style.left = `${live.x}px`;
    el.style.top = `${live.y}px`;
    el.style.width = `${live.w}px`;
    el.style.height = `${live.h}px`;
    const badge = el.querySelector('[data-pin-role="badge"]');
    const left = Math.max(4, Math.min(window.innerWidth - 28, live.x + live.w - 12));
    const top = Math.max(4, Math.min(window.innerHeight - 28, live.y - 12));
    badge.style.left = `${left - live.x}px`;
    badge.style.top = `${top - live.y}px`;
    const note = el.querySelector('[data-pin-role="note"]');
    if (note.style.display !== "none") positionNote(badge, note);
  }
}
function positionNote(badge, note) {
  note.style.maxWidth = `${Math.min(260, window.innerWidth - 16)}px`;
  note.style.maxHeight = `${Math.min(140, window.innerHeight - 16)}px`;
  const anchor = badge.getBoundingClientRect();
  const target = badge.parentElement.getBoundingClientRect();
  const { width, height } = note.getBoundingClientRect();
  const fitsRight = anchor.right + 10 + width <= window.innerWidth - 8;
  const desiredLeft = fitsRight ? anchor.right + 10 : anchor.left;
  const below = Math.max(anchor.bottom, target.bottom) + 8;
  const desiredTop = fitsRight ? anchor.top - 4 : below + height <= window.innerHeight - 8 ? below : Math.min(anchor.top, target.top) - height - 8;
  note.style.left = `${Math.max(8, Math.min(window.innerWidth - width - 8, desiredLeft))}px`;
  note.style.top = `${Math.max(8, Math.min(window.innerHeight - height - 8, desiredTop))}px`;
}
function updatePin(el, pin) {
  const del = el.querySelector('[data-pin-role="delete"]');
  if (del) {
    const label = getPinDeleteLabel();
    del.title = label;
    del.setAttribute("aria-label", label);
  }
  const dot = el.querySelector('[data-pin-role="dot"]');
  if (dot) {
    dot.textContent = String(pin.ordinal);
    dot.setAttribute("aria-label", pin.comment?.trim() ? `${pin.ordinal}: ${pin.comment.trim()}` : String(pin.ordinal));
  }
  const note = el.querySelector('[data-pin-role="note"]');
  if (note) {
    note.textContent = pin.comment?.trim() || "";
    if (!note.textContent) note.style.display = "none";
  }
}
function makePin(pin, animate) {
  const wrap = document.createElement("div");
  wrap.dataset.pinId = pin.id;
  Object.assign(wrap.style, {
    position: "absolute",
    left: "0px",
    top: "0px",
    width: "0px",
    height: "0px",
    pointerEvents: "none"
  });
  const outline = document.createElement("div");
  outline.dataset.pinRole = "outline";
  Object.assign(outline.style, {
    position: "absolute",
    inset: "0",
    border: "1.5px solid rgb(50, 151, 255)",
    background: "rgba(50, 151, 255, 0.04)",
    borderRadius: "2px",
    boxSizing: "border-box",
    pointerEvents: "none",
    opacity: "0",
    transition: "opacity 120ms ease"
  });
  wrap.appendChild(outline);
  const badge = document.createElement("div");
  badge.dataset.pinRole = "badge";
  Object.assign(badge.style, {
    position: "absolute",
    top: "-12px",
    left: "0px",
    width: "24px",
    height: "24px",
    pointerEvents: "auto"
  });
  const dot = document.createElement("button");
  dot.type = "button";
  dot.dataset.pinRole = "dot";
  Object.assign(dot.style, {
    width: "24px",
    height: "24px",
    border: "0",
    padding: "0",
    borderRadius: "12px 12px 12px 4px",
    background: "rgb(50, 151, 255)",
    color: "white",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif',
    fontSize: "11px",
    fontWeight: "700",
    boxShadow: "0 2px 6px rgba(0, 0, 0, 0.12), 0 0 0 2px rgba(255, 255, 255, 0.9)",
    cursor: "pointer",
    userSelect: "none",
    transition: "transform 120ms ease"
  });
  dot.textContent = String(pin.ordinal);
  if (animate) {
    ensurePinKeyframes();
    dot.style.animation = "oneviumPinPop 220ms ease-out";
  }
  const palette = getPopoverPalette();
  const note = document.createElement("div");
  note.dataset.pinRole = "note";
  Object.assign(note.style, {
    position: "fixed",
    top: "0",
    left: "0",
    width: "max-content",
    maxWidth: "260px",
    maxHeight: "140px",
    boxSizing: "border-box",
    overflow: "hidden",
    padding: "8px 12px",
    border: `0.5px solid ${palette.border}`,
    borderRadius: "14px",
    background: palette.surface,
    color: palette.text,
    boxShadow: palette.shadow,
    fontFamily: dot.style.fontFamily,
    fontSize: "12px",
    lineHeight: "1.5",
    whiteSpace: "pre-wrap",
    overflowWrap: "anywhere",
    pointerEvents: "none",
    display: "none"
  });
  const del = document.createElement("button");
  del.dataset.pinRole = "delete";
  del.type = "button";
  Object.assign(del.style, {
    position: "absolute",
    top: "-6px",
    right: "-6px",
    width: "16px",
    height: "16px",
    borderRadius: "999px",
    background: palette.surface,
    border: `0.5px solid ${palette.border}`,
    boxShadow: "0 1px 3px rgba(0, 0, 0, 0.16)",
    color: palette.ghostText,
    fontSize: "12px",
    lineHeight: "14px",
    textAlign: "center",
    padding: "0",
    cursor: "pointer",
    userSelect: "none",
    opacity: "0",
    pointerEvents: "none"
  });
  del.textContent = "\xD7";
  const setEmphasis = (emphasized) => {
    if (emphasized) {
      const currentPalette = getPopoverPalette();
      Object.assign(note.style, { background: currentPalette.surface, color: currentPalette.text, borderColor: currentPalette.border, boxShadow: currentPalette.shadow });
      Object.assign(del.style, { background: currentPalette.surface, color: currentPalette.ghostText, borderColor: currentPalette.border });
    }
    outline.style.opacity = emphasized ? "1" : "0";
    del.style.opacity = emphasized ? "1" : "0";
    del.style.pointerEvents = emphasized ? "auto" : "none";
    note.style.display = emphasized && note.textContent ? "block" : "none";
    if (note.style.display !== "none") positionNote(badge, note);
  };
  badge.addEventListener("mouseenter", () => setEmphasis(true));
  badge.addEventListener("mouseleave", () => setEmphasis(badge.contains(document.activeElement)));
  badge.addEventListener("focusin", () => setEmphasis(true));
  badge.addEventListener("focusout", (event) => {
    if (!(event.relatedTarget instanceof Node) || !badge.contains(event.relatedTarget)) setEmphasis(false);
  });
  badge.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      setEmphasis(false);
    }
  });
  dot.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    onClickHandler?.(pin.id);
  });
  del.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    onDeleteHandler?.(pin.id);
  });
  badge.appendChild(dot);
  badge.appendChild(del);
  badge.appendChild(note);
  wrap.appendChild(badge);
  updatePin(wrap, pin);
  return wrap;
}
function ensurePinKeyframes() {
  const STYLE_ID = "__onevium-pin-keyframes";
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = "@keyframes oneviumPinPop { 0% { transform: scale(0.8); opacity: 0; } 100% { transform: scale(1); opacity: 1; } } @media (prefers-reduced-motion: reduce) { #__onevium-pin-overlay button { animation: none !important; transition: none !important; } }";
  document.documentElement.appendChild(style);
}
function cssEscape(s) {
  const native = window.CSS?.escape;
  if (typeof native === "function") return native(s);
  return s.replace(/[^a-zA-Z0-9_-]/g, (c) => `\\${c}`);
}

// src/shared/agent-cursor.ts
var AGENT_CURSOR_PATH = "M5.6 3.4 L19.4 9.2 Q21.2 10 19.4 10.8 L13.7 12.9 Q13.1 13.1 12.9 13.7 L10.8 19.4 Q10 21.2 9.2 19.4 L3.4 5.6 Q2.7 3.9 4.4 3.1 Q5 2.9 5.6 3.4 Z";
var AGENT_CURSOR_BOX = 24;
var AGENT_CURSOR_TIP = { x: 4, y: 3.6 };
var AGENT_CURSOR_APPEAR_MS = 140;
var MIN_TRAVEL_MS = 160;
var MAX_TRAVEL_MS = 480;
function agentCursorTravelMs(from, to) {
  if (!from) return AGENT_CURSOR_APPEAR_MS;
  const distance = Math.hypot(to.x - from.x, to.y - from.y);
  if (distance < 3) return 0;
  const fitts = 90 + 60 * Math.log2(1 + distance / 16);
  return Math.round(Math.min(MAX_TRAVEL_MS, Math.max(MIN_TRAVEL_MS, fitts)));
}
function minimumJerk(t) {
  const u = Math.min(1, Math.max(0, t));
  return u * u * u * (10 - 15 * u + 6 * u * u);
}
function agentCursorPath(from, to, steps) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const distance = Math.hypot(dx, dy) || 1;
  const bow = Math.min(72, distance * 0.14) * (dx >= 0 ? 1 : -1);
  const control = { x: (from.x + to.x) / 2 - dy / distance * bow, y: (from.y + to.y) / 2 + dx / distance * bow };
  const count = Math.max(2, Math.round(steps));
  const points = [];
  for (let index = 0; index <= count; index++) {
    const offset = index / count;
    const s = minimumJerk(offset);
    const a = (1 - s) * (1 - s);
    const b = 2 * (1 - s) * s;
    const c = s * s;
    points.push({ x: a * from.x + b * control.x + c * to.x, y: a * from.y + b * control.y + c * to.y, offset });
  }
  return points;
}

// electron/preview/picker/cursor-overlay.ts
var HOST_ID = "__onevium-cursor-host";
var PRESS_MS = 260;
var PULSE_MS = 420;
var HALO_SIZE = 64;
var HALO_CENTER = { x: 10, y: 10 };
var shadowRoot = null;
var hostEl = null;
var cursorEl = null;
var glyphEl = null;
var haloEl = null;
var visible = false;
var position = null;
var travel = null;
var reducedMotion = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
var place = (point) => `translate(${point.x - AGENT_CURSOR_TIP.x}px, ${point.y - AGENT_CURSOR_TIP.y}px)`;
function ensureMounted() {
  if (shadowRoot && hostEl?.isConnected) return shadowRoot;
  if (hostEl && !hostEl.isConnected) {
    shadowRoot = null;
    hostEl = null;
    cursorEl = null;
    glyphEl = null;
    haloEl = null;
    visible = false;
    position = null;
    travel = null;
  }
  if (shadowRoot) return shadowRoot;
  const host = document.createElement("div");
  host.id = HOST_ID;
  host.setAttribute("aria-hidden", "true");
  Object.assign(host.style, {
    position: "fixed",
    top: "0",
    left: "0",
    width: "0",
    height: "0",
    zIndex: "2147483647",
    pointerEvents: "none"
  });
  shadowRoot = host.attachShadow({ mode: "closed" });
  const style = document.createElement("style");
  style.textContent = `
    :host { all: initial; }
    .cursor {
      position: fixed;
      top: 0;
      left: 0;
      width: ${AGENT_CURSOR_BOX}px;
      height: ${AGENT_CURSOR_BOX}px;
      opacity: 0;
      transition: opacity 140ms ease-out;
    }
    .cursor.visible { opacity: 1; }
    .halo, .pulse {
      position: absolute;
      width: ${HALO_SIZE}px;
      height: ${HALO_SIZE}px;
      border-radius: 50%;
      /* A soft wash of light under the pointer: no ring, no edge. */
      background: radial-gradient(circle, rgb(59 130 246 / 0.26) 0%, rgb(59 130 246 / 0.12) 38%, rgb(59 130 246 / 0) 70%);
    }
    .halo {
      left: ${HALO_CENTER.x - HALO_SIZE / 2}px;
      top: ${HALO_CENTER.y - HALO_SIZE / 2}px;
      opacity: 0.8;
    }
    .pulse {
      position: fixed;
      margin: ${-HALO_SIZE / 2}px 0 0 ${-HALO_SIZE / 2}px;
      opacity: 0;
    }
    .cursor svg {
      position: absolute;
      inset: 0;
      display: block;
      overflow: visible;
      transform-origin: ${AGENT_CURSOR_TIP.x}px ${AGENT_CURSOR_TIP.y}px;
      filter:
        drop-shadow(0 1px 1.5px rgb(0 0 0 / 0.30))
        drop-shadow(0 3px 6px rgb(0 0 0 / 0.16));
    }
  `;
  shadowRoot.appendChild(style);
  const cursor = document.createElement("div");
  cursor.className = "cursor";
  cursor.innerHTML = `
    <div class="halo"></div>
    <svg width="${AGENT_CURSOR_BOX}" height="${AGENT_CURSOR_BOX}" viewBox="0 0 ${AGENT_CURSOR_BOX} ${AGENT_CURSOR_BOX}" fill="none">
      <path d="${AGENT_CURSOR_PATH}" fill="#111111" stroke="white" stroke-width="1.6" stroke-linejoin="round"/>
    </svg>
  `;
  shadowRoot.appendChild(cursor);
  cursorEl = cursor;
  glyphEl = cursor.querySelector("svg");
  haloEl = cursor.querySelector(".halo");
  hostEl = host;
  document.documentElement.appendChild(host);
  return shadowRoot;
}
function currentPosition(cursor) {
  if (!position) return null;
  if (!travel || travel.playState !== "running") return position;
  const matrix = new DOMMatrixReadOnly(getComputedStyle(cursor).transform);
  return { x: matrix.m41 + AGENT_CURSOR_TIP.x, y: matrix.m42 + AGENT_CURSOR_TIP.y };
}
function moveTo(x, y) {
  const root = ensureMounted();
  const cursor = cursorEl ?? root.querySelector(".cursor");
  if (!cursor) return 0;
  const to = { x, y };
  const from = visible ? currentPosition(cursor) : null;
  travel?.cancel();
  travel = null;
  position = to;
  cursor.style.transform = place(to);
  if (!visible) {
    visible = true;
    cursor.classList.add("visible");
    return AGENT_CURSOR_APPEAR_MS;
  }
  if (reducedMotion()) return 0;
  const duration = agentCursorTravelMs(from, to);
  if (!from || duration === 0) return duration;
  const frames = agentCursorPath(from, to, duration / 16).map((point) => ({ transform: place(point), offset: point.offset }));
  const animation = cursor.animate(frames, { duration, easing: "linear" });
  travel = animation;
  const settle = () => {
    if (travel === animation) travel = null;
  };
  animation.addEventListener("finish", settle, { once: true });
  animation.addEventListener("cancel", settle, { once: true });
  return duration;
}
function ripple(x, y) {
  const root = ensureMounted();
  if (reducedMotion()) return;
  const at = cursorEl ? currentPosition(cursorEl) : null;
  if (visible && at && Math.hypot(at.x - x, at.y - y) < 6 && glyphEl && haloEl) {
    glyphEl.animate(
      [{ transform: "scale(1)" }, { transform: "scale(0.84)", offset: 0.35 }, { transform: "scale(1)" }],
      { duration: PRESS_MS, easing: "cubic-bezier(0.3, 0, 0.2, 1)" }
    );
    haloEl.animate(
      [{ transform: "scale(1)", opacity: 0.8 }, { transform: "scale(1.35)", opacity: 1, offset: 0.35 }, { transform: "scale(1)", opacity: 0.8 }],
      { duration: PRESS_MS + 80, easing: "ease-out" }
    );
    return;
  }
  const pulse2 = document.createElement("div");
  pulse2.className = "pulse";
  pulse2.style.left = `${x}px`;
  pulse2.style.top = `${y}px`;
  root.appendChild(pulse2);
  const animation = pulse2.animate(
    [{ transform: "scale(0.6)", opacity: 0 }, { transform: "scale(1)", opacity: 1, offset: 0.3 }, { transform: "scale(1.25)", opacity: 0 }],
    { duration: PULSE_MS, easing: "ease-out" }
  );
  const remove = () => pulse2.remove();
  animation.addEventListener("finish", remove, { once: true });
  setTimeout(remove, PULSE_MS + 100);
}
function setVisible(next) {
  const root = ensureMounted();
  const cursor = cursorEl ?? root.querySelector(".cursor");
  if (!cursor) return;
  visible = next;
  cursor.classList.toggle("visible", next);
  if (!next) {
    travel?.cancel();
    travel = null;
    position = null;
  }
}
function initCursorOverlay() {
  ensureMounted();
}
function debugState() {
  return {
    mounted: shadowRoot !== null,
    hostInDom: !!hostEl && hostEl.isConnected,
    visible,
    transform: cursorEl?.style.transform ?? "",
    position: cursorEl ? currentPosition(cursorEl) : null,
    moving: !!travel && travel.playState === "running",
    viewport: { iw: window.innerWidth, ih: window.innerHeight, sx: window.scrollX, sy: window.scrollY }
  };
}
var cursorOverlayApi = { moveTo, ripple, setVisible, debugState };

// electron/preview/picker/activity-frame.ts
var HOST_ID2 = "__onevium-activity-frame-host";
var FADE_AFTER_MS = 5e3;
var shadowRoot2 = null;
var hostEl2 = null;
var frameEl = null;
var labelEl = null;
var hideTimer = null;
var held = false;
function ensureMounted2() {
  if (shadowRoot2 && hostEl2?.isConnected) return shadowRoot2;
  if (hostEl2 && !hostEl2.isConnected) {
    shadowRoot2 = null;
    hostEl2 = null;
    frameEl = null;
    labelEl = null;
  }
  if (shadowRoot2) return shadowRoot2;
  const host = document.createElement("div");
  host.id = HOST_ID2;
  host.setAttribute("aria-hidden", "true");
  Object.assign(host.style, {
    position: "fixed",
    top: "0",
    left: "0",
    width: "0",
    height: "0",
    zIndex: "2147483646",
    // just under the cursor overlay's 2147483647
    pointerEvents: "none"
  });
  shadowRoot2 = host.attachShadow({ mode: "closed" });
  const style = document.createElement("style");
  style.textContent = `
    :host { all: initial; }
    .frame {
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: 0;
      /* ~300ms settle when the turn ends (and the same fade-in). */
      transition: opacity 300ms ease-out;
      /* Soft inward edge glow ONLY \u2014 no rim line (proposal \xA77.3: "\u4E0D\u8981\u5927\u9762\u79EF
         \u5149\u6C61\u67D3\uFF0C\u53EA\u505A\u8FB9\u7F18\u7EC6\u5149"; user: \u9634\u5F71\u4E0D\u8981\u7EBF\u6761). Two layered inset shadows
         blur inward from the four edges; the negative spread keeps them off
         the center so page content stays clean. Native tint = cyan\u2192indigo,
         controlled saturation. */
      box-shadow:
        inset 0 0 68px -10px rgba(99, 102, 241, 0.50),
        inset 0 0 26px -4px rgba(56, 189, 248, 0.42);
    }
    .frame.active {
      opacity: 1;
      /* Slow, gentle breathe \u2014 "\u7EC6\u6ED1", never dips fully so it reads as steady
         presence rather than a blinking pulse. */
      animation: onevium-activity-breathe 2.8s ease-in-out infinite;
    }
    @keyframes onevium-activity-breathe {
      0%, 100% { opacity: 0.74; }
      50% { opacity: 1; }
    }
    /* Floating "what the agent is doing" pill. Lives in the page for the
       same reason as the frame (OS-level view covers renderer HTML) so it
       costs the panel no layout height; translucent so page content stays
       readable underneath. Text arrives already localized from the renderer. */
    .label {
      position: fixed;
      left: 12px;
      bottom: 12px;
      max-width: calc(100vw - 24px);
      box-sizing: border-box;
      padding: 5px 10px;
      border-radius: 999px;
      background: rgba(24, 24, 27, 0.62);
      color: rgba(255, 255, 255, 0.92);
      font: 500 11px/1.2 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      letter-spacing: 0.01em;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      pointer-events: none;
      opacity: 0;
      transform: translateY(4px);
      transition: opacity 180ms ease-out, transform 180ms ease-out;
      -webkit-backdrop-filter: blur(8px);
      backdrop-filter: blur(8px);
    }
    .label.active { opacity: 1; transform: translateY(0); }
    /* Reduced motion: no breathing and no fades, but the operating state stays
       visible as a steady glow. */
    @media (prefers-reduced-motion: reduce) {
      .frame, .label { transition: none; }
      .frame.active { animation: none; opacity: 0.9; }
    }
  `;
  shadowRoot2.appendChild(style);
  const frame = document.createElement("div");
  frame.className = "frame";
  shadowRoot2.appendChild(frame);
  frameEl = frame;
  const label = document.createElement("div");
  label.className = "label";
  shadowRoot2.appendChild(label);
  labelEl = label;
  hostEl2 = host;
  document.documentElement.appendChild(host);
  return shadowRoot2;
}
function clearHideTimer() {
  if (hideTimer) {
    clearTimeout(hideTimer);
    hideTimer = null;
  }
}
function pulse() {
  ensureMounted2();
  if (!frameEl) return;
  frameEl.classList.add("active");
  clearHideTimer();
  if (held) return;
  hideTimer = setTimeout(() => {
    hideTimer = null;
    if (!held) frameEl?.classList.remove("active");
  }, FADE_AFTER_MS);
}
function hide() {
  clearHideTimer();
  if (!held) frameEl?.classList.remove("active");
  setLabel(null);
}
function setHeld(on) {
  held = on;
  clearHideTimer();
  if (on) {
    ensureMounted2();
    frameEl?.classList.add("active");
  } else {
    frameEl?.classList.remove("active");
  }
}
function setLabel(text) {
  ensureMounted2();
  if (!labelEl) return;
  if (text) {
    labelEl.textContent = text;
    labelEl.classList.add("active");
  } else {
    labelEl.classList.remove("active");
  }
}
function initActivityFrame() {
  ensureMounted2();
}
function debugState2() {
  return {
    mounted: shadowRoot2 !== null,
    hostInDom: !!hostEl2 && hostEl2.isConnected,
    active: !!frameEl && frameEl.classList.contains("active"),
    held,
    label: labelEl?.classList.contains("active") ? labelEl.textContent : null
  };
}
var activityFrameApi = { pulse, hide, setHeld, setLabel, debugState: debugState2 };

// electron/preview/picker/pin-visibility.ts
var PIN_STYLE_ID = "__onevium-annotation-pin-visibility";
function setPinsVisible(visible2) {
  const style = document.getElementById(PIN_STYLE_ID);
  if (visible2) {
    style?.remove();
    return;
  }
  if (style) return;
  const next = document.createElement("style");
  next.id = PIN_STYLE_ID;
  next.textContent = "#__onevium-pin-overlay { visibility:hidden!important; }";
  document.documentElement.appendChild(next);
}

// src/lib/browser/login-field-rules.ts
var USERNAME_INPUT_TYPES = /* @__PURE__ */ new Set(["text", "email", "tel", ""]);
var ONE_TIME_PATTERN = /(^|[^a-z])(otp|totp|mfa|2fa)([^a-z]|$)|one[-_ ]?time|verif(y|ication)|captcha|sms[-_ ]?code|auth[-_ ]?code|security[-_ ]?code|短信|验证码|校验码|动态码|动态口令|图形码|图片码/;
var USERNAME_PATTERN = /user([-_ ]?(name|id|login))?|login[-_ ]?(name|id)?|^log$|account|e[-_ ]?mail|mail[-_ ]?addr|^email$|phone|mobile|msisdn|identifier|signin|用户名|用户账号|账号|帐号|帐户|账户|邮箱|手机号|手机|登录名/;
var USERNAME_NEGATIVE_PATTERN = /search|query|^q$|coupon|promo|invite|referr|address|street|city|zipcode|postal|company|nick|display[-_ ]?name|first[-_ ]?name|last[-_ ]?name|full[-_ ]?name|real[-_ ]?name|^name$|姓名|昵称|地址|搜索|优惠|邀请/;
function tokens(autocomplete) {
  return new Set(autocomplete.split(/\s+/).filter(Boolean));
}
function haystack(d) {
  return `${d.name} ${d.id} ${d.placeholder} ${d.ariaLabel}`;
}
function looksLikeShortCode(d) {
  const numeric = d.inputMode === "numeric" || d.inputMode === "tel" || d.type === "number";
  return numeric && d.maxLength >= 3 && d.maxLength <= 8;
}
function classifyLoginField(d) {
  if (d.disabled || d.readOnly) return null;
  const auto = tokens(d.autocomplete);
  if (auto.has("one-time-code")) return null;
  const text = haystack(d);
  if (d.type === "password") {
    if (auto.has("new-password")) return null;
    if (ONE_TIME_PATTERN.test(text)) return null;
    return "password";
  }
  if (!USERNAME_INPUT_TYPES.has(d.type)) return null;
  if (ONE_TIME_PATTERN.test(text) || looksLikeShortCode(d)) return null;
  if (auto.has("username") || auto.has("email")) return "username";
  if (USERNAME_NEGATIVE_PATTERN.test(text)) return null;
  if (d.type === "email") return "username";
  if (USERNAME_PATTERN.test(text)) return "username";
  if (d.type === "tel") return "username";
  return null;
}

// electron/preview/picker/login-fields.ts
var { ipcRenderer } = require("electron");
var ANCHOR_CHANNEL = "web-preview:login-fill:internal-anchor";
var ACK_CHANNEL = "web-preview:login-fill:internal-ack";
var SETTLE_MS = 300;
var tracked = null;
var suppressed = false;
var openedAt = 0;
var rafPending = 0;
var observedDocuments = /* @__PURE__ */ new WeakSet();
var hookedFrames = /* @__PURE__ */ new WeakSet();
function isVisible(el) {
  const rect = el.getBoundingClientRect();
  if (rect.width < 8 || rect.height < 8) return false;
  const style = el.ownerDocument.defaultView?.getComputedStyle(el);
  if (!style) return false;
  return style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity || "1") > 0.05;
}
function describe(el) {
  const lower = (value) => (value ?? "").toLowerCase();
  return {
    type: lower(el.type),
    name: lower(el.name),
    id: lower(el.id),
    autocomplete: lower(el.getAttribute("autocomplete")),
    placeholder: lower(el.placeholder),
    ariaLabel: lower(el.getAttribute("aria-label")),
    inputMode: lower(el.getAttribute("inputmode")),
    maxLength: el.maxLength,
    readOnly: el.readOnly,
    disabled: el.disabled
  };
}
function asInput(target) {
  const element = target;
  if (!element || typeof element !== "object" || element.tagName !== "INPUT") return null;
  return element;
}
function classify(target) {
  const el = asInput(target);
  if (!el || !isVisible(el)) return null;
  return classifyLoginField(describe(el));
}
function scopeOf(el) {
  return el.form ?? el.ownerDocument;
}
function track(anchor, kind) {
  const pair = { kind, username: null, password: null, anchor };
  pair[kind] = anchor;
  for (const candidate of scopeOf(anchor).querySelectorAll("input")) {
    const role = classify(candidate);
    if (!role || pair[role]) continue;
    pair[role] = candidate;
  }
  return pair;
}
function rectInTopFrame(el) {
  const own = el.getBoundingClientRect();
  if (own.width < 8 || own.height < 8) return null;
  let x = own.left;
  let y = own.top;
  let view = el.ownerDocument.defaultView;
  while (view && view !== window && view.frameElement) {
    const frame = view.frameElement.getBoundingClientRect();
    x += frame.left;
    y += frame.top;
    view = view.parent;
  }
  if (view !== window) return null;
  return { x, y, width: own.width, height: own.height };
}
function close() {
  if (!tracked) return;
  tracked = null;
  ipcRenderer.send(ANCHOR_CHANNEL, null);
}
function report(pair) {
  const rect = rectInTopFrame(pair.anchor);
  if (!rect) {
    close();
    return;
  }
  tracked = pair;
  ipcRenderer.send(ANCHOR_CHANNEL, {
    kind: pair.kind,
    rect,
    origin: pair.anchor.ownerDocument.defaultView?.location.origin ?? window.location.origin,
    hasUsername: !!pair.username,
    hasPassword: !!pair.password
  });
}
function offer(target, closeOnMiss) {
  if (suppressed) return;
  const el = asInput(target);
  if (!el) return;
  const kind = classify(el);
  if (!kind) {
    if (closeOnMiss) close();
    return;
  }
  openedAt = Date.now();
  report(track(el, kind));
}
function onFocus(event) {
  offer(event.target, true);
}
function onClick(event) {
  offer(event.target, false);
}
function onKeyDown(event) {
  if (!tracked || event.target !== tracked.anchor) return;
  const key = event.key;
  if (key.length === 1 || key === "Backspace" || key === "Delete") close();
}
function reanchor() {
  rafPending = 0;
  if (!tracked) return;
  const rect = rectInTopFrame(tracked.anchor);
  if (rect && tracked.anchor.isConnected && rect.y + rect.height >= 0 && rect.y <= window.innerHeight) {
    report(tracked);
    return;
  }
  if (Date.now() - openedAt < SETTLE_MS) {
    rafPending = requestAnimationFrame(reanchor);
    return;
  }
  close();
}
function onViewportChange() {
  if (!tracked || rafPending) return;
  rafPending = requestAnimationFrame(reanchor);
}
function observe(doc) {
  if (observedDocuments.has(doc)) return;
  observedDocuments.add(doc);
  doc.addEventListener("focusin", onFocus, true);
  doc.addEventListener("focusout", onFocusOut, true);
  doc.addEventListener("click", onClick, true);
  doc.addEventListener("keydown", onKeyDown, true);
  doc.addEventListener("scroll", onViewportChange, { capture: true, passive: true });
}
function onFocusOut() {
  if (!tracked) return;
  setTimeout(() => {
    if (!tracked) return;
    if (tracked.anchor.ownerDocument.activeElement !== tracked.anchor) close();
  }, 0);
}
function observeFrames(root) {
  for (const frame of root.querySelectorAll("iframe")) {
    if (!hookedFrames.has(frame)) {
      hookedFrames.add(frame);
      frame.addEventListener("load", () => observeFrames(root));
    }
    try {
      const doc = frame.contentDocument;
      if (!doc) continue;
      observe(doc);
      observeFrames(doc);
    } catch {
    }
  }
}
function focusField(kind) {
  const el = tracked?.[kind];
  if (!el || !el.isConnected || el.disabled || el.readOnly) return false;
  el.focus({ preventScroll: true });
  try {
    el.select();
  } catch {
  }
  return el.ownerDocument.activeElement === el;
}
function settleField(kind) {
  const el = tracked?.[kind];
  if (!el || !el.isConnected) return { ok: false, filled: false };
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  return { ok: true, filled: el.value.length > 0 };
}
function handleRequest(action, payload) {
  const requestId = typeof payload?.requestId === "string" ? payload.requestId : null;
  const kind = payload?.kind === "username" || payload?.kind === "password" ? payload.kind : null;
  if (!requestId) return;
  if (!kind) {
    ipcRenderer.send(ACK_CHANNEL, { requestId, ok: false, filled: false });
    return;
  }
  const result = action === "focus" ? { ok: focusField(kind), filled: false } : settleField(kind);
  ipcRenderer.send(ACK_CHANNEL, { requestId, ...result });
}
function initLoginFields() {
  if (window.top !== window) return;
  observe(document);
  observeFrames(document);
  const observer = new MutationObserver(() => observeFrames(document));
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener("resize", onViewportChange, { passive: true });
  window.addEventListener("beforeunload", close);
  window.addEventListener("pagehide", close);
  ipcRenderer.on("web-preview:login-fill:focus", (_event, payload) => handleRequest("focus", payload));
  ipcRenderer.on("web-preview:login-fill:settle", (_event, payload) => handleRequest("settle", payload));
  ipcRenderer.on("web-preview:login-fill:dismiss", () => close());
}
function setLoginFillSuppressed(value) {
  suppressed = value;
  if (value) close();
}

// electron/preview/picker/pan-gesture.ts
var PAN_ECHO_MS = 250;
var PAN_GESTURE_GAP_MS = 150;
var PAN_SLIDE_SLOP_PX = 10;
var PAN_SLIDE_RATIO = 2;
var PASS = { hold: false, x: 0, y: 0 };
var HOLD = { hold: true, x: 0, y: 0 };
var clampedDelta = (from, delta, max) => Math.max(0, Math.min(max, from + delta)) - from;
function scroll(range, dy, cancelable) {
  const y = cancelable ? clampedDelta(range.y, dy, range.maxY) : 0;
  return y ? { hold: true, x: 0, y } : PASS;
}
function createPanGesture() {
  let intent = "unknown";
  let lastAt = Number.NEGATIVE_INFINITY;
  let lastCancelable = true;
  let travelX = 0;
  let travelY = 0;
  const scrollFrom = (range, dy, cancelable) => {
    intent = "scroll";
    return scroll(range, dy, cancelable);
  };
  return {
    wheel({ dx, dy, at, cancelable }, range) {
      if (at - lastAt > PAN_GESTURE_GAP_MS || cancelable && !lastCancelable) {
        intent = "unknown";
        travelX = 0;
        travelY = 0;
      }
      lastAt = at;
      lastCancelable = cancelable;
      if (range.maxX <= 0 || intent === "scroll") return scroll(range, dy, cancelable);
      if (!dx && !dy) return intent === "unknown" ? PASS : HOLD;
      if (intent === "slide") {
        if (Math.abs(dy) > Math.abs(dx)) {
          travelX += dx;
          travelY += dy;
        } else {
          travelX = 0;
          travelY = 0;
        }
        if (Math.abs(travelY) >= PAN_SLIDE_SLOP_PX && Math.abs(travelY) >= PAN_SLIDE_RATIO * Math.abs(travelX)) {
          return scrollFrom(range, dy, cancelable);
        }
        return { hold: true, x: clampedDelta(range.x, dx, range.maxX), y: 0 };
      }
      if (intent === "unknown") {
        if (!cancelable || Math.abs(dy) >= PAN_SLIDE_RATIO * Math.abs(dx)) return scrollFrom(range, dy, cancelable);
        intent = "judging";
      }
      travelX += dx;
      travelY += dy;
      if (cancelable && Math.hypot(travelX, travelY) < PAN_SLIDE_SLOP_PX) return HOLD;
      if (!cancelable || Math.abs(travelX) < PAN_SLIDE_RATIO * Math.abs(travelY) || !clampedDelta(range.x, travelX, range.maxX)) {
        return scrollFrom(range, dy, cancelable);
      }
      intent = "slide";
      travelX = 0;
      travelY = 0;
      return { hold: true, x: clampedDelta(range.x, dx, range.maxX), y: 0 };
    }
  };
}
function createPanInput(send, now = () => performance.now()) {
  const gesture = createPanGesture();
  const carry = { x: 0, y: 0 };
  let range = { x: 0, y: 0, maxX: 0, maxY: 0 };
  let lastPanAt = Number.NEGATIVE_INFINITY;
  const wholePixels = (axis, delta, position2, max) => {
    const whole = Math.max(-position2, Math.min(max - position2, Math.round(carry[axis] + delta)));
    carry[axis] += delta - whole;
    return whole;
  };
  return {
    project(next) {
      range = now() - lastPanAt >= PAN_ECHO_MS ? next : { ...next, x: Math.min(range.x, next.maxX), y: Math.min(range.y, next.maxY) };
    },
    /** Pans for one wheel event; returns whether the page must not scroll it. */
    wheel(event, page) {
      const pixels = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? page.innerHeight : 1;
      const unit = pixels * (range.displayScale ? page.devicePixelRatio / range.displayScale : 1) * (range.presentationScale ?? 1);
      const sideways = event.shiftKey && !event.deltaX;
      const step = gesture.wheel({
        dx: (sideways ? event.deltaY : event.deltaX) * unit,
        dy: (sideways ? 0 : event.deltaY) * unit,
        at: event.timeStamp,
        cancelable: event.cancelable
      }, range);
      if (step.x || step.y) {
        const deltaX = wholePixels("x", step.x, range.x, range.maxX);
        const deltaY = wholePixels("y", step.y, range.y, range.maxY);
        if (deltaX || deltaY) {
          send({ deltaX, deltaY });
          range = { ...range, x: range.x + deltaX, y: range.y + deltaY };
          lastPanAt = now();
        }
      }
      return step.hold;
    }
  };
}

// electron/preview/picker/index.ts
var { ipcRenderer: ipcRenderer2, contextBridge } = require("electron");
var handler = new GestureHandler({
  onElementPicked: (payload) => {
    ipcRenderer2.send("web-preview:picker:internal-element-picked", payload);
  },
  onRegionPicked: (payload) => {
    ipcRenderer2.send("web-preview:picker:internal-region-picked", payload);
  },
  onCancelled: () => {
    ipcRenderer2.send("web-preview:picker:internal-cancelled", {});
  }
});
ipcRenderer2.on("web-preview:picker:sync-dock", (_event, state) => setPinsVisible(state.pinsVisible));
setPinHandlers({
  onClick: (pinId) => {
    ipcRenderer2.send("web-preview:picker:internal-pin-click", { pinId });
  },
  onDelete: (pinId) => {
    ipcRenderer2.send("web-preview:picker:internal-pin-delete", { pinId });
  }
});
ipcRenderer2.on("web-preview:picker:sync-pins", (_event, pins, locale) => {
  if (locale) setPickerLocale(locale);
  if (Array.isArray(pins)) syncPins(pins);
});
ipcRenderer2.on(
  "web-preview:picker:edit-pin",
  async (_event, payload) => {
    const result = await showCommentPopover({ rect: payload.rect, initial: payload.initial });
    ipcRenderer2.send("web-preview:picker:internal-pin-edit-result", {
      pinId: payload.pinId,
      comment: result ? result.comment : null
    });
  }
);
function setPickerActive(active, locale) {
  if (locale) setPickerLocale(locale);
  handler.setActive(active);
  setLoginFillSuppressed(active);
}
try {
  contextBridge.exposeInMainWorld("__oneviumPicker", {
    setActive: setPickerActive
  });
  contextBridge.exposeInMainWorld(
    "__oneviumInjectBadges",
    (badges) => {
      injectBadges(badges);
    }
  );
  contextBridge.exposeInMainWorld("__oneviumRemoveBadges", () => removeBadges());
  contextBridge.exposeInMainWorld("__oneviumCursor", cursorOverlayApi);
  contextBridge.exposeInMainWorld("__oneviumActivityFrame", activityFrameApi);
} catch {
  window.__oneviumPicker = { setActive: setPickerActive };
  window.__oneviumInjectBadges = injectBadges;
  window.__oneviumRemoveBadges = removeBadges;
  window.__oneviumCursor = cursorOverlayApi;
  window.__oneviumActivityFrame = activityFrameApi;
}
function initializeOverlays() {
  const overlays = [
    ["cursor", initCursorOverlay],
    ["activity frame", initActivityFrame],
    ["login fields", initLoginFields]
  ];
  for (const [name, init] of overlays) {
    try {
      init();
    } catch (error) {
      console.warn(`[picker] ${name} overlay failed to initialize:`, error);
    }
  }
}
if (document.documentElement) initializeOverlays();
else document.addEventListener("DOMContentLoaded", initializeOverlays, { once: true });
var lastNavigationAt = Date.now();
window.addEventListener("beforeunload", () => {
  setPickerActive(false);
  dismissPopover();
  clearPins();
  setPinsVisible(true);
});
document.addEventListener("readystatechange", () => {
  if (document.readyState !== "complete") return;
  const now = Date.now();
  if (now - lastNavigationAt < 4e3 && lastNavigationAt > 0) {
    ipcRenderer2.send("web-preview:picker:internal-hot-reload", {});
  }
  lastNavigationAt = now;
});
var panInput = createPanInput((delta) => ipcRenderer2.send("web-preview:internal-pan", delta));
ipcRenderer2.on("web-preview:pan-range", (_event, range) => panInput.project(range));
window.addEventListener("wheel", (event) => {
  if (event.ctrlKey || window.top !== window) return;
  if (panInput.wheel(event, window) && event.cancelable) event.preventDefault();
}, { passive: false, capture: true });
