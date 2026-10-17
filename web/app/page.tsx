import type { Metadata } from "next";
import { Almarai, Instrument_Serif } from "next/font/google";
import Link from "next/link";

import { ArrowRight, Github } from "@/components/icons";
import { HistorianGlyph, InvestigatorGlyph, SkepticGlyph, TriageGlyph } from "@/components/landing/agent-glyphs";
import { CopyLine } from "@/components/landing/copy-line";
import { ShockwaveCanvas } from "@/components/landing/shockwave-canvas";

/*
 * Landing page. Layout and effects follow the pasted reference (black, cream #DEDBC8, gold #E6C77D, Almarai + Instrument
 * Serif italics, grain, background video, glass nav); the content is Epicenter's. The reference's team photos, tracking
 * script and quote are deliberately not used (UI_SCREENS §12.10). The app itself keeps its own design system (UI_SCREENS §1).
 */
const sans = Almarai({ subsets: ["latin"], weight: ["300", "400", "700"], variable: "--font-landing-sans" });
const serif = Instrument_Serif({ subsets: ["latin"], weight: "400", style: ["normal", "italic"], variable: "--font-landing-serif" });

export const metadata: Metadata = {
  title: "Epicenter: find where every outage started",
  description:
    "Graph-native root cause analysis on FalkorDB. A Fault Simulator checks every suspect, every answer is a graph path, and the same input always gives the same answer.",
};

const REPO = "https://github.com/Prateek1771/epicenter";
const HERO_VIDEO =
  "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260405_170732_8a9ccda6-5cff-4628-b164-059c500a2b41.mp4";
const serifI ="font-[family-name:var(--font-landing-serif)] italic";

const NAV = [
  ["How it works", "#philosophy"],
  ["Agents", "#agents"],
  ["Simulator", "#what"],
  ["Science", "#science"],
  ["Run it", "#run"],
];

