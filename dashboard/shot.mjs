import puppeteer from "puppeteer-core";

const URL = process.env.URL || "http://localhost:5173";
const OUT = process.env.OUT || "/tmp/shots";
import { mkdirSync } from "node:fs";
mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: "/usr/bin/google-chrome-stable",
  headless: "new",
  args: [
    "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
    "--window-size=1600,900",
    "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
    "--ignore-gpu-blocklist", "--enable-webgl",
  ],
});
const page = await browser.newPage();
await page.setViewport({ width: 1600, height: 900 });
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push("PAGEERROR: " + e.message));

await page.goto(URL, { waitUntil: "networkidle2", timeout: 60000 });
await new Promise((r) => setTimeout(r, 14000)); // let map tiles + WS + queries load
await page.screenshot({ path: `${OUT}/command_center.png` });
console.log("captured command center");

// switch to Commissioner
const tabs = await page.$$(".tab");
for (const t of tabs) {
  const txt = await page.evaluate((el) => el.textContent, t);
  if (txt && txt.includes("Commissioner")) { await t.click(); break; }
}
await new Promise((r) => setTimeout(r, 6000));
await page.screenshot({ path: `${OUT}/commissioner.png` });
console.log("captured commissioner");

// run a what-if scenario
try {
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll("button")];
    const run = btns.find((b) => b.textContent && b.textContent.includes("Run simulation"));
    if (run) run.click();
  });
  await new Promise((r) => setTimeout(r, 9000));
  await page.screenshot({ path: `${OUT}/commissioner_scenario.png` });
  console.log("captured scenario");
} catch (e) { console.log("scenario click failed", e.message); }

console.log("CONSOLE ERRORS:", JSON.stringify(errors.slice(0, 20), null, 2));
await browser.close();
