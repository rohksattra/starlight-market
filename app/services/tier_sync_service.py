from __future__ import annotations

from app.domains.tiers import (
    customer_tier_role_for_spent,
    donor_role_for_total,
    worker_tier_role_for_income,
)


def resolve_tier_role_ids(doc: dict) -> set[int]:
    donation = int(doc.get("donation_given") or 0)
    worker_income = int(doc.get("total_worker_income") or 0)
    customer_spent = int(doc.get("total_customer_spent") or 0)

    chosen_donor = donor_role_for_total(donation)
    chosen_worker = worker_tier_role_for_income(worker_income)
    chosen_customer = customer_tier_role_for_spent(customer_spent)

    return {rid for rid in (chosen_donor, chosen_worker, chosen_customer) if rid is not None}
