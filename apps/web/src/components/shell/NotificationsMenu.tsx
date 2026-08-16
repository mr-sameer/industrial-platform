"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Bell } from "lucide-react";

import { cn } from "@/lib/cn";

/**
 * No notifications backend exists yet (checked: no endpoint in
 * docs/architecture/openapi.json) — see missing-api.md. This renders a
 * real, honest empty state rather than fabricated notification data,
 * per this sprint's "no mocked business data" rule. The UI shell exists
 * now so wiring a real feed later is additive.
 */
export function NotificationsMenu({ variant = "dark" }: { variant?: "dark" | "light" }) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          className={cn(
            "relative flex h-9 w-9 items-center justify-center rounded-md transition-colors",
            variant === "dark"
              ? "text-ink-inverse-muted hover:bg-sidebar-hover hover:text-ink-inverse"
              : "text-ink-muted hover:bg-surface hover:text-ink"
          )}
          aria-label="Notifications"
        >
          <Bell size={18} aria-hidden />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={8}
          className={cn(
            "z-50 w-80 rounded-lg border border-border bg-canvas p-1.5 shadow-popover",
            "animate-scale-in origin-top-right"
          )}
        >
          <div className="border-b border-border px-2.5 py-2.5">
            <p className="text-sm font-semibold text-ink">Notifications</p>
          </div>
          <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
            <Bell size={22} className="text-ink-faint" aria-hidden />
            <p className="text-sm text-ink-muted">You&apos;re all caught up.</p>
            <p className="text-xs text-ink-faint">
              Notifications for verification updates, member activity, and messages will appear here.
            </p>
          </div>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
