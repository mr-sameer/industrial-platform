"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Menu, X } from "lucide-react";
import { useState } from "react";

import { NavLinks } from "@/components/shell/Sidebar";
import { cn } from "@/lib/cn";

/** Mobile/tablet drawer — reuses NavLinks so the link list is never duplicated. */
export function MobileNav({ brand }: { brand: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          className="flex h-9 w-9 items-center justify-center rounded-md text-ink-inverse-muted hover:bg-sidebar-hover hover:text-ink-inverse md:hidden"
          aria-label="Open navigation menu"
        >
          <Menu size={20} aria-hidden />
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink/40 animate-fade-in md:hidden" />
        <Dialog.Content
          className={cn(
            "fixed inset-y-0 left-0 z-50 flex w-72 flex-col bg-sidebar animate-slide-up md:hidden"
          )}
        >
          <Dialog.Title className="sr-only">Navigation menu</Dialog.Title>
          <div className="flex h-14 items-center justify-between border-b border-sidebar-border px-4">
            {brand}
            <Dialog.Close asChild>
              <button
                className="flex h-8 w-8 items-center justify-center rounded-md text-ink-inverse-muted hover:bg-sidebar-hover hover:text-ink-inverse"
                aria-label="Close navigation menu"
              >
                <X size={18} aria-hidden />
              </button>
            </Dialog.Close>
          </div>
          <div className="flex-1 overflow-y-auto py-4" onClick={() => setOpen(false)}>
            <NavLinks />
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
