export function Footer() {
  return (
    <footer className="border-t border-border px-6 py-4 text-xs text-ink-faint">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span>© {new Date().getFullYear()} ForgeX</span>
        <span>Built for verified industrial trade</span>
      </div>
    </footer>
  );
}
