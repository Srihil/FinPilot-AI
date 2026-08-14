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

await page.screenshot({ path: 'screenshots/10_dashboard_charts.png', fullPage: true });
console.log('Dashboard screenshot taken');

// Customers
await page.click('a[href="/customers"]');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(2000);
await page.screenshot({ path: 'screenshots/11_customers.png' });
console.log('Customers page URL:', page.url());

// Analytics  
await page.click('a[href="/analytics"]');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(2000);
await page.screenshot({ path: 'screenshots/12_analytics.png' });
console.log('Analytics page URL:', page.url());

// Settings
await page.click('a[href="/settings"]');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1000);
await page.screenshot({ path: 'screenshots/13_settings.png' });

await browser.close();
console.log('Done!');
