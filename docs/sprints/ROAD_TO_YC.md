# Road to YC — Winter 2027 application

**YC Winter 2027 on-time deadline: Mon 2 Nov 2026, 8:00 pm PT.** Submit Sun 1 Nov 2026, evening. Freeze: Thu 29 Oct 2026, 22:00 — demo build frozen; fixes only after. Source: https://www.ycombinator.com/apply

## Day by day

| Day | Sprint | Critical path |
|---|---|---|
| Wed 21 Oct | S0 | Graded verifier (A0-01), candidate log (B0-01), Verbalized Sampling (C0-01) start; insurance quotes requested, Stripe activation submitted; YC go decided; application answers v0 drafted from the memo; decision log opened. |
| Thu 22 Oct | S0 | Descriptor vector (A0-04), CP-SAT spike (A0-02), replay (B0-02), PartyBench v0 (B0-03), backprompting (C0-02); Checkr account, vendor long-list and form; Halloween host shortlisted; demo storyline. |
| Fri 23 Oct | S0 | DPP pick of three (A0-03), picker (C0-03), Places terms (C0-05), baseline stub (B0-04); Friday demo recorded; dasher job description posted. |
| Sat 24 Oct | S0 | Prompt caching + Haiku 5.5 (C0-04), judge v0 (B0-05); founder video practice takes; application answers v1 outline. |
| Sun 25 Oct | S0 | S0 exit gate; PartyBench v0 report archived; S1 briefs issued; Halloween host confirmed; deploy prep (secrets, disk). |
| Mon 26 Oct | S1 | Go live (C1-01), three concepts in the API (A1-01), PartyBench v1 baselines start (B1-01), landing + waitlist (C1-04); Halloween request entered and Living Pass sent (D1-01); application v1 complete. |
| Tue 27 Oct | S1 | Book it with test checkout (C1-02); UI matrix against the public URL; waitlist posted in three groups; ten vendor calls (D1-02); shopping list checked against retail. |
| Wed 28 Oct | S1 | Dasher console v0 (C1-03); /bench page (B1-02); application v2 with numbers; outside readers; two dasher candidates screened (D1-04). |
| Thu 29 Oct | S1 | Hardening runs and the demo environment pinned (A1-02); outcome ledger (B1-03); insurance and Stripe closed out (D1-05); founder video final take; FREEZE at 22:00. |
| Fri 30 Oct | S1 | Fixes only; full gate + UI matrix + validate_live on the frozen build; application v3 final text pasted into the form; party shopping from the console. |
| Sat 31 Oct | S1 | Halloween proof party run by the founders as dashers (D1-03); outcome row within 2 hours; demo video recorded at night (E1-03). |
| Sun 1 Nov | S1 | Edit the demo video; outside readers on the cut; product link set; final checklist; SUBMIT in the evening (E1-04). |
| Mon 2 Nov | S1 | Buffer only. Deadline 8:00 pm PT. Nothing else scheduled. |

## Evidence checklist

| ID | The form asks | Evidence we bring | Source | Owner |
|---|---|---|---|---|
| Y-01 | Company one-liner and what it does (short) | The verified, fulfilled party bundle: one sentence from the memo's six-things thesis | strategy memo §3; E1-01 | Leo |
| Y-02 | Founders, roles, how long you have worked together | Bios; who built what in the repo (commit history) | git log; E1-01 | Founders |
| Y-03 | Founder video (1 minute, founders only) | Final take after the freeze | E1-02 | Founders |
| Y-04 | Product link / demo | Public URL (live backend) + 2–3 minute demo video | C1-01; E1-03 | Leo |
| Y-05 | How far along are you? | Deployed product; 601-item catalog; verifier; Living Pass; PartyBench numbers; one real party; ten vendors; two dashers; insurance quotes; Stripe activation | B1-01; D1-02; D1-03; D1-04; D1-05 | Leo |
| Y-06 | Are people using it? Revenue? | Pre-revenue; the Halloween party booked in test mode; waitlist count; host rating and guest NPS | C1-04; D1-03; B1-03 | Leo |
| Y-07 | Tech stack, including AI tools used to build | FastAPI/pydantic, deterministic composer + verifier, Claude (Haiku 5.5) with caching, CP-SAT spike, Playwright/axe matrix, PartyBench; built with Claude Code agents under a test gate | README; docs/ARCHITECTURE.md | Leo |
| Y-08 | Why this idea; how do you know people need it | The PB&J moment; the 100-profile matrix; the party outcome; the waitlist; incumbents' gaps (OpenAI checkout retreat, Google MoR stance, Instacart Fizz scope) | memo §3; D1-03; C1-04 | Leo |
| Y-09 | Competitors and what you understand that they do not | Nobody sells a verified, fulfilled bundle; TravelPlanner ladder (solver beats sampling); verifier as reward | memo §2–3 | Leo |
| Y-10 | How will you make money | Merchant of record for the bundle, 20–30% blended take with ≥ 10% contribution; dasher labour inside the price; one real order P&L from the Halloween party | C1-02 price parts; D1-03 receipts | Leo |
| Y-11 | Metrics a partner would check | First-try verified rate vs raw GPT/Gemini/Claude with CIs; cost per plan; p95 latency; on-time and replacement rate (n=1) | B1-01; B1-03 | Agent B |
| Y-12 | Legal entity, equity, prior funding | As applicable; nothing invented | Leo | Leo |
| Y-13 | What is next (the plan) | Nine sprints to Christmas; one metro launch 17 Dec; PartyBench public | strategy/sprint-plan-to-launch.md | Leo |
| Y-14 | Submission | Submitted Sun 1 Nov evening; confirmation screenshot | E1-04 | Leo |

## Cut until after 2 November

- CP-SAT core, concept archive, judge calibration and taste weights wait until after 2 Nov (the spike, DPP and Verbalized Sampling carry the demo).
- Vendor onboarding stops at ten confirmed rows; no vendor API work; Places compliance fix only.
- Insurance is quoted, not bound; Checkr is opened, not run; Stripe stays in test mode.
- No new product surfaces beyond Book it, the dasher console and the landing page.
- The S0 cards keep their dates; anything in S0 not done by Sun 25 Oct moves to S1 only if the demo needs it, otherwise to Backlog.

Sprint documents: `docs/sprints/S0.md`, `docs/sprints/S1.md`.
