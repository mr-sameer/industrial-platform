"use client";

import type { RequirementMatchCandidate } from "@platform/shared-types";
import { Sparkles } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { FollowUpChips } from "@/components/consult/FollowUpChips";
import { RecommendationCard } from "@/components/consult/RecommendationCard";
import { RequirementCard } from "@/components/consult/RequirementCard";
import { ThinkingIndicator } from "@/components/consult/ThinkingIndicator";
import { useAuth } from "@/contexts/AuthContext";
import { listCategories } from "@/lib/products";
import {
  applyClarifyingAnswer,
  computeConfidence,
  extractFromText,
  newRequirementObject,
  nextClarifyingField,
  resolveCategoryId,
  type RequirementObject,
} from "@/lib/requirement";
import { createRequirement, getRequirementMatches } from "@/lib/requirements-api";

/**
 * ForgeX Requirement Intelligence — Phase 3B conversation state machine
 * (docs/product/phase-3a-ai-conversation-architecture.md Section 6),
 * now wired to the real Module 7A-1/7A-2 backend: the conversation's
 * only job is still to build a RequirementObject via deterministic
 * keyword rules (lib/requirement.ts — never an LLM), but "Search now"
 * submits it as a real Requirement (POST /api/v1/requirements) and
 * renders the real, evidence-backed ranked matches
 * (GET /api/v1/requirements/{id}/matches) instead of the old
 * client-only GET /companies/search path. No conversation persistence,
 * no memory, no real LLM, no agents — still explicitly out of scope.
 *
 * Both backend endpoints require an authenticated caller (see
 * app/api/v1/requirements.py's own docstring) — the conversational
 * Q&A itself stays open to anyone; only the actual search step checks
 * auth, matching this codebase's existing useRequireAuth pattern.
 *
 * The homepage's "Ask ForgeX" bar (components/home/AISearchBar.tsx)
 * routes here with `?q=<their text>` rather than duplicating any
 * extraction/matching logic of its own — an initial `q` is treated
 * exactly as if the user had typed and sent that text as this page's
 * first message (see the effect in ConsultForm below), so it goes
 * through the identical clarify → summary → search flow, auth boundary
 * included.
 */

type Phase =
  | "greeting"
  | "clarifying"
  | "summary"
  | "searching"
  | "results"
  | "no_results"
  | "category_required"
  | "auth_required"
  | "error";
type ClarifyField = "intent" | "productOrCategory" | "country" | "certifications";

interface Message {
  id: string;
  role: "assistant" | "user";
  text: string;
  chips?: string[];
}

const QUESTION_CEILING = 4; // Phase 3A Section 3

function questionForField(field: ClarifyField): { text: string; chips?: string[] } {
  switch (field) {
    case "intent":
      return { text: "Who are you looking for?", chips: ["Manufacturer", "Supplier", "Distributor", "Exporter"] };
    case "productOrCategory":
      return { text: "What product or category are you sourcing?" };
    case "country":
      return { text: "Which country?", chips: ["India", "China", "Germany", "Any"] };
    case "certifications":
      return { text: "Any certifications required?", chips: ["ISO", "CE", "BIS", "None"] };
  }
}

let messageIdCounter = 0;
function nextId(): string {
  messageIdCounter += 1;
  return `m${messageIdCounter}`;
}

// useSearchParams() opts a page out of static rendering unless wrapped in
// Suspense — Next.js enforces this at build time (see
// https://nextjs.org/docs/messages/missing-suspense-with-csr-bailout).
// Same pattern as app/(auth)/login/page.tsx: the default export below
// is the Suspense wrapper; ConsultForm holds the actual page content
// and is what reads the `?q=` initial-query param.
export default function ConsultPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center bg-canvas">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-border-strong border-t-accent" />
        </main>
      }
    >
      <ConsultForm />
    </Suspense>
  );
}

