// Priority 11 — session restart test.
// Reaches "profile confirmed" via real UI actions, establishes a real
// workflow session_id by visiting Mission Control, then kills the FastAPI
// process (python PID given as argv[2]) and confirms: (a) the frontend
// never shows a raw 404 overlay, (b) stale-session recovery (Priority 1)
// either transparently recovers or shows the controlled
// "Your search session expired. Your Career Profile is safe." banner with
// a working "Start New Session" action, (c) the Career Profile itself
// (owner_id-scoped, SQLite-backed) is completely untouched across the
// restart.
import { chromium } from "playwright";
import { execSync, spawn } from "child_process";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const RESUME_FIXTURE = path.join(__dirname, "shots", "uat-resume-fixture.txt");
const BACKEND_PORT = 8010;
const REPO_ROOT = path.join(__dirname, "..");

const results = [];
function step(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`[${ok ? "PASS" : "FAIL"}] ${name}${detail ? " -- " + detail : ""}`);
}

function killListenerOnPort(port) {
  try {
    const out = execSync(
      `powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess)"`
    )
      .toString()
      .trim();
    if (out) {
      execSync(`powershell -NoProfile -Command "Stop-Process -Id ${out} -Force -ErrorAction SilentlyContinue"`);
      console.log(`killed backend PID ${out} on port ${port}`);
      return true;
    }
  } catch (e) {
    console.log("kill attempt error:", String(e));
  }
  return false;
}

function spawnBackend() {
  const child = spawn("python", ["-m", "uvicorn", "api.main:app", "--port", String(BACKEND_PORT)], {
    cwd: REPO_ROOT,
    stdio: "ignore",
    detached: true,
    windowsHide: true,
  });
  child.unref();
  return child;
}

async function waitForHealth(timeoutMs) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(`http://127.0.0.1:${BACKEND_PORT}/api/health`);
      if (res.ok) return true;
    } catch {}
    await new Promise((r) => setTimeout(r, 300));
  }
  return false;
}

const consoleIssues = [];
const pageErrors = [];
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
page.on("console", (msg) => {
  if (msg.type() === "error") consoleIssues.push(`[console.error] ${msg.text()}`);
});
page.on("pageerror", (err) => pageErrors.push(String(err)));

