{
  "task": "extract",
  "instructions": [
    "Return JSON only.",
    "Extract entities from the provided email and attachment texts.",
    "Use only entity types from canonical_labels provided in the input.",
    "For sensitive values (e.g. bank details), provide redacted forms and do not include the full value unless explicitly permitted by input policy.",
    "This system may receive German emails. Do not translate; extract values as they appear in the text.",
    "Include evidence snippets that appear verbatim in the canonicalized texts.",
    "Evidence snippets must be exact substrings copied from subject_c14n, body_text_c14n, or attachment text; do not paraphrase or normalize.",
    "If you cannot find a good snippet, copy the first 20 characters from body_text_c14n as the evidence_snippet.",
    "If unsure about an entity, omit it rather than guessing."
  ],
  "input": {
    "normalized_message": "{{NORMALIZED_MESSAGE_JSON}}",
    "attachment_texts": "{{ATTACHMENT_TEXTS_JSON}}",
    "canonical_labels": "{{CANONICAL_LABELS_JSON}}",
    "policies": "{{EXTRACTION_POLICY_JSON}}"
  },
  "output_contract": "ExtractLLMOutput v1.0.0 as defined in prompts/prompt_contract.md"
}
