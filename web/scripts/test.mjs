// `npm test`: runs the node:test unit tests, then adds their results to the newest test report
// (data/reports/<n>-<utc>/findings.md + agent-context.md, written by tests/report.py). A report older than an hour
// isn't this run's: then a new numbered one is started, so reports are never overwritten.
import { spawnSync } from "node:child_process";
import { appendFileSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = dirname(dirname(fileURLToPath(import.meta.url)));
const REPORTS = join(WEB, "..", "data", "reports");
const FRESH_MS = 60 * 60 * 1000;
mkdirSync(REPORTS, { recursive: true });
const junit = join(REPORTS, `.web-junit-${process.pid}.xml`);

const t0 = Date.now();
const res = spawnSync(
  process.execPath,
  [
    "--test",
    "--experimental-strip-types",
    "--disable-warning=ExperimentalWarning",
    "--disable-warning=MODULE_TYPELESS_PACKAGE_JSON",
    "--test-reporter=spec",
    "--test-reporter-destination=stdout",
    "--test-reporter=junit",
    `--test-reporter-destination=${junit}`,
    "lib/**/*.test.ts",
  ],
  { cwd: WEB, stdio: "inherit" },
);
const seconds = ((Date.now() - t0) / 1000).toFixed(1);

const xml = existsSync(junit) ? readFileSync(junit, "utf8") : "";
const unescape = (s) => s.replaceAll("&quot;", '"').replaceAll("&apos;", "'").replaceAll("&lt;", "<").replaceAll("&gt;", ">").replaceAll("&amp;", "&");
const cases = [...xml.matchAll(/<testcase name="([^"]*)"[^>]*?(?:\/>|>([\s\S]*?)<\/testcase>)/g)].map((m) => {
  const body = m[2] ?? "";
  const fail = body.match(/<failure[^>]*message="([^"]*)"/);
  return { name: unescape(m[1]), outcome: fail ? "failed" : body.includes("<skipped") ? "skipped" : "passed", message: fail ? unescape(fail[1]) : "" };
});
const failed = cases.filter((c) => c.outcome === "failed");
const passed = cases.filter((c) => c.outcome === "passed").length;

const dirs = readdirSync(REPORTS).filter((d) => /^\d+-/.test(d)).sort();
let dir = dirs.length ? join(REPORTS, dirs.at(-1)) : null;
if (!dir || Date.now() - statSync(dir).mtimeMs > FRESH_MS) {
  const n = dirs.length ? Number.parseInt(dirs.at(-1), 10) + 1 : 1;
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
  dir = join(REPORTS, `${String(n).padStart(4, "0")}-${stamp}`);
  mkdirSync(dir);
  writeFileSync(join(dir, "findings.md"), `# Test findings: web only\n\nNo Python run in the last hour; this report holds the web unit tests.\n`);
  writeFileSync(join(dir, "agent-context.md"), `# Agent context: Epicenter web tests\n\nRead \`AGENTS.md\` first. Web code is in \`web/\` (Next.js App Router); pure logic in \`web/lib/*.ts\` with \`*.test.ts\` next to it.\n`);
}

const lines = [
  "",
  `## Web unit tests (node:test): ${failed.length ? `${failed.length} failed` : "all passed"}`,
  "",
  `- ${passed} passed · ${failed.length} failed · ${cases.length - passed - failed.length} skipped in ${seconds} s (\`cd web && npm test\`)`,
  ...failed.flatMap((f) => ["", `### \`${f.name}\``, "", "```", f.message.slice(-1500) || "(no message)", "```"]),
  "",
];
appendFileSync(join(dir, "findings.md"), lines.join("\n"));
const guide = failed.length
  ? [
      "",
      "## Web failures",
      "",
      "The pure logic lives in `web/lib/*.ts` with its test next to it (`*.test.ts`). Reproduce with `cd web && npm test`;",
      "type errors with `npx tsc --noEmit`; lint with `npm run lint`. Never hand-edit `web/lib/api-types.ts`",
      "(regenerate it with `npm run gen:api` against a running API).",
      "",
      ...failed.map((f, i) => `${i + 1}. \`${f.name}\`: ${f.message.split("\n")[0].slice(0, 300)}`),
      "",
    ]
  : ["", "## Web", "", `All ${passed} web unit tests passed.`, ""];
appendFileSync(join(dir, "agent-context.md"), guide.join("\n"));
rmSync(junit, { force: true });
console.log(`report: ${dir}`);
process.exit(res.status ?? 1);
