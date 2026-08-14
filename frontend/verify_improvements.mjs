import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

// Login as demo user
await page.goto('http://localhost:3000/login');
await page.waitForLoadState('networkidle');
await page.fill('input[type="email"]', 'admin@acmemfg.in');
await page.fill('input[type="password"]', 'Admin@123');
await page.locator('button[type="submit"]').click();
await page.waitForURL('**/dashboard', { timeout: 10000 });

// AI Assistant - send a message
await page.goto('http://localhost:3000/assistant');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1000);
await page.click('text=New Conversation');
await page.waitForTimeout(500);
await page.fill('textarea', 'Give me a financial summary for this month');
await page.keyboard.press('Enter');
await page.waitForTimeout(5000);
await page.screenshot({ path: 'screenshots/improved_01_ai_chat.png', fullPage: false });
console.log('AI chat screenshot taken');

// Reports page
await page.goto('http://localhost:3000/reports');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(500);
await page.screenshot({ path: 'screenshots/improved_02_reports.png', fullPage: false });
console.log('Reports screenshot taken');

// Approvals page
await page.goto('http://localhost:3000/approvals');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1000);
await page.screenshot({ path: 'screenshots/improved_03_approvals.png', fullPage: false });
console.log('Approvals screenshot taken');

await browser.close();
console.log('Done!');
