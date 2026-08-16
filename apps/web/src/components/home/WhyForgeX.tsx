import { MessageSquareText, ShieldCheck, Sparkles } from "lucide-react";

/**
 * Three sharp differentiators — not a longer list padded to fill
 * space. Each one earns its place: what makes ForgeX different (AI),
 * why it's trustworthy (verification), how it works (conversation).
 */
const REASONS = [
  {
    icon: MessageSquareText,
    title: "Ask, don't browse",
    desc: "Describe what you need in plain language. No filters, no endless directories.",
  },
  {
    icon: ShieldCheck,
    title: "Real verification",
    desc: "Companies are evidence-based verified — not self-reported badges.",
  },
  {
    icon: Sparkles,
    title: "Built for what's next",
    desc: "An AI-native platform from day one, not a search box bolted onto a directory.",
  },
];

export function WhyForgeX() {
  return (
    <section className="border-t border-border bg-canvas px-4 py-20 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-3xl">
        <div className="grid grid-cols-1 gap-10 sm:grid-cols-3">
          {REASONS.map((reason) => {
            const Icon = reason.icon;
            return (
              <div key={reason.title} className="text-center">
                <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-accent-subtle text-accent">
                  <Icon size={20} aria-hidden />
                </div>
                <h3 className="mt-3 text-sm font-semibold text-ink">{reason.title}</h3>
                <p className="mt-1.5 text-sm text-ink-muted">{reason.desc}</p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
