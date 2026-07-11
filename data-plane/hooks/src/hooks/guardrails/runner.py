"""Apply the guardrails configured on a policy to an input/output stage.

Policy.guardrails shape::

    {
      "input":  {"pii": "redact"|"block"|"off", "injection": "block"|"off"},
      "output": {"pii": "redact"|"block"|"off", "schema": {<json schema>}},
      "fail":   "closed"|"open"   # behavior when a guardrail itself errors
    }
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hooks.guardrails import injection, pii, schema


@dataclass(frozen=True)
class GuardrailOutcome:
    allowed: bool
    text: str
    reasons: list[str]


def run(stage: str, config: dict[str, Any], text: str) -> GuardrailOutcome:
    fail = config.get("fail", "closed")
    stage_cfg = config.get(stage, {})
    reasons: list[str] = []
    out = text
    try:
        pii_action = stage_cfg.get("pii", "off")
        if pii_action != "off":
            found = pii.scan(out)
            if found and pii_action == "block":
                return GuardrailOutcome(False, out, [f"pii:{','.join(found)}"])
            if found and pii_action == "redact":
                out = pii.redact(out)
                reasons.append(f"pii-redacted:{','.join(found)}")

        if stage_cfg.get("injection", "off") == "block" and injection.detect(out):
            return GuardrailOutcome(False, out, ["injection"])

        schema_spec = stage_cfg.get("schema")
        if schema_spec:
            ok, err = schema.validate(out, schema_spec)
            if not ok:
                return GuardrailOutcome(False, out, [f"schema:{err}"])
    except Exception as exc:  # a guardrail itself failed
        if fail == "open":
            return GuardrailOutcome(True, text, [f"guardrail-error-ignored:{exc}"])
        return GuardrailOutcome(False, text, [f"guardrail-error:{exc}"])

    return GuardrailOutcome(True, out, reasons)
