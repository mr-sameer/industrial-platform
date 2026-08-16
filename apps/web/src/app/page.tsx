import type { Metadata } from "next";

import { AIConversationDemo } from "@/components/home/AIConversationDemo";
import { FeaturedCompanies } from "@/components/home/FeaturedCompanies";
import { Hero } from "@/components/home/Hero";
import { PublicFooter } from "@/components/home/PublicFooter";
import { PublicHeader } from "@/components/home/PublicHeader";
import { WhyForgeX } from "@/components/home/WhyForgeX";

export const metadata: Metadata = {
  title: "ForgeX — AI-Powered Industrial Intelligence Platform",
  description: "Describe what your business needs. ForgeX finds it.",
};

/**
 * Public homepage — "ChatGPT for Industry," not "IndiaMART." Five
 * sections, each earning its place (see the design-study conversation
 * this implements): Hero+Search (what it is, what to do next),
 * Conversation Demo (why it's different — shown, not explained),
 * Trusted Companies (this is real), Why ForgeX (the differentiators,
 * once, crisply). No browsing affordances (categories/trending/quick-
 * access grids), no nav items without a real destination, no anchor
 * links, no placeholder sections. AI Search is the product's only
 * navigation — see PublicHeader and AISearchBar's own comments.
 */
export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <PublicHeader />
      <main className="flex-1">
        <Hero />
        <AIConversationDemo />
        <FeaturedCompanies />
        <WhyForgeX />
      </main>
      <PublicFooter />
    </div>
  );
}
