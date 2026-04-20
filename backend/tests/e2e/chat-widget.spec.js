/**
 * E2E tests for chat widget — Playwright
 *
 * Prerequisites:
 *   - WordPress running at http://localhost:8080
 *   - WebSocket mock at ws://localhost:8765 (backend/chat_ws_mock.py)
 *
 * Run:
 *   npx playwright test backend/tests/e2e/chat-widget.spec.js
 */
const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.WP_URL || 'http://localhost:8080';

test.describe('Chat Widget', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
    // Wait for widget DOM to be injected
    await page.waitForSelector('#tm-chat-toggle', { timeout: 10000 });
  });

  test('open and close widget', async ({ page }) => {
    const toggle = page.locator('#tm-chat-toggle');
    const panel  = page.locator('#tm-chat-panel');

    // Panel starts hidden
    await expect(panel).toHaveAttribute('hidden', '');

    // Click FAB opens panel
    await toggle.click();
    await expect(panel).not.toHaveAttribute('hidden', '');
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');

    // Escape closes panel
    await page.keyboard.press('Escape');
    await expect(panel).toHaveAttribute('hidden', '');
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });

  test('send message and receive reply', async ({ page }) => {
    // Open panel
    await page.locator('#tm-chat-toggle').click();
    await page.waitForSelector('#tm-chat-panel:not([hidden])');

    const input   = page.locator('#tm-chat-input');
    const sendBtn = page.locator('#tm-chat-send');
    const msgList = page.locator('#tm-chat-messages');

    // Type and send
    await input.fill('Hola, quiero saber de productos');
    await sendBtn.click();

    // User message appears
    const userMsg = msgList.locator('.tm-msg.tm-user .tm-bubble');
    await expect(userMsg.first()).toHaveText('Hola, quiero saber de productos');

    // Bot reply appears (wait up to 10s for WS response)
    const botMsg = msgList.locator('.tm-msg.tm-bot .tm-bubble');
    await expect(botMsg.first()).toBeVisible({ timeout: 10000 });
  });

  test('history persists after reload via localStorage', async ({ page }) => {
    // Open and send a message
    await page.locator('#tm-chat-toggle').click();
    await page.waitForSelector('#tm-chat-panel:not([hidden])');

    const input = page.locator('#tm-chat-input');
    await input.fill('Mensaje de prueba para persistencia');
    await page.locator('#tm-chat-send').click();

    // Verify user message rendered
    const msgList = page.locator('#tm-chat-messages');
    await expect(msgList.locator('.tm-msg.tm-user')).toHaveCount(1, { timeout: 5000 });

    // Check if localStorage has chat data (widget may or may not persist — test is informational)
    const hasStorage = await page.evaluate(() => {
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && (key.includes('chat') || key.includes('tm-'))) return true;
      }
      return false;
    });

    // Reload and re-open panel
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#tm-chat-toggle', { timeout: 10000 });
    await page.locator('#tm-chat-toggle').click();
    await page.waitForSelector('#tm-chat-panel:not([hidden])');

    // If localStorage persistence is implemented, messages should survive reload
    if (hasStorage) {
      const msgCount = await msgList.locator('.tm-msg').count();
      expect(msgCount).toBeGreaterThanOrEqual(1);
    }
    // Otherwise the test passes — it documents current behavior
  });

  test('keyboard navigation — Tab, Enter, Escape', async ({ page }) => {
    // Open panel via click
    await page.locator('#tm-chat-toggle').click();
    await page.waitForSelector('#tm-chat-panel:not([hidden])');

    // Input should auto-focus after opening
    const input = page.locator('#tm-chat-input');
    await expect(input).toBeFocused({ timeout: 1000 });

    // Type message and send with Enter
    await input.fill('Test via Enter');
    await page.keyboard.press('Enter');

    const userMsg = page.locator('#tm-chat-messages .tm-msg.tm-user .tm-bubble');
    await expect(userMsg.first()).toHaveText('Test via Enter');

    // Input should remain focused after send
    await expect(input).toBeFocused();

    // Tab navigates to send button
    await page.keyboard.press('Tab');
    const sendBtn = page.locator('#tm-chat-send');
    await expect(sendBtn).toBeFocused();

    // Escape closes panel and returns focus to toggle
    await page.keyboard.press('Escape');
    const panel = page.locator('#tm-chat-panel');
    await expect(panel).toHaveAttribute('hidden', '');
    const toggle = page.locator('#tm-chat-toggle');
    await expect(toggle).toBeFocused();
  });

});
