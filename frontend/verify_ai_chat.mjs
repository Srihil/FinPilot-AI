import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

await page.goto('http://localhost:3000/login');
await page.waitForLoadState('networkidle');
await page.fill('input[type="email"]', 'admin@acmemfg.in');
await page.fill('input[type="password"]', 'Admin@123');
await page.locator('button[type="submit"]').click();
await page.waitForURL('**/dashboard', { timeout: 10000 });

await page.goto('http://localhost:3000/assistant');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1500);

// Click the existing "Test" conversation
const convItem = page.locator('[class*="conversation"], button, div').filter({ hasText: /^Test/ }).first();
await convItem.click().catch(() => {});
await page.waitForTimeout(1000);

// Send a message
const textarea = page.locator('textarea');
await textarea.fill('Give me a financial summary for this month');
await page.locator('button[type="submit"], button').filter({ has: page.locator('svg') }).last().click().catch(() => {
  page.keyboard.press('Enter');
});
await page.waitForTimeout(5000);

await page.screenshot({ path: 'screenshots/ai_with_response.png', fullPage: false });
console.log('Current URL:', page.url());
const bodyText = await page.locator('body').innerText();
const hasMarkdown = bodyText.includes('Financial Summary') || bodyText.includes('Revenue') || bodyText.includes('₹');
console.log('Has financial data in response:', hasMarkdown);

await browser.close();
