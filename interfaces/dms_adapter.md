# DMS/ECM adapter interface (optional)

This interface is optional. It is used when the organization requires storing documents in a DMS/ECM system.

## Required operations

- store_document
- link_document_to_case
- retrieve_document_metadata

## Security

- Documents must be stored encrypted.
- Access must be controlled via RBAC and recorded in audit events.
