import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

const apiErrors = [];
page.on('response', async resp => {
  if (!resp.ok() && resp.url().includes('/api/')) {
    const body = await resp.text().catch(() => '');
    apiErrors.push(`${resp.status()} ${resp.url()}: ${body.slice(0, 200)}`);
  }
});

await page.goto('http://localhost:3000/signup');
await page.waitForLoadState('networkidle');

const uid = Date.now();
await page.fill('input[name="full_name"]', 'Test Brand Owner');
await page.fill('input[name="email"]', `owner${uid}@brand.com`);
await page.fill('input[name="company_name"]', 'BrandCo Pvt Ltd');
await page.fill('input[name="password"]', 'SecurePass@99');
await page.fill('input[name="confirm_password"]', 'SecurePass@99');
await page.locator('input[name="terms"]').check();

await page.screenshot({ path: 'screenshots/signup_filled.png' });
await page.locator('button[type="submit"]').click();
await page.waitForTimeout(5000);

console.log('URL after submit:', page.url());
console.log('API errors:', apiErrors.length ? apiErrors : 'none');
await page.screenshot({ path: 'screenshots/signup_result.png' });

await browser.close();
