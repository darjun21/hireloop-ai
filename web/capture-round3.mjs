// Drives the real HireLoop workflow one step further than the prior two
// certification rounds: selection -> resume approval -> real Application
// creation -> Mark Applied -> real outcome recording (INTERVIEW) ->
// Strategy Intelligence -> Mission Control. Every state transition below
// is a genuine Playwright click on a genuine button that calls the real
// FastAPI bridge (api/main.py), which calls the real LangGraph workflow.
// Nothing here writes to frontend state directly.
import { chromium } from "playwright";
import fs from "node:fs";

const OUT_DIR = process.argv[2] || "shots";
if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
page.on("console", (msg) => {
  if (msg.type() === "error") console.log("[console.error]", msg.text());
});
page.on("pageerror", (err) => console.log("[pageerror]", err.message));

async function shot(name) {
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT_DIR}/${name}.png`, fullPage: false });
  console.log("Saved", name);
}

// --- A: Mission Control at the job-selection interrupt (real demo start) ---
await page.goto("http://localhost:3000/", { waitUntil: "networkidle" });
const startBtn = page.getByText("START CERTIFICATION DEMO");
await startBtn.waitFor({ state: "visible", timeout: 20000 });
await startBtn.click();
await page.waitForLoadState("networkidle");
await page.waitForTimeout(2000);
await shot("screenshot-A-mission-control-selection-interrupt");

// --- B: Opportunity Detail for job_ai_001 (the certification demo pick) ---
await page.goto("http://localhost:3000/opportunities/job_ai_001", { waitUntil: "networkidle" });
await page.waitForTimeout(1000);
await shot("screenshot-B-opportunity-detail");

// --- Real click: open the Human Decision modal on the detail page ---
const openModalBtn = page.getByRole("button", { name: "Select Opportunity" });
await openModalBtn.waitFor({ state: "visible", timeout: 10000 });
await openModalBtn.click();
await page.waitForTimeout(500);

// --- Real click: SELECT via the modal -> real backend call (Resume Tailor
// + Truth Guard actually run) -> lands on resume-studio at the resume
// approval interrupt ---
const selectBtn = page.locator("button", { hasText: /^Select .+@/ });
await selectBtn.waitFor({ state: "visible", timeout: 10000 });
await selectBtn.click();
await page.waitForLoadState("networkidle");
await page.waitForTimeout(2500);

// --- D: Resume Approval modal (real BLOCKED + real VERIFIED results) ---
await page.waitForSelector('[role="dialog"]', { timeout: 15000 });
await shot("screenshot-D-resume-approval-modal");

// --- Real click: dismiss modal to view the full Resume Studio page ---
const reviewOnPageBtn = page.getByRole("button", { name: "Review on page" });
await reviewOnPageBtn.click();
await page.waitForTimeout(800);

// --- C: Resume Studio background page with real BLOCKED + real VERIFIED ---
await shot("screenshot-C-resume-studio-blocked-verified");

// --- Real click: Approve Safe Changes (inline button on the page, since
// the modal is dismissed) -> real backend call -> creates a real
// ResumeVersion and a real Application (READY_FOR_REVIEW) ---
const approveBtn = page.getByRole("button", { name: "Approve all safe changes" });
await approveBtn.waitFor({ state: "visible", timeout: 10000 });
await approveBtn.click();
await page.waitForLoadState("networkidle");
await page.waitForTimeout(2000);

// --- E: Applications page with the real, newly-created application card ---
await page.goto("http://localhost:3000/applications", { waitUntil: "networkidle" });
await page.waitForTimeout(1200);
await shot("screenshot-E-applications-ready-for-review");

const statusTextE = await page.locator("body").innerText();
const hasReadyForReview = /READY_FOR_REVIEW/i.test(statusTextE);
console.log("Applications page shows READY_FOR_REVIEW:", hasReadyForReview);

// --- Real click: Mark Applied -> real backend call -> status -> APPLIED ---
const markAppliedBtn = page.getByRole("button", { name: "Mark Applied" });
await markAppliedBtn.waitFor({ state: "visible", timeout: 10000 });
await markAppliedBtn.click();
await page.waitForLoadState("networkidle");
await page.waitForTimeout(1500);

// --- F: Applications page after real MARK_APPLIED ---
await shot("screenshot-F-applications-applied");
const statusTextF = await page.locator("body").innerText();
const hasApplied = /\bAPPLIED\b/.test(statusTextF);
console.log("Applications page shows APPLIED:", hasApplied);

// --- Real click: Start outcome update -> real backend call ---
const startOutcomeBtn = page.getByRole("button", { name: "Start outcome update" });
await startOutcomeBtn.waitFor({ state: "visible", timeout: 10000 });
await startOutcomeBtn.click();
await page.waitForTimeout(1200);

// --- Real select + click: choose INTERVIEW and submit -> real backend
// call -> real ApplicationEvent + real outcome analytics + real Learning
// Agent run ---
const outcomeSelect = page.locator("select").last();
await outcomeSelect.waitFor({ state: "visible", timeout: 10000 });
await outcomeSelect.selectOption("INTERVIEW");
const submitOutcomeBtn = page.getByRole("button", { name: "Submit outcome" });
await submitOutcomeBtn.click();
await page.waitForLoadState("networkidle");
await page.waitForTimeout(2000);

const statusTextAfterOutcome = await page.locator("body").innerText();
console.log("Outcome workflow completed marker present:", /Outcome workflow completed/i.test(statusTextAfterOutcome));

// --- G: Strategy Intelligence after the real INTERVIEW outcome ---
await page.goto("http://localhost:3000/strategy", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
await shot("screenshot-G-strategy-intelligence");

const strategyText = await page.locator("body").innerText();
fs.writeFileSync(`${OUT_DIR}/strategy-page-text.txt`, strategyText);
console.log("Strategy page text length:", strategyText.length);

// --- H: Mission Control reflecting the updated real state ---
await page.goto("http://localhost:3000/", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
await shot("screenshot-H-mission-control-final");

const mcText = await page.locator("body").innerText();
fs.writeFileSync(`${OUT_DIR}/mission-control-final-text.txt`, mcText);

await browser.close();
console.log("Done");
