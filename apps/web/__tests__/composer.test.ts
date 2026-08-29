import { describe, expect, it, vi } from "vitest";

import { autoGrowTextarea, isComposerSubmitKey } from "@/lib/composer";

/**
 * Unit coverage for the ForgeX Product Audit P1 #1 shared composer
 * behavior: Enter sends, Shift+Enter inserts a real newline, an IME
 * composition's Enter is never mistaken for a submit, and a textarea
 * grows with its content up to a capped number of rows instead of
 * scrolling a single cramped line.
 */

function keyboardEvent(overrides: Partial<{ key: string; shiftKey: boolean; isComposing: boolean }>) {
  return {
    key: overrides.key ?? "Enter",
    shiftKey: overrides.shiftKey ?? false,
    nativeEvent: { isComposing: overrides.isComposing ?? false },
  } as unknown as React.KeyboardEvent<HTMLTextAreaElement>;
}

describe("isComposerSubmitKey", () => {
  it("treats a plain Enter as submit", () => {
    expect(isComposerSubmitKey(keyboardEvent({ key: "Enter" }))).toBe(true);
  });

  it("treats Shift+Enter as a newline, not a submit", () => {
    expect(isComposerSubmitKey(keyboardEvent({ key: "Enter", shiftKey: true }))).toBe(false);
  });

  it("never treats Enter during an IME composition as a submit", () => {
    expect(isComposerSubmitKey(keyboardEvent({ key: "Enter", isComposing: true }))).toBe(false);
  });

  it("ignores every other key", () => {
    expect(isComposerSubmitKey(keyboardEvent({ key: "a" }))).toBe(false);
  });
});

describe("autoGrowTextarea", () => {
  function makeTextarea({ scrollHeight, lineHeight = "24px" }: { scrollHeight: number; lineHeight?: string }) {
    const el = document.createElement("textarea");
    document.body.appendChild(el);
    Object.defineProperty(el, "scrollHeight", { configurable: true, value: scrollHeight });
    vi.spyOn(window, "getComputedStyle").mockReturnValue({
      lineHeight,
      paddingTop: "0px",
      paddingBottom: "0px",
    } as CSSStyleDeclaration);
    return el;
  }

  it("grows to fit content shorter than the row cap", () => {
    const el = makeTextarea({ scrollHeight: 48 }); // two lines of 24px
    autoGrowTextarea(el, 6);
    expect(el.style.height).toBe("48px");
    expect(el.style.overflowY).toBe("hidden");
  });

  it("caps growth at maxRows and switches to internal scrolling beyond it", () => {
    const el = makeTextarea({ scrollHeight: 24 * 20 }); // a very long requirement
    autoGrowTextarea(el, 6);
    expect(el.style.height).toBe("144px"); // 6 * 24px, not the full 480px
    expect(el.style.overflowY).toBe("auto");
  });

  it("never shrinks below a single row", () => {
    const el = makeTextarea({ scrollHeight: 0 });
    autoGrowTextarea(el, 6);
    expect(el.style.height).toBe("24px");
  });
});
