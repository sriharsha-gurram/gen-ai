"""The 15-question evaluation set for the Enterprise Policy Q&A Bot.

Categories (as required by the Week 2 handout):
  - straightforward (Q1-Q6): single-policy fact lookups
  - ambiguous (Q7-Q8): the question has more than one policy reading
  - multi-document (Q9-Q11): the answer spans two or more handbook pages
  - unanswerable (Q12-Q14): the fact is NOT in the corpus; a correct
    answer abstains ("Not in the knowledge base") instead of guessing.
    Verified by grepping the raw corpus on Nov 7, 2026:
      Q12 — GitLab is all-remote; there is no office Wi-Fi password.
      Q13 — "talent-assessment" mentions a compensation band but gives
            no band numbers for any role/location.
      Q14 — "gym" appears once, about work-life integration, never as
            a reimbursable expense with a limit.
  - edge / long-doc (Q15): retrieval from a very long page (offboarding)

`expected_docs` lists the handbook page(s) a good retrieval should
surface. `expected_fact` is the checkable fact the answer must contain
(for answerable questions) or the abstention expected (unanswerable).
"""
from __future__ import annotations

QUESTIONS = [
    {"id": "Q01", "category": "straightforward",
     "question": "How many paid sick days does GitLab give each team member, and over what period?",
     "expected_docs": ["time-off-types"],
     "expected_fact": "25 paid sick days, rolling 12-month period"},
    {"id": "Q02", "category": "straightforward",
     "question": "How long is GitLab's paid parental leave, and who is eligible for it?",
     "expected_docs": ["leave-types"],
     "expected_fact": "16 weeks paid, any active team member, from first day of employment"},
    {"id": "Q03", "category": "straightforward",
     "question": "What is an onboarding buddy at GitLab, and how long must someone have worked there to volunteer as one?",
     "expected_docs": ["onboarding-buddies"],
     "expected_fact": "A buddy supports a new team member in the first weeks; volunteers need 3+ months at GitLab"},
    {"id": "Q04", "category": "straightforward",
     "question": "Does GitLab have a fixed number of paid time off days per year?",
     "expected_docs": ["time-off-types", "time-away-philosophy"],
     "expected_fact": "No fixed cap: Flexible PTO, team members take time off as needed"},
    {"id": "Q05", "category": "straightforward",
     "question": "What should a team member do if they experience harassment at GitLab?",
     "expected_docs": ["anti-harassment"],
     "expected_fact": "Report it; the policy describes reporting channels and that retaliation is prohibited"},
    {"id": "Q06", "category": "straightforward",
     "question": "How does GitLab handle pronouns in the workplace?",
     "expected_docs": ["pronouns"],
     "expected_fact": "Team members share pronouns (e.g. in profiles); others should use the stated pronouns"},
    {"id": "Q07", "category": "ambiguous",
     "question": "How much time off can I take?",
     "expected_docs": ["time-off-types", "time-away-philosophy", "leave-types"],
     "expected_fact": "Answer must distinguish Flexible PTO from sick time (25 days) and parental leave (16 weeks)"},
    {"id": "Q08", "category": "ambiguous",
     "question": "What support is available when I join GitLab?",
     "expected_docs": ["general-onboarding", "onboarding-buddies"],
     "expected_fact": "Onboarding program plus an onboarding buddy (and MR buddies for engineers)"},
    {"id": "Q09", "category": "multi-document",
     "question": "Compare GitLab's parental leave with its sick leave: how long is each, and when does each start?",
     "expected_docs": ["leave-types", "time-off-types"],
     "expected_fact": "Parental leave 16 weeks from day one; sick time 25 days per rolling 12 months from day one"},
    {"id": "Q10", "category": "multi-document",
     "question": "I am relocating to another country for a GitLab role. What do I need to know about visas and relocation support?",
     "expected_docs": ["relocation", "visas"],
     "expected_fact": "Relocation support exists and visa/work-authorisation steps are documented per country"},
    {"id": "Q11", "category": "multi-document",
     "question": "How does GitLab support learning and career growth, and how does that connect to promotions?",
     "expected_docs": ["learning-and-development", "promotions-transfers"],
     "expected_fact": "Learning and development programs exist; promotions follow the documented process and competencies"},
    {"id": "Q12", "category": "unanswerable",
     "question": "What is the Wi-Fi password for the GitLab office in San Francisco?",
     "expected_docs": [],
     "expected_fact": "ABSTAIN — GitLab is all-remote; no office Wi-Fi password exists in the corpus"},
    {"id": "Q13", "category": "unanswerable",
     "question": "What is the exact salary band for a Senior Backend Engineer in Berlin?",
     "expected_docs": [],
     "expected_fact": "ABSTAIN — no salary band numbers for any role or location are in the corpus"},
    {"id": "Q14", "category": "unanswerable",
     "question": "Can I expense a personal gym membership, and what is the monthly reimbursement limit?",
     "expected_docs": [],
     "expected_fact": "ABSTAIN — no gym reimbursement policy or limit is in the corpus"},
    {"id": "Q15", "category": "edge",
     "question": "What happens to my GitLab access and equipment when I leave the company?",
     "expected_docs": ["offboarding"],
     "expected_fact": "Offboarding process: access is revoked and equipment must be returned"},
]
