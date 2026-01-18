{
  "task": "extract",
  "instructions": [
    "Return JSON only.",
    "Extract entities from the provided email and attachment texts.",
    "Use only entity types from canonical_labels provided in the input.",
    "For sensitive values (e.g. bank details), provide redacted forms and do not include the full value unless explicitly permitted by input policy.",
    "Include evidence snippets that appear verbatim in the canonicalized texts."
  ],
  "input": {
    "normalized_message": "{{NORMALIZED_MESSAGE_JSON}}",
    "attachment_texts": "{{ATTACHMENT_TEXTS_JSON}}",
    "canonical_labels": "{{CANONICAL_LABELS_JSON}}",
    "policies": "{{EXTRACTION_POLICY_JSON}}"
  },
  "output_contract": "ExtractLLMOutput v1.0.0 as defined in prompts/prompt_contract.md"
}