function ConsultForm() {
  const auth = useAuth();
  const searchParams = useSearchParams();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: nextId(),
      role: "assistant",
      text: "Tell me what your business needs — I'll help you find the right company.",
    },
  ]);
  const [phase, setPhase] = useState<Phase>("greeting");
  const [requirement, setRequirement] = useState<RequirementObject | null>(null);
  const [pendingField, setPendingField] = useState<ClarifyField | null>(null);
  const [questionsAsked, setQuestionsAsked] = useState(0);
  const [inputValue, setInputValue] = useState("");
  const [matches, setMatches] = useState<RequirementMatchCandidate[] | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const ranInitialQuery = useRef(false);

  useEffect(() => {
    // Guarded the same way AuthContext's own bootstrap effect is
    // (bootstrapped ref, see contexts/AuthContext.tsx) — React 18
    // StrictMode double-invokes effects in development, and without
    // this guard a `?q=` param would seed the opening message twice.
    if (ranInitialQuery.current) return;
    ranInitialQuery.current = true;
    const initialQuery = searchParams.get("q")?.trim();
    if (!initialQuery) return;
    addMessage({ role: "user", text: initialQuery });
    handleFirstMessage(initialQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once on mount only, by design (see the ref guard above)
  }, []);

  function scrollToBottom() {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  }

  function addMessage(msg: Omit<Message, "id">) {
    setMessages((prev) => [...prev, { ...msg, id: nextId() }]);
    scrollToBottom();
  }

  function askNextOrSummarize(req: RequirementObject, questionsSoFar: number) {
    const field = nextClarifyingField(req);
    if (field === null || questionsSoFar >= QUESTION_CEILING) {
      const withConfidence = { ...req, overallConfidence: computeConfidence(req) };
      setRequirement(withConfidence);
      setPhase("summary");
      addMessage({ role: "assistant", text: "Here's what I understood:" });
      return;
    }
    const question = questionForField(field);
    setPendingField(field);
    setRequirement(req);
    setPhase("clarifying");
    addMessage({ role: "assistant", text: question.text, chips: question.chips });
  }

  function handleFirstMessage(text: string) {
    const req = extractFromText(newRequirementObject(text), text, true);
    askNextOrSummarize(req, 0);
  }

  function handleClarifyingAnswer(answerText: string) {
    if (!requirement || !pendingField) return;
    const updated = applyClarifyingAnswer(requirement, pendingField, answerText);
    const asked = questionsAsked + 1;
    setQuestionsAsked(asked);
    askNextOrSummarize(updated, asked);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const text = inputValue.trim();
    if (text.length === 0) return;
    addMessage({ role: "user", text });
    setInputValue("");
    if (phase === "greeting") handleFirstMessage(text);
    else if (phase === "clarifying") handleClarifyingAnswer(text);
  }

  function handleChipClick(value: string) {
    addMessage({ role: "user", text: value });
    if (phase === "clarifying") handleClarifyingAnswer(value);
  }

  async function handleSearch() {
    if (!requirement) return;

    if (auth.status !== "authenticated" || !auth.accessToken) {
      setPhase("auth_required");
      return;
    }

    setPhase("searching");
    addMessage({ role: "assistant", text: "Searching…" });
    try {
      const categoriesResult = await listCategories();
      if (!categoriesResult.success) {
        setPhase("error");
        addMessage({ role: "assistant", text: "Something went wrong on my end — let's try that again." });
        return;
      }
      const productCategoryId = requirement.productOrCategory.value
        ? resolveCategoryId(categoriesResult.data, requirement.productOrCategory.value)
        : null;

      const created = await createRequirement(
        {
          raw_query: requirement.rawQuery,
          product_category_id: productCategoryId,
          country: requirement.country.value,
          city: requirement.city.value,
          certifications: requirement.certifications.value,
          quantity: requirement.quantity.value,
          budget: requirement.budget.value,
          timeline: requirement.timeline.value,
          extraction_confidence: requirement.overallConfidence / 100,
          criteria: [],
        },
        auth.accessToken
      );
      if (!created.success) {
        setPhase("error");
        addMessage({ role: "assistant", text: "Something went wrong on my end — let's try that again." });
        return;
      }

      const matchesResult = await getRequirementMatches(created.data.id, auth.accessToken);
      if (!matchesResult.success) {
        setPhase("error");
        addMessage({ role: "assistant", text: "Something went wrong on my end — let's try that again." });
        return;
      }

      if (matchesResult.data.status === "category_required") {
        setPhase("category_required");
        return;
      }

      setMatches(matchesResult.data.matches);
      setPhase(matchesResult.data.matches.length > 0 ? "results" : "no_results");
    } catch {
      setPhase("error");
      addMessage({ role: "assistant", text: "Something went wrong on my end — let's try that again." });
    }
  }

  function handleStartOver() {
    setMessages([
      {
        id: nextId(),
        role: "assistant",
        text: "Tell me what your business needs — I'll help you find the right company.",
      },
    ]);
    setPhase("greeting");
    setRequirement(null);
    setPendingField(null);
    setQuestionsAsked(0);
    setMatches(null);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSubmit(e as unknown as FormEvent);
    }
  }

  const showInput = phase === "greeting" || phase === "clarifying";

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <header className="sticky top-0 z-40 border-b border-border bg-canvas/90 px-4 py-4 backdrop-blur-sm sm:px-6">
        <div className="mx-auto flex max-w-2xl items-center justify-between">
          <Link href="/" className="font-display text-lg font-semibold tracking-tight text-ink">
            Forge<span className="text-accent">X</span>
          </Link>
          <Link href="/discover" className="text-sm text-ink-muted hover:text-ink">
            Search instead
          </Link>
        </div>
      </header>

      <main className="flex-1 px-4 py-8 sm:px-6">
        <div className="mx-auto flex max-w-2xl flex-col gap-4">
          {messages.map((msg) => (
            <div key={msg.id}>
              {msg.role === "assistant" ? (
                <div className="flex items-start gap-2.5">
                  <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-subtle text-accent">
                    <Sparkles size={13} aria-hidden />
                  </div>
                  <div className="max-w-md rounded-2xl rounded-tl-sm border border-border bg-surface px-4 py-2.5">
                    <p className="text-sm text-ink">{msg.text}</p>
                  </div>
                </div>
              ) : (
                <div className="flex justify-end">
                  <p className="max-w-xs rounded-2xl rounded-br-sm bg-accent px-4 py-2.5 text-sm text-white">
                    {msg.text}
                  </p>
                </div>
              )}
              {msg.chips && msg.id === messages[messages.length - 1]?.id && phase === "clarifying" && (
                <div className="mt-2">
                  <FollowUpChips options={msg.chips} onSelect={handleChipClick} />
                </div>
              )}
            </div>
          ))}

          {phase === "searching" && <ThinkingIndicator />}

          {phase === "summary" && requirement && (
            <div className="ml-9 flex flex-col gap-3">
              <RequirementCard requirement={requirement} />
              <FollowUpChips options={["Search now", "Start over"]} onSelect={(v) => (v === "Search now" ? handleSearch() : handleStartOver())} />
            </div>
          )}

          {phase === "no_results" && (
            <div className="ml-9 flex flex-col gap-2">
              <p className="text-sm text-ink-muted">
                I couldn&apos;t find a company matching those requirements yet — ForgeX is growing daily.
              </p>
              <FollowUpChips options={["Start over"]} onSelect={handleStartOver} />
            </div>
          )}

          {phase === "category_required" && (
            <div className="ml-9 flex flex-col gap-2">
              <p className="text-sm text-ink-muted">
                I don&apos;t recognize &quot;{requirement?.productOrCategory.value}&quot; as a product category
                ForgeX tracks yet, so I can&apos;t search for it. Try a different phrasing, or start over.
              </p>
              <FollowUpChips options={["Start over"]} onSelect={handleStartOver} />
            </div>
          )}

          {phase === "auth_required" && (
            <div className="ml-9 flex flex-col gap-2">
              <p className="text-sm text-ink-muted">
                Log in to search ForgeX&apos;s knowledge graph for matching companies.
              </p>
              <Link
                href={`/login?next=${encodeURIComponent("/consult")}`}
                className="w-fit rounded-full bg-accent px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
              >
                Log in
              </Link>
            </div>
          )}

          {phase === "error" && <FollowUpChips options={["Start over"]} onSelect={handleStartOver} />}

          {phase === "results" && matches && (
            <div className="ml-9 flex flex-col gap-3">
              <p className="text-sm text-ink-muted">{matches.length} companies match your requirement.</p>
              {matches.map((match) => (
                <RecommendationCard key={match.offering_id} match={match} />
              ))}
              <div>
                <FollowUpChips options={["New search"]} onSelect={handleStartOver} />
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </main>

      {showInput && (
        <form onSubmit={handleSubmit} className="sticky bottom-0 border-t border-border bg-canvas px-4 py-4 sm:px-6">
          <div className="mx-auto flex max-w-2xl items-center gap-3 rounded-2xl border border-border-strong bg-canvas px-4 py-3 shadow-popover focus-within:border-accent focus-within:ring-4 focus-within:ring-accent/10">
            <input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={phase === "greeting" ? "e.g. Need CNC machining in India" : "Type your answer…"}
              aria-label="Your message"
              className="flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-faint"
            />
            <button
              type="submit"
              disabled={inputValue.trim().length === 0}
              className="rounded-full bg-accent px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
            >
              Send
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