const AGENTS = [
  { name: "Triage", role: "Turns the alert into suspects", text: "Every operation upstream of the alert that misbehaved becomes a hypothesis, bounded at six hops.", file: "triage.py", Glyph: TriageGlyph },
  { name: "Investigator", role: "Checks each suspect, in parallel", text: "Did it go bad first? Is it slow itself or waiting on a callee? Did something change right before?", file: "investigator.py", Glyph: InvestigatorGlyph },
  { name: "Skeptic", role: "Argues with the winner", text: "If the leading suspect doesn't explain the alert's own footprint, it is refuted and the ranking runs again.", file: "skeptic.py", Glyph: SkepticGlyph },
  { name: "Historian", role: "Remembers what fixed it", text: "A 64-dimension incident signature finds similar past incidents and the actions that resolved them.", file: "historian.py", Glyph: HistorianGlyph },
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
    <div className={`landing ${sans.variable} ${serif.variable} min-h-screen bg-black font-[family-name:var(--font-landing-sans)] text-[#DEDBC8] antialiased`}>
      {/* 1 · Hero */}
      <section className="p-2 sm:p-3">
        <div className="relative h-[calc(100vh-1rem)] overflow-hidden rounded-2xl border border-white/5 bg-[#050505] sm:h-[calc(100vh-1.5rem)]">
          {/* ponytail: hotlinked from the user's CDN; copy it into web/public/ if that link may expire before the demo */}
          <video
            src={HERO_VIDEO}
            autoPlay
            muted
            loop
            playsInline
            preload="metadata"
            className="absolute inset-0 size-full object-cover opacity-60 motion-reduce:hidden"
            aria-hidden
          />
          <ShockwaveCanvas className="absolute inset-0 size-full opacity-60 mix-blend-screen" />
          <div className="noise-overlay pointer-events-none absolute inset-0 opacity-70 mix-blend-overlay" />
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/50 via-black/20 to-black/80" />

          <nav className="absolute top-4 left-1/2 z-50 flex w-[calc(100%-2rem)] max-w-5xl -translate-x-1/2 items-center gap-6 rounded-full border border-white/10 bg-black/40 px-5 py-2.5 backdrop-blur-md">
            <Link href="/" className="flex items-center gap-2 text-sm font-bold tracking-wide">
              <span className="grid size-6 place-items-center rounded-full border border-[#E6C77D]/60">
                <span className="size-1.5 rounded-full bg-[#E6C77D]" />
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
            <Link href="/incidents" className="ml-auto rounded-full bg-[#E6C77D] px-4 py-1.5 text-xs font-bold tracking-wide text-black transition-opacity hover:opacity-90 md:ml-0">
              Open app
            </Link>
          </nav>

          <div className="absolute inset-x-0 bottom-0 z-20 p-6 sm:p-10 lg:p-14">
            <p className="mb-6 text-xs tracking-[0.25em] uppercase opacity-60">Root cause analysis · built on FalkorDB</p>
            <h1 className="text-[13vw] leading-[0.92] font-light tracking-tight sm:text-[9vw]">
              Every outage has
              <br />
              an <span className={`${serifI} text-[#E6C77D]`}>epicenter.</span>
            </h1>
            <div className="mt-8 flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
              <p className="max-w-md text-base leading-relaxed opacity-75">
                Epicenter searches your live call graph upstream from the alert, checks every suspect against what actually
                broke, and returns the answer as a path you can verify.
              </p>
              <div className="flex flex-wrap gap-3">
                <Link href="/incidents" className="inline-flex items-center gap-2 rounded-full bg-[#E6C77D] px-6 py-3 text-sm font-bold text-black transition-opacity hover:opacity-90">
                  Open the app <ArrowRight className="size-4" />
                </Link>
                <Link href="/runs" className="inline-flex items-center gap-2 rounded-full border border-[#DEDBC8]/30 px-6 py-3 text-sm transition-colors hover:border-[#DEDBC8]/70">
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
        <h2 className={`${serifI} mt-8 text-4xl leading-tight text-[#E6C77D] sm:text-6xl`}>
          It&apos;s 3 a.m. Forty alerts, twelve dashboards, one question: where did it start?
        </h2>
        <p className="mx-auto mt-10 max-w-2xl text-lg leading-relaxed opacity-70">
          The loudest service is rarely the cause. Checkout is on fire because payment is failing, and payment is failing
          because a flag flipped two minutes earlier. Most tools, and most AI agents, stop at the loudest symptom. Epicenter
          follows the graph to where it began.
        </p>
      </section>

      {/* 3 · Philosophy */}
      <section id="philosophy" className="px-3 sm:px-6">
        <div className="mx-auto max-w-6xl rounded-[2rem] border border-white/5 bg-[#0A0A0A] px-6 py-20 sm:px-16 sm:py-28">
          <span className="inline-block rounded-full border border-white/10 px-3 py-1 text-[11px] tracking-[0.2em] uppercase opacity-70">Our philosophy</span>
          <h2 className="mt-10 max-w-4xl text-4xl leading-[1.1] font-light sm:text-6xl">
            <span className={`${serifI} text-[#E6C77D]`}>The graph does the reasoning.</span> The language model only explains.
          </h2>
          <p className="mt-10 max-w-2xl text-lg leading-relaxed opacity-70">
            Suspects, evidence, memory and agent hand-offs all live in FalkorDB. The ranking is a deterministic score with
            versioned weights: the same input gives the same answer, byte for byte. When nothing in the graph explains the
            alert, Epicenter says so instead of inventing a cause.
          </p>
          <figure className="mt-20 border-t border-white/10 pt-10">
            <blockquote className={`${serifI} text-2xl opacity-90 sm:text-3xl`}>“All models are wrong, but some are useful.”</blockquote>
            <figcaption className="mt-4 text-xs tracking-[0.2em] uppercase opacity-50">George E. P. Box, statistician</figcaption>
          </figure>
        </div>
      </section>

      {/* 4 · The agents (the reference's team grid) */}
      <section id="agents" className="mx-auto max-w-7xl px-6 py-28 sm:py-36">
        <div className="flex flex-col justify-between gap-6 sm:flex-row sm:items-end">
          <h2 className="text-4xl font-light sm:text-5xl">
            The <span className={`${serifI} text-[#E6C77D]`}>agents</span>
          </h2>
          <p className="max-w-md opacity-60">Several agents work the incident together, through the same graph. None of them can change the verdict on its own.</p>
        </div>
        <div className="mt-16 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {AGENTS.map(({ name, role, text, file, Glyph }) => (
            <article key={name} className="group">
              <div className="aspect-[3/4] overflow-hidden rounded-xl border border-white/5 opacity-80 grayscale transition duration-500 group-hover:opacity-100 group-hover:grayscale-0">
                <Glyph />
              </div>
              <div className="mt-5 flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-lg font-bold">{name}</h3>
                  <p className={`${serifI} text-[#E6C77D]`}>{role}</p>
                </div>
                <a href={`${REPO}/blob/main/api/agents/${file}`} target="_blank" rel="noreferrer" className="text-[#E6C77D]/30 transition-colors hover:text-[#E6C77D]" aria-label={`${name} source on GitHub`}>
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
        <div className="mt-12 grid grid-cols-1 gap-x-16 gap-y-14 md:grid-cols-2">
          {WHAT.map(([title, text]) => (
            <div key={title} className="border-t border-white/20 pt-8">
              <h3 className={`${serifI} text-3xl text-[#E6C77D]`}>{title}</h3>
              <p className="mt-4 leading-relaxed opacity-70">{text}</p>
            </div>
          ))}
        </div>
        <p className="mt-14 text-sm opacity-70">
          Built for Graph Hacks on{" "}
          <a href="https://www.falkordb.com" target="_blank" rel="noreferrer" className="underline decoration-[#E6C77D]/50 underline-offset-4 hover:decoration-[#E6C77D]">
            FalkorDB
          </a>
          , the graph database the whole investigation lives in.
        </p>
      </section>

      {/* 6 · Science */}
      <section id="science" className="relative overflow-hidden border-y border-white/5 bg-[#050505] px-6 py-28 sm:py-36">
        <div className="pointer-events-none absolute top-1/2 left-1/2 size-[600px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/[0.02] blur-[120px]" />
        <div className="bg-noise pointer-events-none absolute inset-0 opacity-[0.04]" />
        <div className="relative mx-auto max-w-5xl">
          <p className="text-xs tracking-[0.25em] uppercase opacity-50">Under the hood</p>
          <h2 className="mt-8 max-w-3xl text-4xl leading-tight font-light sm:text-5xl">
            Deterministic first. <span className={`${serifI} text-[#E6C77D]`}>Explainable always.</span>
          </h2>
          <ul className="mt-14 grid grid-cols-1 gap-x-12 gap-y-5 md:grid-cols-2">
            {SCIENCE.map((s) => (
              <li key={s} className="flex items-start gap-4 border-b border-white/5 pb-5">
                <span className="mt-2 size-1.5 shrink-0 rounded-full bg-[#E6C77D]" />
                <span className="opacity-80">{s}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* 7 · Proof + run it yourself (the reference's stats + form card) */}
      <section id="run" className="mx-auto grid max-w-6xl grid-cols-1 gap-16 px-6 py-28 sm:py-36 lg:grid-cols-2">
        <div>
          <p className="text-xs tracking-[0.25em] uppercase opacity-50">Measured on our own runs</p>
          <dl className="mt-12 space-y-10">
            {STATS.map(([n, label]) => (
              <div key={n} className="border-t border-white/10 pt-6">
                <dt className={`${serifI} text-6xl text-[#E6C77D]`}>{n}</dt>
                <dd className="mt-2 opacity-60">{label}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="rounded-[2rem] border border-white/5 bg-[#0A0A0A] p-8 sm:p-12">
          <h2 className="text-3xl font-light">
            Run it <span className={`${serifI} text-[#E6C77D]`}>yourself</span>
          </h2>
          <p className="mt-3 opacity-60">Docker and about fifteen minutes. The system evaluator picks the samples your machine can run.</p>
          <div className="mt-10 space-y-7">
            <CopyLine label="1 · Clone" cmd={`git clone ${REPO}.git && cd epicenter`} />
            <CopyLine label="2 · Configure" cmd="cp .env.example .env" />
            <CopyLine label="3 · Start" cmd="docker compose up -d" />
          </div>
          <div className="mt-10 flex flex-wrap gap-3">
            <Link href="/runs" className="inline-flex items-center gap-2 rounded-full bg-[#E6C77D] px-6 py-3 text-sm font-bold text-black transition-opacity hover:opacity-90">
              Try a live fault <ArrowRight className="size-4" />
            </Link>
            <a href={`${REPO}/blob/main/docs/SETUP.md`} target="_blank" rel="noreferrer" className="inline-flex items-center rounded-full border border-[#DEDBC8]/30 px-6 py-3 text-sm transition-colors hover:border-[#DEDBC8]/70">
              Setup guide
            </a>
          </div>
        </div>
      </section>

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
