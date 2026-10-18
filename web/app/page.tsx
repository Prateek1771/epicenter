import type { Metadata } from "next";
import { Almarai } from "next/font/google";
import Link from "next/link";

import { ArrowRight, Github, Menu } from "@/components/icons";
import { HistorianGlyph, InvestigatorGlyph, SkepticGlyph, TriageGlyph } from "@/components/landing/agent-glyphs";
import { CopyLine } from "@/components/landing/copy-line";
import { hasArt, Illustration } from "@/components/landing/illustration";
import { Reveal, W } from "@/components/landing/reveal";
import { ShockwaveCanvas } from "@/components/landing/shockwave-canvas";

/*
 * Landing page. Layout and effects follow the pasted reference (black, cream, gold, Almarai + Instrument Serif italics,
 * grain, background video, glass nav); the content is Epicenter's. The colours are the app's own tokens (globals.css), so
 * the landing and the app are one palette; Instrument Serif is loaded app-wide in layout.tsx (--font-landing-serif).
 */
const sans = Almarai({ subsets: ["latin"], weight: ["300", "400", "700"], variable: "--font-landing-sans" });

export const metadata: Metadata = {
  title: "Epicenter: find where every outage started",
  description:
    "Graph-native root cause analysis on FalkorDB. A Fault Simulator checks every suspect, every answer is a graph path, and the same input always gives the same answer.",
};

const REPO = "https://github.com/Prateek1771/epicenter";
const HERO_VIDEO =
  "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260405_170732_8a9ccda6-5cff-4628-b164-059c500a2b41.mp4";
const serifI = "font-[family-name:var(--font-landing-serif)] italic";

const NAV = [
  ["How it works", "#philosophy"],
  ["Agents", "#agents"],
  ["Simulator", "#what"],
  ["Science", "#science"],
  ["Run it", "#run"],
];

const AGENTS = [
  { name: "Triage", role: "Turns the alert into suspects", text: "Every operation upstream of the alert that misbehaved becomes a hypothesis, bounded at six hops.", file: "triage.py", Glyph: TriageGlyph, art: "agent-triage" },
  { name: "Investigator", role: "Checks each suspect, in parallel", text: "Did it go bad first? Is it slow itself or waiting on a callee? Did something change right before?", file: "investigator.py", Glyph: InvestigatorGlyph, art: "agent-investigator" },
  { name: "Skeptic", role: "Argues with the winner", text: "If the leading suspect doesn't explain the alert's own footprint, it is refuted and the ranking runs again.", file: "skeptic.py", Glyph: SkepticGlyph, art: "agent-skeptic" },
  { name: "Historian", role: "Remembers what fixed it", text: "A 64-dimension incident signature finds similar past incidents and the actions that resolved them.", file: "historian.py", Glyph: HistorianGlyph, art: "agent-historian" },
];

const WHAT = [
  ["Causal search", "Upstream from the alert over the live call graph: onset order, self-time vs. child-time, the change that came just before. Scored deterministically, never by a model."],
  ["The Fault Simulator", "For every suspect: if this were the cause, what would we see? It predicts the footprint, compares it with what broke, and says “explains 6 of 7”."],
  ["Why not X?", "Ask about any service and get the reason it lost: a victim of its callee, went bad too late, not upstream, or simply outscored."],
  ["Memory", "Resolved incidents become knowledge. The next time the same pattern appears, the fix that worked is proposed first, with where it worked."],
];

const SCIENCE = [
  "Operation-level CALLS graph in FalkorDB, one graph per environment",
  "Robust z-scores and PELT change points for anomaly onsets",
  "Drain3 log templates instead of raw log lines",
  "PageRank on a scratch projection of the incident",
  "Deterministic score from six parts, with versioned weights",
  "Propagation rules that predict each fault's footprint",
  "Every AI claim checked against cited evidence (Jev)",
  "Accuracy measured on the public RCAEval benchmark",
];

const STATS = [
  ["9 / 9", "live fault scenarios matched their expected verdict"],
  ["0.7 s", "alert to verdict on the OpenTelemetry Demo"],
  ["110", "graph queries in that run, every one receipted"],
];

