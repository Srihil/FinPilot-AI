import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

// Track API responses
const apiResponses = [];
page.on('response', async resp => {
  if (resp.url().includes('/api/assistant')) {
    const body = await resp.text().catch(() => '');
    apiResponses.push({ url: resp.url(), status: resp.status(), body: body.slice(0, 200) });
  }
});

await page.goto('http://localhost:3000/login');
await page.waitForLoadState('networkidle');
await page.fill('input[type="email"]', 'admin@acmemfg.in');
await page.fill('input[type="password"]', 'Admin@123');
await page.locator('button[type="submit"]').click();
await page.waitForURL('**/dashboard', { timeout: 10000 });

await page.goto('http://localhost:3000/assistant');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(2000);
await page.screenshot({ path: 'screenshots/assistant_loaded.png' });

// Click New Conversation
await page.click('button:has-text("New Conversation")');
await page.waitForTimeout(2000);
await page.screenshot({ path: 'screenshots/assistant_new_conv.png' });

// Now find the textarea and type
const textarea = await page.locator('textarea').first();
await textarea.click();
await textarea.fill('What was our revenue this month?');
await page.screenshot({ path: 'screenshots/assistant_typed.png' });

// Press Enter to send
await textarea.press('Enter');
await page.waitForTimeout(6000);
await page.screenshot({ path: 'screenshots/assistant_response.png' });

console.log('API calls:', apiResponses.map(r => `${r.status} ${r.url.split('/').slice(-2).join('/')}`));

await browser.close();
