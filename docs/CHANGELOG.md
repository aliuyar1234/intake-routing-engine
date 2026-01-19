# Changelog

All notable changes to Intake Routing Engine (IEIM) are documented here.

This project follows Semantic Versioning.

## 1.0.5

- Added LLM-first pipeline mode with explicit confidence thresholds and deterministic fail-closed gates.
- Added pipeline mode configuration and LLM threshold configuration to runtime configs.
- Default pipeline mode in provided configs and Helm values is now LLM_FIRST (LLM still disabled until configured).

## 1.0.4

- Renamed the GitHub repository to `intake-routing-engine` and updated internal identifiers and docs.

## 1.0.3

- Renamed the GitHub repository (intermediate) and updated internal identifiers and docs.
- Fixed Mermaid rendering in `spec/02_ARCHITECTURE.md`.

## 1.0.2

- Manifest hashing is stable across platforms (LF normalization) and ignores runtime output directories.
- Added a manifest regeneration helper script and release engineering improvements (SBOMs, signing, upgrade checks).
- Added performance/load-test profiles and scaling guidance.

## 1.0.1

- Initial SSOT pack v1.0.1 with schemas, verification scripts, and a phase-by-phase reference implementation.
