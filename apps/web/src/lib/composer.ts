import type { KeyboardEvent } from "react";

/**
 * Shared behavior for every ForgeX text composer — the homepage's "Ask
 * ForgeX" bar and Consult's own message input. ForgeX Product Audit
 * P1 #1: these were two independently-styled single-line inputs that
 * read as two different applications; this file is the one place both
 * now get their growing-textarea sizing and Enter/Shift+Enter/IME
 * submit convention from, so they stay behaviorally identical without
 * forcing the two components (one uncontrolled for burst-input safety,
 * one plain-controlled) into a single risky shared component.
 */

/**
 * Enter sends — the convention every modern AI chat interface uses —
 * Shift+Enter inserts a real newline, and a pending IME composition
 * (accented characters, CJK input) is never intercepted as a submit,
 * since the Enter keystroke there confirms the composition, not the
 * message.
 */
export function isComposerSubmitKey(e: KeyboardEvent<HTMLTextAreaElement>): boolean {
  return e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing;
}

const DEFAULT_MAX_ROWS = 6;

/**
 * Grows a textarea with its content up to `maxRows` lines, then lets it
 * scroll internally — the composer's outer chrome stays a fixed,
 * comfortable size while the actual writing area is never more
 * cramped than what's actually been typed. Pure DOM mutation (no
 * React state), so calling this on every keystroke costs nothing and
 * can't reintroduce the render-loop risk the homepage bar's own
 * onChange handler already guards against.
 */
export function autoGrowTextarea(el: HTMLTextAreaElement, maxRows: number = DEFAULT_MAX_ROWS): void {
  el.style.height = "auto";
  const style = window.getComputedStyle(el);
  const lineHeight = parseFloat(style.lineHeight) || 24;
  const paddingY = parseFloat(style.paddingTop || "0") + parseFloat(style.paddingBottom || "0");
  const maxHeight = lineHeight * maxRows + paddingY;
  const minHeight = lineHeight * 1 + paddingY;
  el.style.height = `${Math.max(Math.min(el.scrollHeight, maxHeight), minHeight)}px`;
  el.style.overflowY = el.scrollHeight > maxHeight ? "auto" : "hidden";
}

/** One shared visual identity for the composer "pill" — same radius, border, shadow, focus ring everywhere it appears. */
export const COMPOSER_CONTAINER_CLASSNAME =
  "flex items-end gap-3 rounded-2xl border border-border-strong bg-canvas px-4 py-3 shadow-popover transition-shadow focus-within:border-accent focus-within:ring-4 focus-within:ring-accent/10";

/** One shared textarea treatment — the actual writing area, sized by autoGrowTextarea above. */
export const COMPOSER_TEXTAREA_CLASSNAME =
  "flex-1 resize-none bg-transparent py-1.5 text-base leading-6 text-ink outline-none placeholder:text-ink-faint disabled:cursor-not-allowed disabled:opacity-60";
