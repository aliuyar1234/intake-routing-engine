# Cost controls

## Guardrails

- Max LLM calls per day (config)
- Token budgets per stage (classify/extract/assist)
- Cache TTL and cache hit rate targets
- Disable LLM automatically on cost anomaly detection

## Monitoring

- cost_per_email
- token_usage_per_stage
- cache_hit_rate

## Response to anomaly

1. Disable LLM in config and redeploy.
   - Alternatively, set `incident.disable_llm: true` as an emergency kill-switch.
2. Route uncertain classifications to HITL.
3. Review prompts and input size constraints.
4. Document cause and add regression tests.
