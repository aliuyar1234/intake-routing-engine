{
  "task": "classify",
  "instructions": [
    "Return JSON only.",
    "Classify the provided email into intents (multi-label), one primary_intent, product_line, urgency, and risk_flags.",
    "Use only labels from canonical_labels provided in the input.",
    "Provide confidence values in [0,1].",
    "This system may receive German emails. Do not translate; classify based on meaning while keeping labels in canonical form.",
    "Provide short evidence snippets that appear verbatim in the canonicalized subject/body or attachment extracted text.",
    "Evidence snippets must be exact substrings copied from subject_c14n, body_text_c14n, or attachment text; do not paraphrase or normalize.",
    "If you cannot find a good snippet, copy the first 20 characters from body_text_c14n as the evidence_snippet.",
    "If unsure, use conservative defaults: INTENT_GENERAL_INQUIRY, PROD_UNKNOWN, URG_NORMAL, and no risk_flags, but still include evidence snippets from the input."
  ],
  "input": {
    "normalized_message": "{{NORMALIZED_MESSAGE_JSON}}",
    "attachment_texts": "{{ATTACHMENT_TEXTS_JSON}}",
    "canonical_labels": "{{CANONICAL_LABELS_JSON}}"
  },
  "output_contract": "ClassifyLLMOutput v1.0.0 as defined in prompts/prompt_contract.md"
}
