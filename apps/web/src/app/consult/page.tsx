"use client";

import type { RequirementMatchCandidate } from "@platform/shared-types";
import { Sparkles } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Suspense,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
} from "react";

import { FollowUpChips } from "@/components/consult/FollowUpChips";
import { RecommendationCard } from "@/components/consult/RecommendationCard";
import { RequirementCard } from "@/components/consult/RequirementCard";
import { ThinkingIndicator } from "@/components/consult/ThinkingIndicator";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/cn";
import { autoGrowTextarea, COMPOSER_CONTAINER_CLASSNAME, COMPOSER_TEXTAREA_CLASSNAME, isComposerSubmitKey } from "@/lib/composer";
import { listCategories, listCategorySpecifications } from "@/lib/products";
import {
  applyClarifyingAnswer,
  computeConfidence,
  extractFromText,
  extractTechnicalCriteria,
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
  | "thinking"
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
const GREETING_TEXT = "Tell me what your business needs — I'll help you find the right company.";
// ForgeX Product Audit P1 #1: a brief, deliberate pause before ForgeX's
// first reply to a homepage handoff — long enough to read as "thinking
// about what you just said" (Phase 3A Section 13's own "no distinction
// between loading data and generating a response — both are ForgeX
// working"), short enough to never feel like a stall. Well under every
// test file's default `waitFor` budget in this repo.
const HANDOFF_THINKING_DELAY_MS = 450;

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

// P0 #1 (Buyer UX Audit): a logged-out buyer can complete the whole
// clarify -> summary flow and only discover login is required at
// "Search now" (the auth boundary documented at the top of this file).
// Without this, the redirect to /login and back unmounts ConsultForm
// and every bit of state above is gone, forcing a retype. sessionStorage
// (tab-scoped, cleared on read) survives that round trip without
// persisting requirement text any longer than the login detour itself.
const PENDING_SEARCH_KEY = "forgex:consult:pending-search";

interface PendingSearch {
  requirement: RequirementObject;
  messages: Message[];
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
  // ForgeX Product Audit P1 #1: a buyer arriving with `?q=` already told
  // ForgeX what they need on the homepage — showing the generic "Tell me
  // what your business needs" greeting *after* echoing their own message
  // back reads as if ForgeX didn't hear them, and showing all of it at
  // once (greeting + their message + the next question) in the same
  // instant is exactly the "pre-written conversation" feeling the audit
  // flagged. So: with a handoff, the first thing ever rendered is their
  // own message (preserved verbatim, already sent — no reason to delay
  // it) and nothing else; the greeting only exists for a cold, no-`?q=`
  // visit. The real first reply is added by the effect below, after a
  // brief "thinking" pause.
  const initialQueryRef = useRef(searchParams.get("q")?.trim() || null);
  const [messages, setMessages] = useState<Message[]>(() =>
    initialQueryRef.current
      ? [{ id: nextId(), role: "user", text: initialQueryRef.current }]
      : [{ id: nextId(), role: "assistant", text: GREETING_TEXT }]
  );
  const [phase, setPhase] = useState<Phase>(() => (initialQueryRef.current ? "thinking" : "greeting"));
  const [requirement, setRequirement] = useState<RequirementObject | null>(null);
  const [pendingField, setPendingField] = useState<ClarifyField | null>(null);
  const [questionsAsked, setQuestionsAsked] = useState(0);
  const [inputValue, setInputValue] = useState("");
  const [matches, setMatches] = useState<RequirementMatchCandidate[] | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const ranInitialQuery = useRef(false);

  useEffect(() => {
    const initialQuery = initialQueryRef.current;
    if (!initialQuery) return;
    // The guard lives *inside* the timer callback, not around the
    // scheduling itself — React 18 StrictMode double-invokes effects in
    // development (mount, cleanup, mount again on the same instance).
    // Guarding the scheduling would let StrictMode's synchronous
    // cleanup (clearTimeout) cancel the first timer and then the guard
    // block the second mount from ever scheduling a replacement,
    // leaving the "thinking" indicator spinning forever. Guarding the
    // callback instead lets both timers be scheduled (harmless — the
    // first is always cancelled by the real cleanup below) while still
    // guaranteeing handleFirstMessage runs exactly once.
    const timer = setTimeout(() => {
      if (ranInitialQuery.current) return;
      ranInitialQuery.current = true;
      handleFirstMessage(initialQuery);
    }, HANDOFF_THINKING_DELAY_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once on mount only, by design (see the ref guard above)
  }, []);

  const restoredPendingSearch = useRef(false);

  useEffect(() => {
    // Mirrors the `?q=` effect's ref-guard reasoning above. Only fires
    // once auth.status resolves to "authenticated" — i.e. right after the
    // buyer returns from the /login detour this same conversation
    // triggered (see handleSearch's auth_required branch) — so a plain
    // unauthenticated visit never touches this, and it never fires twice
    // under StrictMode's double-invoke.
    if (restoredPendingSearch.current) return;
    if (auth.status !== "authenticated") return;
    restoredPendingSearch.current = true;

    let raw: string | null = null;
    try {
      raw = sessionStorage.getItem(PENDING_SEARCH_KEY);
      if (raw) sessionStorage.removeItem(PENDING_SEARCH_KEY);
    } catch {
      raw = null;
    }
    if (!raw) return;

    try {
      const pending = JSON.parse(raw) as PendingSearch;
      // Fresh ids so they can't collide with nextId()'s own counter,
      // which restarts at 0 on this new page load.
      setMessages(pending.messages.map((m) => ({ ...m, id: nextId() })));
      setRequirement(pending.requirement);
      setPhase("summary");
      scrollToBottom();
    } catch {
      // Corrupt/unexpected stored value — ignore, buyer just sees the
      // ordinary empty greeting instead of a crash.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- ref-guarded, same reasoning as the ?q= effect above
  }, [auth.status]);

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

    // ForgeX Product Audit P0: auth.status/auth.accessToken here are this
    // render's closure — if the AuthContext bootstrap (POST
    // /api/auth/refresh, fired on every fresh mount) hadn't settled yet
    // when the buyer answered the last clarifying question, this used to
    // read a stale "loading"/null and send a genuinely logged-in buyer
    // into the "please log in" branch right after they'd just answered
    // every question. resolveAuth() waits for the real, settled outcome
    // instead of trusting this closure.
    const resolved = await auth.resolveAuth();
    if (resolved.status !== "authenticated" || !resolved.accessToken) {
      try {
        const pending: PendingSearch = { requirement, messages };
        sessionStorage.setItem(PENDING_SEARCH_KEY, JSON.stringify(pending));
      } catch {
        // Storage unavailable (private browsing, quota) — the buyer falls
        // back to retyping after login, same as before this fix.
      }
      setPhase("auth_required");
      return;
    }
    const accessToken = resolved.accessToken;

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

      // Technical criteria (Motor Power / Flow Rate / Head — see
      // lib/requirement.ts's extractTechnicalCriteria) need the
      // category's REAL specifications, only knowable once a category
      // has actually resolved; no category means no criteria, never a
      // guess. A specs-fetch failure fails open to no criteria too —
      // the search itself still proceeds on trust/location/certification
      // signals alone, exactly as it always has.
      let technicalCriteria: ReturnType<typeof extractTechnicalCriteria> = [];
      if (productCategoryId) {
        const specsResult = await listCategorySpecifications(productCategoryId);
        if (specsResult.success) {
          technicalCriteria = extractTechnicalCriteria(requirement.rawQuery, specsResult.data);
        }
      }
      setRequirement((prev) => (prev ? { ...prev, technicalCriteria } : prev));

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
          criteria: technicalCriteria,
        },
        accessToken
      );
      if (!created.success) {
        setPhase("error");
        addMessage({ role: "assistant", text: "Something went wrong on my end — let's try that again." });
        return;
      }

      const matchesResult = await getRequirementMatches(created.data.id, accessToken);
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
    setMessages([{ id: nextId(), role: "assistant", text: GREETING_TEXT }]);
    setPhase("greeting");
    setRequirement(null);
    setPendingField(null);
    setQuestionsAsked(0);
    setMatches(null);
  }

  function handleComposerKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (isComposerSubmitKey(e)) {
      e.preventDefault();
      handleSubmit(e as unknown as FormEvent);
    }
  }

  // "thinking"/"searching" keep the composer visible-but-disabled rather
  // than removing it — Phase 3A Section 13's own interaction-states table
  // treats "loading" and "generating a response" identically ("both are
  // ForgeX working"), and a composer that vanishes and reappears between
  // every turn is exactly the kind of layout jump this P1 is fixing.
  const showInput =
    phase === "greeting" || phase === "clarifying" || phase === "thinking" || phase === "searching";
  const inputDisabled = phase === "thinking" || phase === "searching";

  useLayoutEffect(() => {
    if (inputRef.current) autoGrowTextarea(inputRef.current);
  }, [inputValue]);

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
            <div key={msg.id} className="animate-slide-up">
              {msg.role === "assistant" ? (
                <div className="flex items-start gap-2.5">
                  <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-subtle text-accent">
                    <Sparkles size={13} aria-hidden />
                  </div>
                  <div className="max-w-md rounded-2xl rounded-tl-sm border border-border bg-surface px-4 py-2.5">
                    <p className="whitespace-pre-wrap text-sm text-ink">{msg.text}</p>
                  </div>
                </div>
              ) : (
                <div className="flex justify-end">
                  <p className="max-w-md whitespace-pre-wrap rounded-2xl rounded-br-sm bg-accent px-4 py-2.5 text-sm text-white">
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

          {(phase === "searching" || phase === "thinking") && (
            <div className="animate-fade-in">
              <ThinkingIndicator />
            </div>
          )}

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
          <div className={cn(COMPOSER_CONTAINER_CLASSNAME, "mx-auto max-w-2xl")}>
            <textarea
              ref={inputRef}
              value={inputValue}
              onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setInputValue(e.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder={phase === "greeting" ? "e.g. Need CNC machining in India" : "Type your answer…"}
              aria-label="Your message"
              rows={1}
              disabled={inputDisabled}
              className={COMPOSER_TEXTAREA_CLASSNAME}
            />
            <button
              type="submit"
              disabled={inputValue.trim().length === 0 || inputDisabled}
              className="mb-0.5 shrink-0 rounded-full bg-accent px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
            >
              Send
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
