export function FollowUpChips({
  options,
  onSelect,
}: {
  options: string[];
  onSelect: (value: string) => void;
}) {
  return (
    <div className="ml-9 flex flex-wrap gap-2">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => onSelect(option)}
          className="rounded-full border border-border-strong bg-canvas px-3.5 py-1.5 text-sm font-medium text-ink transition-colors hover:border-accent hover:text-accent"
        >
          {option}
        </button>
      ))}
    </div>
  );
}
