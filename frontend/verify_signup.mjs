import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

// Capture console errors
const errors = [];
page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
page.on('pageerror', err => errors.push(err.message));

await page.goto('http://localhost:3001/signup');
await page.waitForLoadState('networkidle');

// Fill signup form
await page.fill('input[name="full_name"], input[placeholder*="name" i]', 'Test Owner');
await page.fill('input[type="email"]', `owner_${Date.now()}@testbiz.com`);
await page.fill('input[name="company_name"], input[placeholder*="company" i]', 'TestBiz Pvt Ltd');

// Find password fields
const pwFields = await page.locator('input[type="password"]').all();
await pwFields[0].fill('SecurePass@99');
if (pwFields[1]) await pwFields[1].fill('SecurePass@99');

// Check terms checkbox if present
const checkbox = page.locator('input[type="checkbox"]').first();
if (await checkbox.isVisible()) await checkbox.check();

await page.screenshot({ path: 'screenshots/signup_before.png' });
await page.locator('button[type="submit"]').click();
await page.waitForTimeout(4000);

console.log('After submit URL:', page.url());
await page.screenshot({ path: 'screenshots/signup_after.png' });

const relevant = errors.filter(e => !e.includes('runtime.lastError') && !e.includes('favicon'));
console.log('Console errors:', relevant.length ? relevant : 'none');

await browser.close();
