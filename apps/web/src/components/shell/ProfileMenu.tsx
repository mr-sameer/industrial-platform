"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown, LogOut, Monitor, User as UserIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Avatar } from "@/components/ui/Avatar";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/cn";

/** Real user data + real logout — no placeholder content. */
export function ProfileMenu() {
  const auth = useAuth();
  const router = useRouter();

  if (!auth.user) return null;

  async function handleLogout() {
    await auth.logout();
    router.push("/login");
  }

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          className={cn(
            "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-ink-inverse-muted",
            "hover:bg-sidebar-hover hover:text-ink-inverse transition-colors"
          )}
          aria-label="Account menu"
        >
          <Avatar name={auth.user.full_name} size="sm" />
          <span className="hidden max-w-[10rem] truncate lg:inline">{auth.user.full_name}</span>
          <ChevronDown size={14} aria-hidden />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={8}
          className={cn(
            "z-50 w-64 rounded-lg border border-border bg-canvas p-1.5 shadow-popover",
            "animate-scale-in origin-top-right"
          )}
        >
          <div className="px-2.5 py-2">
            <p className="truncate text-sm font-medium text-ink">{auth.user.full_name}</p>
            <p className="truncate text-xs text-ink-muted">{auth.user.email}</p>
          </div>
          <DropdownMenu.Separator className="my-1 h-px bg-border" />
          <DropdownMenu.Item asChild>
            <Link
              href="/dashboard"
              className="flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-sm text-ink outline-none hover:bg-surface data-[highlighted]:bg-surface"
            >
              <UserIcon size={16} aria-hidden /> Dashboard
            </Link>
          </DropdownMenu.Item>
          <DropdownMenu.Item asChild>
            <Link
              href="/account/sessions"
              className="flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-sm text-ink outline-none hover:bg-surface data-[highlighted]:bg-surface"
            >
              <Monitor size={16} aria-hidden /> Active sessions
            </Link>
          </DropdownMenu.Item>
          <DropdownMenu.Separator className="my-1 h-px bg-border" />
          <DropdownMenu.Item
            onSelect={handleLogout}
            className="flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-sm text-danger outline-none hover:bg-danger-subtle data-[highlighted]:bg-danger-subtle"
          >
            <LogOut size={16} aria-hidden /> Log out
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
