# Key rotation

## Key types

- Storage encryption keys (KMS/HSM)
- Service-to-service mTLS certificates
- API tokens for ingestion and case system adapters
- LLM gateway credentials

## Rotation procedure

1. Create new key versions in KMS/HSM.
2. Update services to accept both old and new keys (read old, write new).
3. Re-encrypt newly written objects with the new key version.
4. Validate access and audit logs.
5. Retire old key version after the configured safety window.

## Audit

Every rotation must be recorded as an audit event with actor identity and configuration hashes.
