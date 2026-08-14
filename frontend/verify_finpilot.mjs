import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
page.setDefaultTimeout(12000);

try {
  // 1. Landing page
  await page.goto('http://localhost:3000');
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: 'screenshots/01_landing.png' });
  const title = await page.title();
  console.log('1. Landing title:', title);
  const bodyText = await page.locator('body').innerText();
  console.log('   Has FinPilot:', bodyText.includes('FinPilot'));
  console.log('   Has hero text:', bodyText.toLowerCase().includes('finance') || bodyText.toLowerCase().includes('ai'));

  // 2. Login page
  await page.goto('http://localhost:3000/login');
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: 'screenshots/02_login.png' });
  console.log('2. Login page loaded at:', page.url());

  await page.locator('input[type="email"]').fill('admin@acmemfg.in');
  await page.locator('input[type="password"]').fill('Admin@123');
  await page.screenshot({ path: 'screenshots/03_login_filled.png' });
  await page.locator('button[type="submit"]').click();
  await page.waitForTimeout(4000);
  console.log('3. After login URL:', page.url());
  await page.screenshot({ path: 'screenshots/04_after_login.png' });

  // 4. Dashboard
  await page.waitForTimeout(2000);
  const dashText = await page.locator('body').innerText();
  console.log('4. Has Revenue:', dashText.includes('Revenue'));
  console.log('   Has Customers in sidebar:', dashText.includes('Customers'));
  console.log('   Has AI Assistant:', dashText.includes('Assistant') || dashText.includes('AI'));
  await page.screenshot({ path: 'screenshots/05_dashboard.png' });

  // 5. Navigate to AI Assistant
  const navLinks = page.locator('a, button').filter({ hasText: /assistant|ai/i });
  const count = await navLinks.count();
  console.log('5. AI assistant nav links found:', count);
  if (count > 0) {
    await navLinks.first().click();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'screenshots/06_ai_assistant.png' });
    console.log('   AI Assistant page URL:', page.url());
  }

} catch (e) {
  console.error('Error:', e.message);
  await page.screenshot({ path: 'screenshots/error.png' }).catch(() => {});
} finally {
  await browser.close();
}
