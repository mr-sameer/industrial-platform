import { AISearchBar } from "@/components/home/AISearchBar";

/**
 * One dominant element: the search box. No competing content beside
 * it — no stat badges, no secondary CTAs, no suggestion-chip row.
 * Per product direction: communicate what ForgeX is and what to do
 * next within 5 seconds, with nothing else competing for attention.
 */
export function Hero() {
  return (
    <section className="relative overflow-hidden bg-canvas px-4 pb-24 pt-24 sm:px-6 sm:pt-32 lg:px-8">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.035]"
        style={{
          backgroundImage:
            "linear-gradient(var(--color-ink) 1px, transparent 1px), linear-gradient(90deg, var(--color-ink) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
        }}
      />
      <div className="relative mx-auto max-w-3xl text-center">
        <h1 className="font-display text-4xl font-bold tracking-tight text-ink sm:text-5xl lg:text-6xl">
          Ask ForgeX
        </h1>
        <p className="mx-auto mt-4 max-w-lg text-lg text-ink-muted">
          AI-Powered Industrial Intelligence Platform. Describe what your business needs — ForgeX finds it.
        </p>
        <div className="mt-10">
          <AISearchBar />
        </div>
      </div>
    </section>
  );
}
