import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const htmlPath = path.resolve("attachments/fourth_Header_first_jobs_page_example.html");
const jsPath = path.resolve("kariyer_ats/extract_wizard.js");
const html = fs.readFileSync(htmlPath, "utf8");
const extractSrc = fs.readFileSync(jsPath, "utf8");

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
await page.setContent(html, { waitUntil: "domcontentloaded" });
const result = await page.evaluate(`(${extractSrc})()`);
await browser.close();

fs.writeFileSync("artifacts/wizard_extract_sample.json", JSON.stringify(result, null, 2));
console.log(JSON.stringify(result, null, 2));

const checks = {
  pozisyon: result.pozisyon.includes("Çağrı Merkezi"),
  departman: result.departman === "Satış",
  lokasyon: Array.isArray(result.lokasyon) && result.lokasyon.includes("Bursa"),
  calisma_sekli: result.calisma_sekli.includes("Tam Zamanlı"),
  calisma_tercihi: result.calisma_tercihi.includes("İş yerinde"),
  pozisyon_seviyesi: result.pozisyon_seviyesi === "Uzman",
  skills: result.yetenekler.includes("Çağrı Merkezi"),
  education: result.egitim_seviyesi.includes("Lise-Mezun"),
  desc: result.ilan_aciklamasi.includes("KEN Academy"),
  image: result.ilan_gorsel_url.includes("jobtemplate"),
  company: result.sirket_sayfasi.includes("More Payroll"),
  positions: result.calistigi_pozisyonlar.includes("Müşteri Temsilcisi"),
};
const failed = Object.entries(checks).filter(([, v]) => !v);
console.log("CHECKS", checks);
if (failed.length) {
  console.error("FAILED", failed.map(([k]) => k));
  process.exit(1);
}
console.log("ALL CHECKS PASSED");