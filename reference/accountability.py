"""Fail-closed accountability review contract for private writes.

Cryptography cannot decide whether prose contains a commitment, error, task,
relationship boundary, or safety issue.  A caller-supplied flag would merely
move that decision back to the writer.  This module instead defines a trusted
guard that reviews every plaintext write and, when necessary, records a
minimal durable entry in the ordinary accountability system before sealing the
private body.

The reference implementation deliberately does not provide a semantic
classifier or ordinary ledger.  Deployments must inject both through
``AccountabilityGuard`` and must not expose the resulting receipt as a tool
argument that the writer can forge.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class AccountabilityClass(str, Enum):
    """Result of an independent pre-seal responsibility review."""

    PRIVATE_ONLY = "private_only"
    COMMITMENT = "commitment"
    ERROR = "error"
    TASK = "task"
    RELATIONSHIP_BOUNDARY = "relationship_boundary"
    PROJECT_CHANGE = "project_change"
    MAJOR_DECISION = "major_decision"
    SAFETY = "safety"
    CREDENTIAL = "credential"
    THIRD_PARTY_PRIVATE = "third_party_private"
    HIDDEN_REASONING = "hidden_reasoning"


ACCOUNTABLE_CLASSES = frozenset(
    {
        AccountabilityClass.COMMITMENT,
        AccountabilityClass.ERROR,
        AccountabilityClass.TASK,
        AccountabilityClass.RELATIONSHIP_BOUNDARY,
        AccountabilityClass.PROJECT_CHANGE,
        AccountabilityClass.MAJOR_DECISION,
        AccountabilityClass.SAFETY,
    }
)

PROHIBITED_CLASSES = frozenset(
    {
        AccountabilityClass.CREDENTIAL,
        AccountabilityClass.THIRD_PARTY_PRIVATE,
        AccountabilityClass.HIDDEN_REASONING,
    }
)

MAX_ORDINARY_RECORD_REF_BYTES = 1024
_CORRELATION_ID = re.compile(r"[0-9a-f]{32}\Z")


class AccountabilityError(Exception):
    """Base error for accountability review and receipt validation."""


class AccountabilityConfigurationError(AccountabilityError):
    """No trusted accountability guard is configured for writes."""


class AccountabilityReviewError(AccountabilityError):
    """The guard failed or returned a receipt that cannot authorize sealing."""


class ProhibitedPrivateContentError(AccountabilityError):
    """The reviewed content class must not be stored in the private space."""


@dataclass(frozen=True)
class AccountabilityReceipt:
    """A guard-issued result, optionally linked to an ordinary ledger record.

    ``ordinary_record_ref`` is required for accountable classes and forbidden
    for ``private_only``.  The referenced ordinary record must preserve enough
    non-private information to track the responsibility; a fabricated URI or
    bare boolean does not satisfy the contract.
    """

    classification: AccountabilityClass | str
    correlation_id: str
    ordinary_record_ref: str | None = None


class AccountabilityGuard(Protocol):
    """Trusted server-side reviewer and ordinary-ledger adapter.

    Implementations receive plaintext because classification cannot be
    inferred from encrypted bytes.  They must avoid logging or copying the
    private body.  For accountable content, they must durably write the
    ordinary record before returning its receipt.  Uncertainty must be treated
    as accountable, not silently downgraded to ``private_only``.
    """

    def review_and_record(
        self,
        *,
        correlation_id: str,
        title: str,
        content: str,
        kind: str,
    ) -> AccountabilityReceipt:
        """Review one proposed write and return a non-caller-issued receipt."""


def validate_receipt(
    receipt: AccountabilityReceipt,
    *,
    expected_correlation_id: str,
) -> AccountabilityReceipt:
    """Normalize and validate a trusted guard receipt."""
    if not isinstance(receipt, AccountabilityReceipt):
        raise AccountabilityReviewError(
            "accountability guard must return AccountabilityReceipt"
        )
    if not _CORRELATION_ID.fullmatch(expected_correlation_id):
        raise AccountabilityReviewError("invalid expected correlation id")
    if receipt.correlation_id != expected_correlation_id:
        raise AccountabilityReviewError("accountability receipt correlation mismatch")

    try:
        classification = AccountabilityClass(receipt.classification)
    except (TypeError, ValueError) as exc:
        raise AccountabilityReviewError(
            "accountability receipt has an unknown classification"
        ) from exc

    if classification in PROHIBITED_CLASSES:
        raise ProhibitedPrivateContentError(
            f"{classification.value} content must not be sealed in private space"
        )

    ordinary_record_ref = receipt.ordinary_record_ref
    if ordinary_record_ref is not None:
        if not isinstance(ordinary_record_ref, str):
            raise AccountabilityReviewError("ordinary record reference must be text")
        ordinary_record_ref = ordinary_record_ref.strip()
        if (
            not ordinary_record_ref
            or len(ordinary_record_ref.encode("utf-8")) > MAX_ORDINARY_RECORD_REF_BYTES
            or any(character.isspace() for character in ordinary_record_ref)
            or any(
                ord(character) < 0x21 or ord(character) == 0x7F
                for character in ordinary_record_ref
            )
        ):
            raise AccountabilityReviewError("ordinary record reference is invalid")

    if classification in ACCOUNTABLE_CLASSES and ordinary_record_ref is None:
        raise AccountabilityReviewError(
            "accountable content requires a durable ordinary record reference"
        )
    if (
        classification is AccountabilityClass.PRIVATE_ONLY
        and ordinary_record_ref is not None
    ):
        raise AccountabilityReviewError(
            "private-only content must not create an unnecessary existence link"
        )

    return AccountabilityReceipt(
        classification=classification,
        correlation_id=expected_correlation_id,
        ordinary_record_ref=ordinary_record_ref,
    )


def receipt_payload(receipt: AccountabilityReceipt) -> dict[str, str | int | None]:
    """Return the encrypted payload representation for a validated receipt."""
    classification = AccountabilityClass(receipt.classification)
    return {
        "version": 1,
        "classification": classification.value,
        "correlation_id": receipt.correlation_id,
        "ordinary_record_ref": receipt.ordinary_record_ref,
    }
