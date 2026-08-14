import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

const errors = [];
page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
page.on('response', resp => {
  if (!resp.ok() && resp.url().includes('/api/')) {
    console.log(`API ${resp.status()} on ${resp.url()}`);
  }
});

// Try port 3000 where the updated build is served
await page.goto('http://localhost:3000/signup');
await page.waitForLoadState('networkidle');
await page.screenshot({ path: 'screenshots/signup_p3000.png' });

const pwFields = await page.locator('input[type="password"]').all();
await page.fill('input[type="email"]', `owner_${Date.now()}@brand.com`);
// Fill by name attribute or placeholder
const nameInput = page.locator('input').first();
await nameInput.fill('Brand Owner');

// Better: fill each visible input in order
const inputs = await page.locator('input:visible').all();
console.log('Input count:', inputs.length);
for (const inp of inputs) {
  const type = await inp.getAttribute('type');
  const name = await inp.getAttribute('name');
  const placeholder = await inp.getAttribute('placeholder') || '';
  console.log(`  type=${type} name=${name} placeholder=${placeholder.slice(0,30)}`);
}

await browser.close();
