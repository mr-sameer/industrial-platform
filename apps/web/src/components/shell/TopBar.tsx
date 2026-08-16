import { Breadcrumbs } from "@/components/shell/Breadcrumbs";
import { CommandSearch } from "@/components/shell/CommandSearch";
import { MobileNav } from "@/components/shell/MobileNav";
import { NotificationsMenu } from "@/components/shell/NotificationsMenu";
import { ProfileMenu } from "@/components/shell/ProfileMenu";

function Brand() {
  return (
    <span className="font-display text-sm font-semibold tracking-tight text-ink-inverse">
      Forge<span className="text-accent">X</span>
    </span>
  );
}

/**
 * Split in two rows on small screens (nav row, then breadcrumb row) so
 * nothing gets cramped — see docs/architecture/design-system.md's
 * responsiveness notes.
 */
export function TopBar() {
  return (
    <header className="border-b border-border bg-canvas">
      <div className="flex h-14 items-center gap-3 border-b border-sidebar-border bg-sidebar px-4 md:hidden">
        <MobileNav brand={<Brand />} />
        <Brand />
        <div className="flex-1" />
        <NotificationsMenu />
        <ProfileMenu />
      </div>
      <div className="hidden h-14 items-center gap-4 px-6 md:flex">
        <Breadcrumbs />
        <div className="flex-1" />
        <CommandSearch />
        <NotificationsMenu variant="light" />
      </div>
      <div className="flex h-11 items-center gap-2 border-t border-border px-4 md:hidden">
        <Breadcrumbs />
      </div>
    </header>
  );
}

export { Brand };
