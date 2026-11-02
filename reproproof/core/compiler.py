"""Action Plan to Playwright JavaScript Test Compiler.

Security Invariant: Safe Structured Data Serialization.
Model outputs are NEVER interpolated into executable JavaScript source or comments.
Instead, the compiler embeds the validated ActionPlan as pure JSON data within
a fixed, audited static Playwright driver loop.
"""

from __future__ import annotations

import hashlib
import json
from typing import Tuple
from reproproof.core.schemas import ActionPlan


class PlaywrightCompiler:
    """Compiles an ActionPlan into an immutable, data-driven Playwright test."""

    STATIC_TEST_DRIVER = """// Auto-generated frozen test driver by ReproProof compiler
// Security Invariant: Plan is data-driven JSON, never dynamically evaluated code.
const { test, expect } = require('@playwright/test');

const PLAN = JSON.parse(__PLAN_JSON_LITERAL__);

test('__TEST_NAME__', async ({ page, baseURL }) => {
  // Reset state before running reproduction if available
  try {
    await page.request.post(`${baseURL}/api/reset`);
  } catch (e) {}

  // 1. Execute Action Steps
  for (let i = 0; i < PLAN.steps.length; i++) {
    const step = PLAN.steps[i];
    if (step.action === 'goto') {
      const targetUrl = new URL(step.path || '/', baseURL).toString();
      await page.goto(targetUrl);
    } else if (step.action === 'click') {
      if (step.role && step.name) {
        await page.getByRole(step.role, { name: step.name }).first().click();
      } else if (step.name) {
        await page.getByText(step.name).first().click();
      } else if (step.selector) {
        await page.locator(step.selector).first().click();
      }
    } else if (step.action === 'fill') {
      await page.locator(step.selector).first().fill(step.value || '');
    } else if (step.action === 'select') {
      await page.locator(step.selector).first().selectOption(step.value || '');
    }
  }

  // 2. Capture Screenshot of Defect State
  if (PLAN.screenshot_path) {
    await page.screenshot({ path: PLAN.screenshot_path, fullPage: true });
  }

  // 3. Execute Assertions
  for (let i = 0; i < PLAN.assertions.length; i++) {
    const a = PLAN.assertions[i];
    if (a.action === 'assert_text_visible') {
      const loc = (a.exact !== undefined && a.exact !== null) ? page.getByText(a.text, { exact: a.exact }) : page.getByText(a.text);
      await expect(loc.first()).toBeVisible();
    } else if (a.action === 'assert_text_hidden') {
      const loc = (a.exact !== undefined && a.exact !== null) ? page.getByText(a.text, { exact: a.exact }) : page.getByText(a.text);
      await expect(loc.first()).toBeHidden();
    } else if (a.action === 'assert_element_visible') {
      await expect(page.locator(a.selector).first()).toBeVisible();
    } else if (a.action === 'assert_value_equals') {
      await expect(page.locator(a.selector).first()).toHaveValue(a.value || '');
    } else if (a.action === 'assert_url_contains') {
      const escapedVal = (a.value || '').replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
      await expect(page).toHaveURL(new RegExp(escapedVal));
    }
  }
});
"""

    def compile(
        self,
        plan: ActionPlan,
        test_name: str = "reproduction-test",
        screenshot_path: str = "repro-screenshot.png",
    ) -> Tuple[str, str]:
        """Compiles an ActionPlan into a safe data-driven Playwright test.

        Returns: (test_code, sha256_hash)
        """
        # Serialize plan into a dictionary with screenshot_path
        plan_dict = plan.model_dump()
        plan_dict["screenshot_path"] = screenshot_path

        # Serialize as strict JSON literal (double json.dumps produces a safe JS string literal)
        raw_json = json.dumps(plan_dict, ensure_ascii=False)
        escaped_literal = json.dumps(raw_json)

        # Sanitize test_name: alphanumeric and dashes only
        safe_test_name = "".join(c for c in test_name if c.isalnum() or c in "-_") or "repro-test"

        code = self.STATIC_TEST_DRIVER.replace("__PLAN_JSON_LITERAL__", escaped_literal)
        code = code.replace("__TEST_NAME__", safe_test_name)

        sha256 = hashlib.sha256(code.encode("utf-8")).hexdigest()
        return code, sha256
