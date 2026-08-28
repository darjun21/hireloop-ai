// One-off script: launches headless Chromium, opens Mission Control at
// 1920x1080, clicks "START CERTIFICATION DEMO" so real backend data is
// showing, and saves a PNG. Requires the API bridge (uvicorn api.main:app
// --port 8000) and the Next.js server (npm start, port 3000) to already
// be running.
import { chromium } from "playwright";

const url = process.argv[2] || "http://localhost:3000/";
const out = process.argv[3] || "screenshot-mission-control.png";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await page.goto(url, { waitUntil: "networkidle" });

// Click the demo-start button once it actually renders (empty state loads
// asynchronously after the session bootstrap call resolves).
const btn = page.getByText("START CERTIFICATION DEMO");
await btn.waitFor({ state: "visible", timeout: 15000 });
await btn.click();
await page.waitForTimeout(4000);
await page.waitForLoadState("networkidle");
await page.screenshot({ path: out, fullPage: false });
await browser.close();
console.log("Saved", out);
