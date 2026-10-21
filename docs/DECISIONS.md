# Decision log

One entry per design or product decision an agent could not make alone: the options, the reason, who decided, the date. The log is the input to the next sprint's research brief. Newest first.

## 2026-10-21 · Sprint 0

- **Reward formula.** Per-rule partial credit with tolerances (budget 0.25, servings 0.30, guest range 0.20), safety weight 1.0, budget/servings/guest range 0.7, completeness 0.3; `hard_micro`, `hard_macro`, `R = (hard_micro + hard_macro + pass)/3`; best-of-N ranks lexicographically (pass, hard_macro, hard_micro). No curriculum (Planner-R1 found none helps; sparse reward collapses). Soft-reward sigmoid gate (τ 0.75, k 28) joins in S1. — Leo + research, A0-01
- **Candidate log schema v1.** One JSONL row per candidate with catalog_sha256, verifier_version, model_id, usage, graded verdict, descriptor vector, selection; PII pseudonymized before write; replay re-verifies the verifier only (the Claude API has no seed). — B0-01
- **Three shown, chosen by DPP.** Greedy MAP DPP with θ = 0.6 over cosine descriptor similarity; API returns `alternatives` when `variants=3`. — A0-03
- **Solver spike before the solver.** CP-SAT on one profile with hints and infeasibility assumptions; go/no-go for the S1 core recorded on Friday. — A0-02
- **Claude path: Verbalized Sampling + structured backprompting.** k = 5, τ = 0.10; all violations sent at once; ≤ 3 rounds; keep the best-R draft; never re-prompt a passing plan. — C0-01, C0-02
- **Cheap tier + prompt caching.** Haiku 5.5 default with one cached system block ≥ 512 tokens; Sonnet 5.5 opt-in for hard briefs. 20k calls ≈ $9. — C0-04
- **Places terms.** Cache only place_id (indefinitely) and lat/lng (≤ 30 days); refetch details on render; attribution shown. — C0-05
- **YC timing.** Winter 2027 on-time deadline is Sun 2 Nov, 8 pm PT (not end of November). Decision due Thu 23 Oct: apply on time with pre-launch proof, or Early Decision for Spring 2027. — E0-01 (open)
- **Payments structure.** iParty is the disclosed seller of the bundle; vendors and dashers paid via Stripe Connect separate charges and transfers; Stripe Managed Payments excluded (digital-only); alcohol excluded at launch. — D0-02
- **Insurance programme.** GL $1M/$2M + contingent liability + occupational accident via broker quotes; ask about abuse & molestation and host liquor. Bind decision in S1. — D0-01
