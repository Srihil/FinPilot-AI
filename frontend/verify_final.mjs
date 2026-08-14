import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
page.setDefaultTimeout(15000);

// Login
await page.goto('http://localhost:3000/login');
await page.waitForLoadState('networkidle');
await page.locator('input[type="email"]').fill('admin@acmemfg.in');
await page.locator('input[type="password"]').fill('Admin@123');
await page.locator('button[type="submit"]').click();
await page.waitForURL('**/dashboard', { timeout: 10000 });
await page.waitForTimeout(3000);

// Dashboard
await page.screenshot({ path: 'screenshots/final_01_dashboard.png', fullPage: false });

// Customers (check NaN fix)
await page.click('a[href="/customers"]');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(2000);
await page.screenshot({ path: 'screenshots/final_02_customers.png' });

// Analytics (check data fix)
await page.click('a[href="/analytics"]');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(3000);
await page.screenshot({ path: 'screenshots/final_03_analytics.png' });

// AI Assistant
await page.click('a[href="/assistant"]');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1000);
// Create new conversation
await page.click('text=New Conversation');
await page.waitForTimeout(1000);
// Type a question
await page.fill('textarea', 'What was our revenue this month?');
await page.keyboard.press('Enter');
await page.waitForTimeout(3000);
await page.screenshot({ path: 'screenshots/final_04_ai_chat.png' });

// Reports
await page.click('a[href="/reports"]');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1000);
await page.screenshot({ path: 'screenshots/final_05_reports.png' });

// Settings
await page.click('a[href="/settings"]');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1000);
await page.screenshot({ path: 'screenshots/final_06_settings.png' });

await browser.close();
console.log('All screenshots taken!');
