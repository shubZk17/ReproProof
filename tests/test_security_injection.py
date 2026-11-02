"""Adversarial security unit tests verifying prompt-injection-to-RCE defense."""

import json
import pytest
from reproproof.core.schemas import ActionPlan, ActionStep
from reproproof.core.compiler import PlaywrightCompiler


def test_adversarial_code_injection_in_text():
    """Ensure malicious JS/shell payloads in text fields are safely serialized as JSON."""
    payload = "'; require('child_process').execSync('calc.exe'); //\n\r\u2028\u2029*/</script>"
    plan = ActionPlan(
        expected_behavior="Target behavior",
        steps=[{"action": "goto", "path": "/"}],
        assertions=[{"action": "assert_text_visible", "text": payload}],
    )

    compiler = PlaywrightCompiler()
    code, sha256 = compiler.compile(plan)

    # Must contain the static safe driver
    assert "const PLAN = JSON.parse(" in code
    # The payload MUST NOT appear outside the JSON string literal
    assert "require('child_process')" not in code.split("const PLAN = JSON.parse(")[0]
    # The payload must be embedded inside the JSON string literal
    assert len(sha256) == 64

    # Extract the literal and verify JSON parsing reconstructs the exact string
    # Find argument to JSON.parse(
    prefix = "const PLAN = JSON.parse("
    start = code.index(prefix) + len(prefix)
    end = code.rindex(");\n\ntest(")
    json_literal_str = code[start:end]

    # Evaluating the literal through json.loads (same as JS string literal parsing)
    parsed_inner = json.loads(json_literal_str)
    reconstructed_dict = json.loads(parsed_inner)
    assert reconstructed_dict["assertions"][0]["text"] == payload


def test_adversarial_malicious_path_rejected():
    """Ensure javascript: or absolute URLs with protocols are rejected by schema."""
    with pytest.raises(ValueError, match="Path must be a relative URL"):
        ActionStep(action="goto", path="javascript:alert(1)")

    with pytest.raises(ValueError, match="Path must be a relative URL"):
        ActionStep(action="goto", path="http://attacker.com/steal")

    with pytest.raises(ValueError, match="Path must be a relative URL"):
        ActionStep(action="goto", path="data:text/html,<script>alert(1)</script>")


def test_adversarial_invalid_role_rejected():
    """Ensure invalid or malicious ARIA roles are rejected by schema."""
    with pytest.raises(ValueError, match="Role .* is not an allowlisted ARIA role"):
        ActionStep(action="click", role="arbitrary_payload", name="Submit")


def test_adversarial_missing_required_fields():
    """Ensure malformed action objects missing required targets fail validation."""
    with pytest.raises(ValueError, match="requires both 'selector' and 'value'"):
        ActionStep(action="fill", selector="#input")

    with pytest.raises(ValueError, match="requires 'text'"):
        ActionStep(action="assert_text_visible")
