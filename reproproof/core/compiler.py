"""Action Plan to Playwright JavaScript/TypeScript Compiler.

Compiles validated ActionPlan models into standalone, reproducible Playwright tests.
Enforces R3: Allowed actions only, strict escaping, and explicit assertion markers.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Tuple
from reproproof.core.schemas import ActionPlan, ActionStep


def escape_js_string(s: str) -> str:
    """Escapes strings for safe embedding in JavaScript code."""
    return json.dumps(s)


class PlaywrightCompiler:
    """Compiles an ActionPlan into a Playwright test script."""

    def compile_step(self, step: ActionStep, step_idx: int) -> str:
        """Translates an ActionStep into a Playwright statement."""
        action = step.action

        if action == "goto":
            path = step.path or "/"
            if not path.startswith("/"):
                path = "/" + path
            return f"  // Step {step_idx}: goto\n  await page.goto(baseURL + {escape_js_string(path)});\n"

        if action == "click":
            if step.role and step.name:
                role_lit = escape_js_string(step.role)
                name_lit = escape_js_string(step.name)
                return f"  // Step {step_idx}: click role {step.role} name {step.name}\n  await page.getByRole({role_lit}, {{ name: {name_lit} }}).click();\n"
            elif step.name:
                name_lit = escape_js_string(step.name)
                return f"  // Step {step_idx}: click text\n  await page.getByText({name_lit}).click();\n"
            elif step.selector:
                sel_lit = escape_js_string(step.selector)
                return f"  // Step {step_idx}: click selector\n  await page.locator({sel_lit}).click();\n"
            else:
                raise ValueError(f"Step {step_idx}: click requires role+name, name, or selector.")

        if action == "fill":
            sel_lit = escape_js_string(step.selector or "")
            val_lit = escape_js_string(step.value or "")
            return f"  // Step {step_idx}: fill\n  await page.locator({sel_lit}).fill({val_lit});\n"

        if action == "select":
            sel_lit = escape_js_string(step.selector or "")
            val_lit = escape_js_string(step.value or "")
            return f"  // Step {step_idx}: select\n  await page.locator({sel_lit}).selectOption({val_lit});\n"

        # Assertions
        if action == "assert_text_visible":
            text_lit = escape_js_string(step.text or "")
            return f"  // Assertion {step_idx}: assert_text_visible\n  // [INTENDED_ASSERTION: {step.action} text={step.text}]\n  await expect(page.getByText({text_lit})).toBeVisible();\n"

        if action == "assert_text_hidden":
            text_lit = escape_js_string(step.text or "")
            return f"  // Assertion {step_idx}: assert_text_hidden\n  // [INTENDED_ASSERTION: {step.action} text={step.text}]\n  await expect(page.getByText({text_lit})).toBeHidden();\n"

        if action == "assert_element_visible":
            sel_lit = escape_js_string(step.selector or "")
            return f"  // Assertion {step_idx}: assert_element_visible\n  // [INTENDED_ASSERTION: {step.action} selector={step.selector}]\n  await expect(page.locator({sel_lit})).toBeVisible();\n"

        if action == "assert_value_equals":
            sel_lit = escape_js_string(step.selector or "")
            val_lit = escape_js_string(step.value or "")
            return f"  // Assertion {step_idx}: assert_value_equals\n  // [INTENDED_ASSERTION: {step.action} selector={step.selector}]\n  await expect(page.locator({sel_lit})).toHaveValue({val_lit});\n"

        if action == "assert_url_contains":
            val_lit = escape_js_string(step.value or "")
            return f"  // Assertion {step_idx}: assert_url_contains\n  // [INTENDED_ASSERTION: {step.action} url={step.value}]\n  await expect(page).toHaveURL(new RegExp({val_lit}));\n"

        raise ValueError(f"Unsupported action type: {action}")

    def compile(
        self,
        plan: ActionPlan,
        test_name: str = "reproduction-test",
        screenshot_path: str = "repro-screenshot.png",
    ) -> Tuple[str, str]:
        """Compiles an ActionPlan into Playwright JavaScript test code.
        
        Returns: (test_code, sha256_hash)
        """
        lines = [
            "// Auto-generated frozen test by ReproProof compiler",
            "// Once approved by a human, this file is immutable.",
            "const { test, expect } = require('@playwright/test');",
            "",
            f"test('{test_name}', async ({{ page, baseURL }}) => {{",
            "  // Reset state before running reproduction if available",
            "  try { await page.request.post(`${baseURL}/api/reset`); } catch (e) {}",
            "",
        ]

        # Add steps
        for idx, step in enumerate(plan.steps, start=1):
            lines.append(self.compile_step(step, idx))

        # Screenshot before final assertions
        escaped_ss = escape_js_string(screenshot_path)
        lines.append(f"  // Capture screenshot of defect state\n  await page.screenshot({{ path: {escaped_ss}, fullPage: true }});\n")

        # Add assertions
        for idx, assertion in enumerate(plan.assertions, start=len(plan.steps) + 1):
            lines.append(self.compile_step(assertion, idx))

        lines.append("});")
        lines.append("")

        code = "\n".join(lines)
        sha256 = hashlib.sha256(code.encode("utf-8")).hexdigest()
        return code, sha256
