{
  "task": "classify",
  "instructions": [
    "Return JSON only.",
    "Classify the provided email into intents (multi-label), one primary_intent, product_line, urgency, and risk_flags.",
    "Use only labels from canonical_labels provided in the input.",
    "Provide confidence values in [0,1].",
    "Provide short evidence snippets (strings) that appear verbatim in the canonicalized subject/body or attachment extracted text."
  ],
  "input": {
    "normalized_message": "{{NORMALIZED_MESSAGE_JSON}}",
    "attachment_texts": "{{ATTACHMENT_TEXTS_JSON}}",
    "canonical_labels": "{{CANONICAL_LABELS_JSON}}"
  },
  "output_contract": "ClassifyLLMOutput v1.0.0 as defined in prompts/prompt_contract.md"
}
