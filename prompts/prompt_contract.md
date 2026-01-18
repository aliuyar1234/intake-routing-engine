# Prompt contract

This file defines how IEIM interacts with LLMs in a safe, schema-gated manner.

## Hard requirements

1. Output must be JSON only (no Markdown, no prose).
2. Outputs must validate against the contract schema below.
3. Outputs must use only canonical labels provided at runtime.
4. Any schema validation failure triggers a deterministic retry policy; persistent failure results in fail-closed review.

## Retry policy

- Attempt 1: call with temperature configured for the environment.
- Attempt 2: temperature forced to 0.0 and a shortened input.
- If still invalid: stop and mark the stage as needs review.

## Refusal/unsafe handling

If the model refuses or returns a non-JSON response, treat it as failure and fail closed.

## Token budgets

Token budgets are enforced by configuration and logged in audit events.

## Contract schemas (LLM outputs)

These contracts are **not** the same as the system’s core result schemas in `schemas/`. The pipeline converts these outputs into audited, schema-validated results by:
- validating the contract
- mapping evidence snippets to offsets and snippet hashes deterministically
- enforcing canonical label membership (from `spec/00_CANONICAL.md`)

### ClassifyLLMOutput v1.0.0

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["intents", "primary_intent", "product_line", "urgency", "risk_flags"],
  "properties": {
    "intents": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["label", "confidence", "evidence_snippets"],
        "properties": {
          "label": {"type": "string"},
          "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
          "evidence_snippets": {"type": "array", "items": {"type": "string", "maxLength": 200}}
        }
      }
    },
    "primary_intent": {"type": "string"},
    "product_line": {
      "type": "object",
      "additionalProperties": false,
      "required": ["label", "confidence", "evidence_snippets"],
      "properties": {
        "label": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "evidence_snippets": {"type": "array", "items": {"type": "string", "maxLength": 200}}
      }
    },
    "urgency": {
      "type": "object",
      "additionalProperties": false,
      "required": ["label", "confidence", "evidence_snippets"],
      "properties": {
        "label": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "evidence_snippets": {"type": "array", "items": {"type": "string", "maxLength": 200}}
      }
    },
    "risk_flags": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["label", "confidence", "evidence_snippets"],
        "properties": {
          "label": {"type": "string"},
          "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
          "evidence_snippets": {"type": "array", "items": {"type": "string", "maxLength": 200}}
        }
      }
    }
  }
}
```

### ExtractLLMOutput v1.0.0

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["entities"],
  "properties": {
    "entities": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["entity_type", "value_redacted", "confidence", "evidence_snippets"],
        "properties": {
          "entity_type": {"type": "string"},
          "value_redacted": {"type": "string", "maxLength": 200},
          "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
          "evidence_snippets": {"type": "array", "items": {"type": "string", "maxLength": 200}}
        }
      }
    }
  }
}
```

### IdentityAssistLLMOutput v1.0.0

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["keys"],
  "properties": {
    "keys": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["key_type", "key_value", "evidence_snippets"],
        "properties": {
          "key_type": {"type": "string"},
          "key_value": {"type": "string", "maxLength": 200},
          "evidence_snippets": {"type": "array", "items": {"type": "string", "maxLength": 200}}
        }
      }
    }
  }
}
```
