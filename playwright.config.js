// Root Playwright configuration for ReproProof runner
const { defineConfig, devices } = require('@playwright/test');

// Prevent runs/ from being included in default Playwright test discovery
// Only runner processes with PLAYWRIGHT_ALLOW_RUNS=1 execute test files in runs/
const allowRuns = process.env.PLAYWRIGHT_ALLOW_RUNS === '1';

module.exports = defineConfig({
  testDir: '.',
  testMatch: /.*\.spec\.(js|ts)/,
  testIgnore: allowRuns ? [] : ['runs/**', '**/runs/**'],
  timeout: 30000,
  expect: {
    timeout: 5000,
  },
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    headless: true,
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
