const { test, expect } = require('@playwright/test');

test.describe('Protected Inventory Regression Checks', () => {
  test.beforeEach(async ({ request, baseURL }) => {
    // Reset inventory state before each test
    await request.post(`${baseURL}/api/reset`);
  });

  test('R1: catalog loads and displays initial items', async ({ page, baseURL }) => {
    await page.goto(baseURL + '/');
    await expect(page.getByText('Warehouse Inventory')).toBeVisible();
    await expect(page.getByText('Widget A', { exact: true })).toBeVisible();
    await expect(page.getByText('Widget B', { exact: true })).toBeVisible();
    await expect(page.getByText('Widget C', { exact: true })).toBeVisible();
  });

  test('R2: can add a new item to catalog', async ({ page, baseURL }) => {
    await page.goto(baseURL + '/');
    await page.fill('#item-name', 'Widget Gamma');
    await page.fill('#item-count', '42');
    await page.click('#btn-add-item');
    await expect(page.getByText('Widget Gamma', { exact: true })).toBeVisible();
    await expect(page.getByText('42', { exact: true })).toBeVisible();
  });
});
