# Test strategy

This strategy defines the tests and gates required for IEIM.

## Test layers

### Unit tests
- Canonicalization functions
- Hashing and RFC8785 JSON canonicalization
- Routing rule evaluation
- Identity scoring and threshold logic

### Integration tests
- Ingestion adapters against stubs
- CRM/Policy/Claims lookups against stubs
- Case adapter against stub
- AV and OCR tool integration stubs

### End-to-end tests
An end-to-end run uses the sample corpus in `data/samples/` and compares outputs against `data/samples/gold/`.

## Coverage targets
- Contract coverage: 100% (all stage outputs schema validated)
- Routing decision coverage: all routing rules hit by at least one sample
- Fail-closed coverage: all negative cases produce review outcomes

## Synthetic test data generator spec
A generator must be able to emit:
- emails with thread keys
- attachments with extracted text
- multilingual content
- high-risk cases (legal, GDPR, malware)

The generator must be deterministic given a seed.
