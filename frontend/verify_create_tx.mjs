import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

await page.goto('http://localhost:3000/login');
await page.waitForLoadState('networkidle');
await page.fill('input[type="email"]', 'admin@acmemfg.in');
await page.fill('input[type="password"]', 'Admin@123');
await page.locator('button[type="submit"]').click();
await page.waitForURL('**/dashboard', { timeout: 10000 });

await page.goto('http://localhost:3000/transactions');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1000);

// Click "Create Transaction"
await page.click('button:has-text("Create Transaction")');
await page.waitForTimeout(600);
await page.screenshot({ path: 'screenshots/create_tx_dialog.png' });
console.log('Dialog opened');

// Type a natural language transaction
await page.fill('textarea', 'Create an expense of ₹15,000 for office supplies from Office World');
await page.waitForTimeout(300);
await page.screenshot({ path: 'screenshots/create_tx_typed.png' });

// Click Extract & Preview
await page.click('button:has-text("Extract")');
await page.waitForTimeout(4000);
await page.screenshot({ path: 'screenshots/create_tx_preview.png' });
console.log('Preview screenshot taken');

await browser.close();
