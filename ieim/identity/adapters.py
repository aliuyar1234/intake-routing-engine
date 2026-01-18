from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PolicyRecord:
    policy_id: str
    is_active: bool = True


@dataclass(frozen=True)
class ClaimRecord:
    claim_id: str
    is_open: bool = True


class PolicyAdapter(ABC):
    @abstractmethod
    def lookup_by_policy_number(self, *, policy_number: str) -> Optional[PolicyRecord]:
        raise NotImplementedError


class ClaimsAdapter(ABC):
    @abstractmethod
    def lookup_by_claim_number(self, *, claim_number: str) -> Optional[ClaimRecord]:
        raise NotImplementedError


class CRMAdapter(ABC):
    @abstractmethod
    def policy_numbers_for_sender_email(self, *, email: str) -> list[str]:
        raise NotImplementedError


@dataclass
class InMemoryPolicyAdapter(PolicyAdapter):
    """Stub policy adapter for tests and local runs."""

    valid_policy_numbers: Optional[set[str]] = None

    def lookup_by_policy_number(self, *, policy_number: str) -> Optional[PolicyRecord]:
        if self.valid_policy_numbers is not None and policy_number not in self.valid_policy_numbers:
            return None
        return PolicyRecord(policy_id=f"POL-{policy_number}", is_active=True)


@dataclass
class InMemoryClaimsAdapter(ClaimsAdapter):
    """Stub claims adapter for tests and local runs."""

    valid_claim_numbers: Optional[set[str]] = None

    def lookup_by_claim_number(self, *, claim_number: str) -> Optional[ClaimRecord]:
        claim_number = claim_number.upper()
        if self.valid_claim_numbers is not None and claim_number not in self.valid_claim_numbers:
            return None
        return ClaimRecord(claim_id=claim_number, is_open=True)


@dataclass
class InMemoryCRMAdapter(CRMAdapter):
    """Stub CRM adapter.

    Mapping is sender email -> associated policy numbers.
    """

    email_to_policy_numbers: dict[str, list[str]]

    def policy_numbers_for_sender_email(self, *, email: str) -> list[str]:
        values = self.email_to_policy_numbers.get(email, [])
        return sorted(values)