try {
  await page.goto("http://localhost:3000/", { waitUntil: "networkidle" });
  await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForTimeout(800);

  // Reach "profile confirmed": upload resume, apply, fill personal info + save.
  await page.goto("http://localhost:3000/career-profile", { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  await page.getByText("Resume & Evidence", { exact: true }).click();
  await page.waitForTimeout(300);
  await page.setInputFiles('input[type="file"]', RESUME_FIXTURE);
  await page.waitForTimeout(2000);
  if (await page.locator("text=Profile Update Preview").isVisible().catch(() => false)) {
    await page.getByRole("button", { name: "Apply Profile Update" }).click();
    await page.waitForTimeout(800);
  }
  await page.getByText("Personal", { exact: true }).click();
  await page.waitForTimeout(300);
  await page.locator("label", { hasText: "First name" }).locator("input").fill("Priya");
  await page.locator("label", { hasText: "Last name" }).locator("input").fill("UATCandidate");
  await page.locator("label", { hasText: "Professional email" }).locator("input").fill("priya.uat@example.com");
  await page.getByRole("button", { name: "Save Changes" }).click();
  await page.waitForTimeout(800);
  step("Profile confirmed stage reached (Personal Info saved)", await page.locator("text=Saved at").isVisible().catch(() => false));

  const ownerIdBefore = await page.evaluate(() => localStorage.getItem("hireloop_owner_id"));

  // Establish a real workflow session_id via Mission Control.
  await page.goto("http://localhost:3000/", { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  const sessionIdBefore = await page.evaluate(() => localStorage.getItem("hireloop_session_id"));
  step("Workflow session_id established before restart", !!sessionIdBefore, sessionIdBefore || "");

  // --- Kill the FastAPI process ---
  const killed = killListenerOnPort(BACKEND_PORT);
  step("Backend process killed (real OS process termination)", killed);
  await new Promise((r) => setTimeout(r, 1000));
  const deadNow = await fetch(`http://127.0.0.1:${BACKEND_PORT}/api/health`).then(() => false).catch(() => true);
  step("Backend confirmed unreachable immediately after kill", deadNow);

  // --- Restart the FastAPI process (fresh process => fresh in-memory _SESSIONS) ---
  spawnBackend();
  const up = await waitForHealth(20000);
  step("Backend process restarted and healthy again", up);

  // --- Interact with the frontend again: click something that hits a workflow endpoint ---
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForTimeout(2000);

  const rawErrorOverlay = await page.locator("text=Unhandled Runtime Error").isVisible().catch(() => false);
  step("No raw Next.js runtime error overlay after restart", !rawErrorOverlay);

  const raw404Text = await page.locator("text=Unknown session_id").isVisible().catch(() => false);
  step("No raw 'Unknown session_id' 404 text shown to the user", !raw404Text);

  const recoveryBannerVisible = await page.locator("text=Your search session expired").isVisible().catch(() => false);
  const missionControlLoaded = await page.locator("text=Ready For Your First Loop").isVisible().catch(() => false)
    || await page.locator("text=Your next opportunity is taking shape").isVisible().catch(() => false);
  step(
    "Frontend ends up in a sane state: either transparent recovery (Mission Control loads) or the controlled expired-session banner",
    recoveryBannerVisible || missionControlLoaded,
    recoveryBannerVisible ? "controlled banner shown" : missionControlLoaded ? "transparent recovery -- Mission Control loaded normally" : "NEITHER -- investigate"
  );

  if (recoveryBannerVisible) {
    const startNewBtn = page.getByRole("button", { name: "Start New Session" });
    step("'Start New Session' action present in the banner", await startNewBtn.isVisible().catch(() => false));
    await startNewBtn.click();
    await page.waitForTimeout(1500);
    const recoveredAfterClick = await page.locator("text=Your next opportunity is taking shape").isVisible().catch(() => false)
      || await page.locator("text=Ready For Your First Loop").isVisible().catch(() => false);
    step("Clicking 'Start New Session' recovers to a working Mission Control", recoveredAfterClick);
  }

  const sessionIdAfter = await page.evaluate(() => localStorage.getItem("hireloop_session_id"));
  step("session_id changed after restart+recovery (old one correctly discarded)", sessionIdAfter !== sessionIdBefore, `before=${sessionIdBefore} after=${sessionIdAfter}`);

  const ownerIdAfter = await page.evaluate(() => localStorage.getItem("hireloop_owner_id"));
  step("owner_id UNCHANGED across the whole restart (Career Profile identity preserved)", ownerIdAfter === ownerIdBefore, `before=${ownerIdBefore} after=${ownerIdAfter}`);

  // --- Confirm the Career Profile itself is completely intact ---
  await page.goto("http://localhost:3000/career-profile", { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  await page.getByText("Personal", { exact: true }).click();
  await page.waitForTimeout(400);
  const firstNameAfter = await page.locator("label", { hasText: "First name" }).locator("input").inputValue();
  step("Career Profile personal info survived the backend restart untouched", firstNameAfter === "Priya", firstNameAfter);

  await page.getByText("Resume & Evidence", { exact: true }).click();
  await page.waitForTimeout(400);
  const skillsSection = await page.locator("text=QuantumFluxCalibration").isVisible().catch(() => false);
  step("Resume-derived skills survived the backend restart untouched", skillsSection);
} catch (e) {
  step("UNEXPECTED SCRIPT ERROR", false, String(e));
}

console.log("\n=== CONSOLE ERRORS ===");
for (const m of consoleIssues) console.log(m);
console.log("\n=== UNCAUGHT PAGE ERRORS ===");
for (const e of pageErrors) console.log(e);

console.log("\n=== RESULTS SUMMARY ===");
for (const r of results) console.log(`${r.ok ? "PASS" : "FAIL"} :: ${r.name}${r.detail ? " :: " + r.detail : ""}`);
const failCount = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failCount}/${results.length} steps passed.`);

await browser.close();
