import os

def generate_enterprise_corpus():
    # Ensure directory structure
    categories = {
        "corpus/skus": 17,
        "corpus/legal": 17,
        "corpus/policies": 16
    }
    
    for path in categories.keys():
        os.makedirs(path, exist_ok=True)

    print("Generating comprehensive 50-document enterprise corpus...")

    # 1. Generate 17 SKU & Catalog Documents
    for i in range(1, 18):
        filename = f"corpus/skus/product_tier_{i:02d}.md"
        content = f"""# Enterprise Product Suite - Module {i} Specification

## Executive Summary
Module {i} delivers advanced data orchestration, automated quote-to-cash workflows, and high-performance ingestion pipelines tailored for enterprise tier-{i % 3 + 1} organizations.

## Pricing Structure & Tiered Licensing
* **Base Platform Subscription:** ${35000 + (i * 1500):,} / year.
* **Included User Seats:** 25 named users. Additional seats billed at ${1000 + (i * 50)} per user/year.
* **Volume API Tiering:**
  * Tier 1 (0 - 15M calls/mo): Included in base fee.
  * Tier 2 (15M - 50M calls/mo): $0.00012 per request.
  * Tier 3 (50M+ calls/mo): Requires custom enterprise rider approval.

## Contractual Terms & Renewals
* Automatic annual renewal with a standard 4% inflation adjustment cap.
* Multi-year commitments of 36 months qualify for a 12% total contract value (TCV) reduction.
"""
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)

    # 2. Generate 17 Legal & SLA Documents
    for i in range(1, 18):
        filename = f"corpus/legal/sla_agreement_region_{i:02d}.md"
        content = f"""# Master Service Agreement - Region Code {i:02d}

## Section {i}: Uptime Guarantees and Service Level Agreements (SLA)
{i}.1 **System Availability:** Vendor commits to a monthly uptime availability of 99.{9 + (i % 9)}% for all production workloads deployed under Region {i:02d}.

{i}.2 **Credit Remedies:** In the event of availability breaches, client receives service credits:
* Availability between 99.0% and 99.8%: 15% credit of monthly MRR.
* Availability between 95.0% and 98.9%: 30% credit of monthly MRR.
* Availability below 95.0%: 50% credit of monthly MRR plus termination rights.

{i}.3 **Liability Cap:** Aggregate liability for Region {i:02d} contracts is strictly capped at 100% of fees paid during the preceding twelve (12) months.
"""
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)

    # 3. Generate 16 Policy & Discount Documents
    for i in range(1, 17):
        filename = f"corpus/policies/discount_matrix_policy_{i:02d}.md"
        content = f"""# Global Discount & Approval Policy - Version {i}.0

## Purpose & Scope
This commercial governance policy applies to all global sales transactions processed under Framework {i}.

## Delegation of Authority (DoA) Matrix
* **Account Executive:** Maximum discretionary discount of up to {5 + (i % 6)}% off list price.
* **Regional Sales Director:** Authority to approve discounts between {6 + (i % 6)}% and {18 + (i % 5)}%. Requires signed justification memo.
* **Vice President of Global Sales:** Authority to approve discounts up to {25 + (i % 6)}%.
* **Executive Committee (CRO/CEO):** Any discount exceeding {30}% or containing non-standard indemnification requires board-level review.

## Compliance
Failure to log discount rationales in the CPQ audit ledger within 24 hours results in commission forfeiture for the deal cycle.
"""
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)

    print("Successfully generated 50 comprehensive enterprise documents across 3 domain folders.")

if __name__ == "__main__":
    generate_enterprise_corpus()
