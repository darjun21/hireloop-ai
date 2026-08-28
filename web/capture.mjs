// Drives the real HireLoop workflow through the actual browser UI (no
// simulated state) and captures the required certification screenshots.
import { chromium } from "playwright";
import fs from "node:fs";

const OUT_DIR = process.argv[2] || "shots";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
page.on("console", (msg) => {
  if (msg.type() === "error") console.log("[console.error]", msg.text());
});

// --- Screenshot A: right after starting the demo, at the first human interrupt ---
await page.goto("http://localhost:3000/", { waitUntil: "networkidle" });
const startBtn = page.getByText("START CERTIFICATION DEMO");
await startBtn.waitFor({ state: "visible", timeout: 15000 });
await startBtn.click();
await page.waitForTimeout(3000);
await page.waitForLoadState("networkidle");
await page.screenshot({ path: `${OUT_DIR}/screenshot-A-mission-control.png`, fullPage: false });
console.log("Saved screenshot A");

// --- Drive forward: select the top opportunity via the real modal button ---
const selectBtn = page.locator("button", { hasText: /^Select .+@/ });
await selectBtn.waitFor({ state: "visible", timeout: 10000 });
await selectBtn.click();
await page.waitForTimeout(3000);
await page.waitForLoadState("networkidle");
await page.waitForTimeout(1500);
await page.screenshot({ path: `${OUT_DIR}/screenshot-B-mission-control.png`, fullPage: false });
console.log("Saved screenshot B (mission control)");

await page.goto("http://localhost:3000/resume-studio", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
await page.screenshot({ path: `${OUT_DIR}/screenshot-B-resume-studio.png`, fullPage: false });
console.log("Saved screenshot B (resume studio)");

await page.goto("http://localhost:3000/opportunities", { waitUntil: "networkidle" });
await page.waitForTimeout(1000);
await page.screenshot({ path: `${OUT_DIR}/screenshot-C-opportunities.png`, fullPage: false });

await page.goto("http://localhost:3000/applications", { waitUntil: "networkidle" });
await page.waitForTimeout(1000);
await page.screenshot({ path: `${OUT_DIR}/screenshot-E-applications.png`, fullPage: false });

await page.goto("http://localhost:3000/strategy", { waitUntil: "networkidle" });
await page.waitForTimeout(1000);
await page.screenshot({ path: `${OUT_DIR}/screenshot-F-strategy.png`, fullPage: false });

await page.goto("http://localhost:3000/", { waitUntil: "networkidle" });
await page.waitForTimeout(1000);
const qa = await page.evaluate(() => ({
  scrollWidth: document.documentElement.scrollWidth,
  clientWidth: document.documentElement.clientWidth,
  scrollHeight: document.documentElement.scrollHeight,
  clientHeight: document.documentElement.clientHeight,
}));
fs.writeFileSync(`${OUT_DIR}/qa-mission-control.json`, JSON.stringify(qa, null, 2));
console.log("QA:", qa);

await browser.close();
console.log("Done");
