{
  "task": "identity_assist",
  "instructions": [
    "Return JSON only.",
    "Propose candidate lookup keys (policy numbers, claim numbers, customer numbers, email addresses) extracted from the email.",
    "Do not decide the final identity. Your output is advisory and must be validated deterministically by the identity service.",
    "Include evidence snippets for each proposed key."
  ],
  "input": {
    "normalized_message": "{{NORMALIZED_MESSAGE_JSON}}",
    "attachment_texts": "{{ATTACHMENT_TEXTS_JSON}}"
  },
  "output_contract": "IdentityAssistLLMOutput v1.0.0 as defined in prompts/prompt_contract.md"
}
