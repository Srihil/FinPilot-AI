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
await page.waitForTimeout(2000);

// Count before
const convsBefore = await page.locator('button[title="Delete conversation"]').count();
console.log('Delete buttons found:', convsBefore);

// Hover over first conversation and screenshot
const firstConvRow = page.locator('[title="Delete conversation"]').first().locator('..');
await page.locator('[title="Delete conversation"]').first().locator('..').hover().catch(() => {
  // try hovering the container
  page.locator('div.group').first().hover();
});
await page.waitForTimeout(400);
await page.screenshot({ path: 'screenshots/delete_hover.png' });
console.log('Hover screenshot taken');

// Count conversations
const totalBefore = await page.locator('div.group.flex.items-center').count();
console.log('Total conv rows before:', totalBefore);

// Click delete on first conversation
await page.locator('[title="Delete conversation"]').first().click({ force: true });
await page.waitForTimeout(2000);

const totalAfter = await page.locator('div.group.flex.items-center').count();
console.log('Total conv rows after delete:', totalAfter);
await page.screenshot({ path: 'screenshots/after_delete.png' });

await browser.close();
