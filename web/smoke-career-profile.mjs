// Real-browser smoke test for this hardening pass: Career Profile save +
// reload persistence, Mission Control <-> Career Profile navigation, and
// full console error capture (CORS / 404 / uncaught rejection).
import { chromium } from "playwright";

const consoleMessages = [];
const pageErrors = [];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("console", (msg) => {
  consoleMessages.push({ type: msg.type(), text: msg.text() });
});
page.on("pageerror", (err) => {
  pageErrors.push(String(err));
});
page.on("requestfailed", (req) => {
  consoleMessages.push({ type: "requestfailed", text: `${req.method()} ${req.url()} :: ${req.failure()?.errorText}` });
});
page.on("response", (res) => {
  if (res.status() >= 400) {
    consoleMessages.push({ type: "http-error", text: `${res.status()} ${res.request().method()} ${res.url()}` });
  }
});

console.log("=== Navigating to Mission Control ===");
await page.goto("http://localhost:3000/", { waitUntil: "networkidle" });
await page.waitForTimeout(1000);

console.log("=== Navigating to Career Profile ===");
await page.goto("http://localhost:3000/career-profile", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);

// Go to Career & Preferences tab
await page.getByText("Career & Preferences", { exact: true }).click();
await page.waitForTimeout(500);

console.log("=== Filling Employment Preferences ===");
const locationsInput = page.locator("label", { hasText: "Locations" }).locator("input");
await locationsInput.fill("United States");

const employmentTypeInput = page.locator("label", { hasText: "Employment type" }).locator("input");
await employmentTypeInput.fill("Full Time");

const compMinInput = page.locator("label", { hasText: "Target compensation min" }).locator("input");
await compMinInput.fill("120000");

const relocationSelect = page.locator("label", { hasText: "Relocation willing" }).locator("select");
await relocationSelect.selectOption("true");

console.log("=== Clicking Save Changes ===");
const saveButtons = page.getByRole("button", { name: /Save Changes/ });
await saveButtons.first().click();

// Confirm success state (Saved at ...)
await page.waitForTimeout(1500);
const savedText = await page.locator("text=Saved at").first().isVisible().catch(() => false);
console.log("Save confirmation visible:", savedText);

console.log("=== Reloading page ===");
await page.reload({ waitUntil: "networkidle" });
await page.waitForTimeout(1500);
await page.getByText("Career & Preferences", { exact: true }).click();
await page.waitForTimeout(500);

const locationsAfterReload = await page.locator("label", { hasText: "Locations" }).locator("input").inputValue();
const employmentTypeAfterReload = await page.locator("label", { hasText: "Employment type" }).locator("input").inputValue();
const compMinAfterReload = await page.locator("label", { hasText: "Target compensation min" }).locator("input").inputValue();
const relocationAfterReload = await page.locator("label", { hasText: "Relocation willing" }).locator("select").inputValue();

console.log("After reload -> locations:", locationsAfterReload);
console.log("After reload -> employment type:", employmentTypeAfterReload);
console.log("After reload -> comp min:", compMinAfterReload);
console.log("After reload -> relocation:", relocationAfterReload);

console.log("=== Navigating Mission Control <-> Career Profile a few times ===");
for (let i = 0; i < 3; i++) {
  await page.goto("http://localhost:3000/", { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  await page.goto("http://localhost:3000/career-profile", { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
}

console.log("=== Navigating to Candidate Setup (discovery prefill check) ===");
await page.goto("http://localhost:3000/candidate-setup", { waitUntil: "networkidle" });
await page.waitForTimeout(1000);
const prefillVisible = await page.locator("text=pre-filled from your Career Profile").isVisible().catch(() => false);
console.log("Discovery prefill banner visible:", prefillVisible);

await browser.close();

console.log("\n=== CONSOLE MESSAGES ===");
for (const m of consoleMessages) console.log(`[${m.type}] ${m.text}`);
console.log("\n=== UNCAUGHT PAGE ERRORS ===");
for (const e of pageErrors) console.log(e);
console.log("\nDONE.");
