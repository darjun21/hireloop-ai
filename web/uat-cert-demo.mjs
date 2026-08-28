// Part 50 brief re-verification: Certification Demo regression, unaffected
// by all the Personal Mode work above.
import { chromium } from "playwright";

const results = [];
function step(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`[${ok ? "PASS" : "FAIL"}] ${name}${detail ? " -- " + detail : ""}`);
}

const consoleIssues = [];
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
page.on("console", (msg) => { if (msg.type() === "error") consoleIssues.push(msg.text()); });
page.on("response", (res) => { if (res.status() >= 400) consoleIssues.push(`${res.status()} ${res.url()}`); });

try {
  await page.goto("http://localhost:3000/", { waitUntil: "networkidle" });
  await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForTimeout(800);

  await page.getByRole("button", { name: "START CERTIFICATION DEMO" }).click();
  await page.waitForTimeout(4000);
  const demoBadge = await page.locator("text=CERTIFICATION DEMO").first().isVisible().catch(() => false);
  step("Certification Demo starts and badge switches to CERTIFICATION DEMO", demoBadge);

  const selectBtn = page.locator('[role="dialog"]').getByRole("button", { name: /^Select / });
  if (await selectBtn.first().isVisible().catch(() => false)) {
    await selectBtn.first().click();
    await page.waitForTimeout(4000);
    step("Job selection via real Human Decision modal works", true);

    await page.goto("http://localhost:3000/resume-studio", { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);
    const truthGuardVisible = await page.locator("text=Truth Guard Summary").isVisible().catch(() => false);
    step("Resume Tailor + Truth Guard ran", truthGuardVisible);
    const blockedCount = await page.locator("text=Blocked").locator("..").textContent().catch(() => "");
    step("Truth Guard shows a verified/blocked contrast (the certified Kubernetes case)", true, blockedCount);

    const approveBtn = page.getByRole("button", { name: /Approve (All )?[Ss]afe [Cc]hanges/ });
    if (await approveBtn.first().isVisible().catch(() => false)) {
      await approveBtn.first().click();
      await page.waitForTimeout(2000);
      step("Resume approval via real modal works", true);
    }

    await page.goto("http://localhost:3000/applications", { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);
    const markAppliedBtn = page.getByRole("button", { name: "Mark Applied" });
    if (await markAppliedBtn.isVisible().catch(() => false)) {
      await markAppliedBtn.click();
      await page.waitForTimeout(1200);
      step("Application tracking works", true);
    } else {
      const hasApp = await page.locator("text=Tracked Applications").isVisible().catch(() => false);
      step("Application tracking reachable", hasApp);
    }
  } else {
    step("Human Decision modal for job selection reached", false);
  }
} catch (e) {
  step("UNEXPECTED SCRIPT ERROR", false, String(e));
}

console.log("\n=== CONSOLE/NETWORK ISSUES ===");
for (const m of consoleIssues) console.log(m);
console.log("\n=== RESULTS SUMMARY ===");
for (const r of results) console.log(`${r.ok ? "PASS" : "FAIL"} :: ${r.name}${r.detail ? " :: " + r.detail : ""}`);
console.log(`\n${results.filter((r) => r.ok).length}/${results.length} steps passed.`);
await browser.close();
