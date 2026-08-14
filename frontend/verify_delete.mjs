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

// Count conversations before
const convsBefore = await page.locator('.group.flex.items-center').count();
console.log('Conversations before delete:', convsBefore);

// Screenshot showing delete icons on hover
const firstConv = page.locator('.group.flex.items-center').first();
await firstConv.hover();
await page.waitForTimeout(300);
await page.screenshot({ path: 'screenshots/conv_hover_delete.png' });
console.log('Hover screenshot taken');

// Click delete on first conversation
const deleteBtn = firstConv.locator('button[title="Delete conversation"]');
const isVisible = await deleteBtn.isVisible();
console.log('Delete button visible on hover:', isVisible);

if (isVisible) {
  await deleteBtn.click();
  await page.waitForTimeout(2000);
  const convsAfter = await page.locator('.group.flex.items-center').count();
  console.log('Conversations after delete:', convsAfter);
  await page.screenshot({ path: 'screenshots/conv_after_delete.png' });
}

await browser.close();