export default function Landing() {
  return (
    <div className={`landing ${sans.variable} min-h-screen bg-black font-[family-name:var(--font-landing-sans)] text-cream antialiased`}>
      {/* 1 · Hero */}
      <section className="p-2 sm:p-3">
        <div className="relative h-[calc(100vh-1rem)] overflow-hidden rounded-2xl border border-white/5 bg-void sm:h-[calc(100vh-1.5rem)]">
          {/* Limit: the hero video is hotlinked from a CDN; copy it into web/public/ if that link may expire before the demo */}
          <video
            src={HERO_VIDEO}
            autoPlay
            muted
            loop
            playsInline
            preload="metadata"
            poster={hasArt("hero-poster") ? "/landing/hero-poster.webp" : undefined}
            className="absolute inset-0 size-full object-cover opacity-60 motion-reduce:hidden"
            aria-hidden
          />
          <ShockwaveCanvas className="absolute inset-0 size-full opacity-60 mix-blend-screen" />
          <div className="noise-overlay pointer-events-none absolute inset-0 opacity-70 mix-blend-overlay" />
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/50 via-black/20 to-black/80" />

          <nav className="absolute top-4 left-1/2 z-50 flex w-[calc(100%-2rem)] max-w-5xl -translate-x-1/2 items-center gap-6 rounded-full border border-white/10 bg-black/40 px-5 py-2.5 backdrop-blur-md">
            <Link href="/" className="flex items-center gap-2 text-sm font-bold tracking-wide">
              <span className="grid size-6 place-items-center rounded-full border border-gold/60">
                <span className="size-1.5 rounded-full bg-gold" />
              </span>
              Epicenter
            </Link>
            <div className="hidden flex-1 items-center justify-center gap-7 md:flex">
              {NAV.map(([label, href]) => (
                <a key={href} href={href} className="text-xs tracking-[0.14em] uppercase opacity-70 transition-opacity hover:opacity-100">
                  {label}
                </a>
              ))}
            </div>
            <Link href="/incidents" className="ml-auto rounded-full bg-gold px-4 py-1.5 text-xs font-bold tracking-wide text-black transition-opacity hover:opacity-90 md:ml-0">
              Open app
            </Link>
            {/* Note: native <details> for the phone menu; no state, closes on the next tap of the button */}
            <details className="relative md:hidden">
              <summary className="grid size-8 cursor-pointer list-none place-items-center rounded-full border border-white/15 [&::-webkit-details-marker]:hidden" aria-label="Menu">
                <Menu className="size-4" />
              </summary>
              <div className="absolute top-11 right-0 flex w-48 flex-col rounded-2xl border border-white/10 bg-black/90 p-2 backdrop-blur-md">
                {NAV.map(([label, href]) => (
                  <a key={href} href={href} className="rounded-xl px-3 py-2.5 text-xs tracking-[0.14em] uppercase opacity-80 hover:bg-white/5 hover:opacity-100">
                    {label}
                  </a>
                ))}
              </div>
            </details>
          </nav>

          <div className="absolute inset-x-0 bottom-0 z-20 p-6 sm:p-10 lg:p-14">
            <p className="mb-6 text-xs tracking-[0.25em] uppercase opacity-60">Root cause analysis · built on FalkorDB</p>
            <Reveal as="h1" className="text-[13vw] leading-[0.92] font-light tracking-tight not-italic sm:text-[9vw]">
              <W>Every outage has</W>
              <br />
              <W from={3}>an</W> <span className={`${serifI} text-gold`}><W from={4}>epicenter.</W></span>
            </Reveal>
            <div className="mt-8 flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
              <p className="max-w-md text-base leading-relaxed opacity-75">
                Epicenter searches your live call graph upstream from the alert, checks every suspect against what actually
                broke, and returns the answer as a path you can verify.
              </p>
              <div className="flex flex-wrap gap-3">
                <Link href="/incidents" className="inline-flex items-center gap-2 rounded-full bg-gold px-6 py-3 text-sm font-bold text-black transition-opacity hover:opacity-90">
                  Open the app <ArrowRight className="size-4" />
                </Link>
                <Link href="/runs" className="inline-flex items-center gap-2 rounded-full border border-cream/30 px-6 py-3 text-sm transition-colors hover:border-cream/70">
                  Break something on purpose
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 2 · Where you might be */}
      <section className="mx-auto max-w-4xl px-6 py-28 text-center sm:py-36">
        <p className="text-xs tracking-[0.25em] uppercase opacity-50">Where you might be</p>
        <Reveal as="h2" className={`${serifI} mt-8 text-4xl leading-tight text-gold sm:text-6xl`}>
          <W>It’s 3 a.m. Forty alerts, twelve dashboards, one question: where did it start?</W>
        </Reveal>
        <p className="mx-auto mt-10 max-w-2xl text-lg leading-relaxed opacity-70">
          The loudest service is rarely the cause. Checkout is on fire because payment is failing, and payment is failing
          because a flag flipped two minutes earlier. Most tools, and most AI agents, stop at the loudest symptom. Epicenter
          follows the graph to where it began.
        </p>
        <Illustration name="where-you-are" alt="An on-call engineer's desk at 3 a.m., lit by a wall of alerts" ratio="aspect-[21/9]" className="mt-16 rounded-2xl border border-white/5" />
      </section>

      {/* 3 · Philosophy */}
      <section id="philosophy" className="px-3 sm:px-6">
        <div className="mx-auto max-w-6xl rounded-[2rem] border border-white/5 bg-carbon px-6 py-20 sm:px-16 sm:py-28">
          <span className="inline-block rounded-full border border-white/10 px-3 py-1 text-[11px] tracking-[0.2em] uppercase opacity-70">Our philosophy</span>
          <Reveal as="h2" className="mt-10 max-w-4xl text-4xl leading-[1.1] font-light not-italic sm:text-6xl">
            <span className={`${serifI} text-gold`}><W>The graph does the reasoning.</W></span> <W from={5}>The language model only explains.</W>
          </Reveal>
          <p className="mt-10 max-w-2xl text-lg leading-relaxed opacity-70">
            Suspects, evidence, memory and agent hand-offs all live in FalkorDB. The ranking is a deterministic score with
            versioned weights: the same input gives the same answer, byte for byte. When nothing in the graph explains the
            alert, Epicenter says so instead of inventing a cause.
          </p>
          <Illustration name="philosophy" alt="A hand-drawn map laid over the territory it describes" ratio="aspect-[16/9]" className="mt-14 rounded-2xl border border-white/5" />
          <figure className="mt-20 border-t border-white/10 pt-10">
            <blockquote className={`${serifI} text-2xl opacity-90 sm:text-3xl`}>“All models are wrong, but some are useful.”</blockquote>
            <figcaption className="mt-4 text-xs tracking-[0.2em] uppercase opacity-50">George E. P. Box, statistician</figcaption>
          </figure>
        </div>
      </section>

      {/* 4 · The agents (the reference's team grid) */}
      <section id="agents" className="mx-auto max-w-7xl px-6 py-28 sm:py-36">
        <div className="flex flex-col justify-between gap-6 sm:flex-row sm:items-end">
          <Reveal as="h2" className="text-4xl font-light not-italic sm:text-5xl">
            <W>The</W> <span className={`${serifI} text-gold`}><W from={1}>agents</W></span>
          </Reveal>
          <p className="max-w-md opacity-60">Several agents work the incident together, through the same graph. None of them can change the verdict on its own.</p>
        </div>
        <div className="mt-16 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {AGENTS.map(({ name, role, text, file, Glyph, art }) => (
            <article key={name} className="group">
              <div className="aspect-[3/4] overflow-hidden rounded-xl border border-white/5 opacity-80 grayscale transition duration-500 group-hover:opacity-100 group-hover:grayscale-0">
                <Illustration name={art} alt={`${name}: ${role.toLowerCase()}`} ratio="aspect-[3/4]" fallback={<Glyph />} />
              </div>
              <div className="mt-5 flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-lg font-bold">{name}</h3>
                  <p className={`${serifI} text-gold`}>{role}</p>
                </div>
                <a href={`${REPO}/blob/main/api/agents/${file}`} target="_blank" rel="noreferrer" className="text-gold/30 transition-colors hover:text-gold" aria-label={`${name} source on GitHub`}>
                  <Github className="size-5" />
                </a>
              </div>
              <p className="mt-3 text-sm leading-relaxed opacity-60">{text}</p>
            </article>
          ))}
        </div>
      </section>

      {/* 5 · What we do */}
      <section id="what" className="mx-auto max-w-6xl px-6 pb-28 sm:pb-36">
        <p className="text-xs tracking-[0.25em] uppercase opacity-50">What it does</p>
        <Illustration name="what-it-does" alt="A path of light walking a dark graph upstream to one glowing node" ratio="aspect-[16/9]" className="mt-10 rounded-2xl border border-white/5" />
        <div className="mt-12 grid grid-cols-1 gap-x-16 gap-y-14 md:grid-cols-2">
          {WHAT.map(([title, text]) => (
            <div key={title} className="border-t border-white/20 pt-8">
              <Reveal as="h3" className={`${serifI} text-3xl text-gold`}><W>{title}</W></Reveal>
              <p className="mt-4 leading-relaxed opacity-70">{text}</p>
            </div>
          ))}
        </div>
        <p className="mt-14 text-sm opacity-70">
          Built for Graph Hacks on{" "}
          <a href="https://www.falkordb.com" target="_blank" rel="noreferrer" className="underline decoration-gold/50 underline-offset-4 hover:decoration-gold">
            FalkorDB
          </a>
          , the graph database the whole investigation lives in.
        </p>
      </section>

      {/* 6 · Science */}
      <section id="science" className="relative overflow-hidden border-y border-white/5 bg-void px-6 py-28 sm:py-36">
        <Illustration name="science" alt="" ratio="!absolute inset-0" className="opacity-25" />
        <div className="pointer-events-none absolute top-1/2 left-1/2 size-[min(600px,120vw)] -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/[0.02] blur-[120px]" />
        <div className="bg-noise pointer-events-none absolute inset-0 opacity-[0.04]" />
        <div className="relative mx-auto max-w-5xl">
          <p className="text-xs tracking-[0.25em] uppercase opacity-50">Under the hood</p>
          <Reveal as="h2" className="mt-8 max-w-3xl text-4xl leading-tight font-light not-italic sm:text-5xl">
            <W>Deterministic first.</W> <span className={`${serifI} text-gold`}><W from={2}>Explainable always.</W></span>
          </Reveal>
          <ul className="mt-14 grid grid-cols-1 gap-x-12 gap-y-5 md:grid-cols-2">
            {SCIENCE.map((s) => (
              <li key={s} className="flex items-start gap-4 border-b border-white/5 pb-5">
                <span className="mt-2 size-1.5 shrink-0 rounded-full bg-gold" />
                <span className="opacity-80">{s}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* 7 · Proof + run it yourself (the reference's stats + form card) */}
      <section id="run" className="mx-auto grid max-w-6xl grid-cols-1 gap-16 px-6 py-28 sm:py-36 lg:grid-cols-2">
        <div>
          <Illustration name="run-it" alt="A laptop on a dark desk running Epicenter in a terminal" ratio="aspect-[4/3]" className="mb-12 rounded-2xl border border-white/5" />
          <p className="text-xs tracking-[0.25em] uppercase opacity-50">Measured on our own runs</p>
          <dl className="mt-12 space-y-10">
            {STATS.map(([n, label]) => (
              <div key={n} className="border-t border-white/10 pt-6">
                <dt className={`${serifI} text-6xl text-gold`}>{n}</dt>
                <dd className="mt-2 opacity-60">{label}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="rounded-[2rem] border border-white/5 bg-carbon p-8 sm:p-12">
          <Reveal as="h2" className="text-3xl font-light not-italic">
            <W>Run it</W> <span className={`${serifI} text-gold`}><W from={2}>yourself</W></span>
          </Reveal>
          <p className="mt-3 opacity-60">Docker and about fifteen minutes. The system evaluator picks the samples your machine can run.</p>
          <div className="mt-10 space-y-7">
            <CopyLine label="1 · Clone" cmd={`git clone ${REPO}.git && cd epicenter`} />
            <CopyLine label="2 · Configure" cmd="cp .env.example .env" />
            <CopyLine label="3 · Start" cmd="docker compose up -d" />
          </div>
          <div className="mt-10 flex flex-wrap gap-3">
            <Link href="/runs" className="inline-flex items-center gap-2 rounded-full bg-gold px-6 py-3 text-sm font-bold text-black transition-opacity hover:opacity-90">
              Try a live fault <ArrowRight className="size-4" />
            </Link>
            <a href={`${REPO}/blob/main/docs/SETUP.md`} target="_blank" rel="noreferrer" className="inline-flex items-center rounded-full border border-cream/30 px-6 py-3 text-sm transition-colors hover:border-cream/70">
              Setup guide
            </a>
          </div>
        </div>
      </section>

      <noscript>
        <style>{"[data-reveal] .rv-w { opacity: 1 !important; transform: none !important; filter: none !important; }"}</style>
      </noscript>
      <footer className="border-t border-white/5 px-6 py-10">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 text-xs tracking-[0.15em] uppercase opacity-50">
          <span>Epicenter · Graph Hacks · FalkorDB</span>
          <a href={REPO} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 hover:opacity-100">
            <Github className="size-4" /> Source
          </a>
        </div>
      </footer>
    </div>
  );
}
