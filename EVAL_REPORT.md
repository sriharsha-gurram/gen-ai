# Evaluation Report — Enterprise Policy Q&A Bot

Run date: 2026-11-07. Corpus: 29 GitLab Handbook People pages, 605 chunks (1200 chars, 200 overlap). Embeddings: OpenAI text-embedding-3-small (1536-dim). Generation/rerank/judge: OpenAI gpt-4o-mini. Retrieval: hybrid BM25 + semantic, RRF fusion, LLM rerank.

Provider note: the first index was built with Gemini gemini-embedding-2 and Q01 of this run was originally answered by Gemini gemini-3-flash-preview (45.9s, grounded, correct). The Gemini free tier then exhausted (429s), so the index was re-embedded with OpenAI and Q02-Q15 were run on OpenAI; the Gemini index is kept in data/index/gemini-archive/.

## Summary

- Questions: 15 (12 answerable, 3 unanswerable)
- Retrieval hit rate (answerable, expected doc in top-4): 12/12 = 100%
- Correct abstention (unanswerable): 3/3
- Grounded answers (LLM judge): 8/15
- Fact correct (LLM judge): 9/15
- Latency: mean 7.0s, p95 5.5s, max 45.9s

## Per-question results

| ID | Category | Retrieval hit | Fact | Groundedness | Abstained | Citations valid | Latency |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Q01 | straightforward | yes | correct | grounded | False | True | 45.9s |
| Q02 | straightforward | yes | correct | grounded | False | True | 5.5s |
| Q03 | straightforward | yes | correct | partial | False | True | 4.5s |
| Q04 | straightforward | yes | correct | grounded | False | True | 5.2s |
| Q05 | straightforward | yes | correct | grounded | False | True | 4.1s |
| Q06 | straightforward | yes | correct | grounded | False | True | 3.6s |
| Q07 | ambiguous | yes | partial | partial | False | True | 3.3s |
| Q08 | ambiguous | yes | partial | partial | False | True | 4.4s |
| Q09 | multi-document | yes | partial | partial | False | True | 5.5s |
| Q10 | multi-document | yes | partial | partial | False | True | 5.1s |
| Q11 | multi-document | yes | partial | partial | False | True | 4.3s |
| Q12 | unanswerable | n/a | correct | grounded | True | False | 3.8s |
| Q13 | unanswerable | n/a | correct | grounded | True | True | 3.1s |
| Q14 | unanswerable | n/a | correct | grounded | True | False | 3.2s |
| Q15 | edge | yes | partial | partial | False | True | 3.1s |

## Per-question detail

### Q01 (straightforward)

**Q:** How many paid sick days does GitLab give each team member, and over what period?

**Expected:** 25 paid sick days, rolling 12-month period

**Answer:** Eligible team members receive 100% of their weekly wages for up to 25 working days through the GitLab Sick Time policy [2]. Eligibility for this time is calculated on a rolling 12-month period, which is a window that continuously shifts forward while maintaining a constant 12-month duration [1]. If a leave extends beyond 25 working days, it is unpaid by GitLab, subject to local requirements [2].

Partially covered: the specific criteria used to determine which team members are "eligible" for this policy.

**Retrieved docs:** time-off-types, time-off-types, leave-types | **Judge:** The answer accurately identifies both the 25-day limit and the rolling 12-month period mentioned in the passages.

### Q02 (straightforward)

**Q:** How long is GitLab's paid parental leave, and who is eligible for it?

**Expected:** 16 weeks paid, any active team member, from first day of employment

**Answer:** GitLab offers 16 weeks of paid Parental Leave to any active team member, regardless of gender, who becomes a parent through childbirth, adoption, fostering, or surrogacy while working at GitLab. This benefit is available from the first day of employment, provided the qualifying event occurs during employment [1][2]. 

Partially covered: Eligibility details are fully stated; however, specifics on the application process or documentation required are not mentioned.

**Retrieved docs:** leave-types, leave-types, time-off-types, time-off-types | **Judge:** The answer accurately reflects GitLab's parental leave policy and eligibility.

### Q03 (straightforward)

**Q:** What is an onboarding buddy at GitLab, and how long must someone have worked there to volunteer as one?

**Expected:** A buddy supports a new team member in the first weeks; volunteers need 3+ months at GitLab

**Answer:** An onboarding buddy at GitLab is someone who helps new team members adjust to their roles, offering mentorship and support during their initial weeks at the company. To qualify as an onboarding buddy, an employee must have worked at GitLab for more than 3 months [1][2]. 

Partially covered: Specific details about the onboarding buddy program beyond eligibility criteria are not included.

**Retrieved docs:** onboarding-buddies, onboarding-buddies, general-onboarding, general-onboarding | **Judge:** The answer correctly describes the role of an onboarding buddy and the time requirement, but lacks some details about their support beyond mentorship.

### Q04 (straightforward)

**Q:** Does GitLab have a fixed number of paid time off days per year?

**Expected:** No fixed cap: Flexible PTO, team members take time off as needed

**Answer:** GitLab does not have a fixed number of paid time off (PTO) days per year, as it operates under a Flexible PTO policy. This allows team members to take the time they need for personal obligations, relaxation, or vacations, provided they coordinate with their manager and make a coverage plan. However, while there is no specific limit, special permission is required for time off that exceeds 25 consecutive calendar days [1][2]. 

Partially covered: It does not mention any specific recommendation or minimum PTO days required.

**Retrieved docs:** time-off-types, time-off-types, time-off-and-absence, leave-types | **Judge:** The answer accurately reflects GitLab's Flexible PTO policy and captures the lack of a fixed cap on PTO days.

### Q05 (straightforward)

**Q:** What should a team member do if they experience harassment at GitLab?

**Expected:** Report it; the policy describes reporting channels and that retaliation is prohibited

**Answer:** Team members who feel that they may have been subjected to harassment at GitLab should bring their complaints to their People Business Partner (PBP), who will engage the appropriate internal consultation services and respond to claims. GitLab prohibits any dismissal or unfair treatment of team members who report harassment or cooperate in an investigation or consultation process [1][2]. 

Partially covered: Details regarding what specific actions constitute harassment are mentioned, but the procedures following a complaint are not included.

**Retrieved docs:** anti-harassment, anti-harassment, talent-assessment, talent-assessment | **Judge:** The answer accurately describes the reporting process and the prohibition of retaliation.

### Q06 (straightforward)

**Q:** How does GitLab handle pronouns in the workplace?

**Expected:** Team members share pronouns (e.g. in profiles); others should use the stated pronouns

**Answer:** At GitLab, the handling of pronouns in the workplace focuses on respect, inclusion, and personal choice. Team members are encouraged to use the pronouns that individuals identify for themselves, as this practice reflects respect and allyship. Sharing pronouns is voluntary, and not everyone may feel comfortable doing so due to cultural or personal reasons, which should always be respected. This commitment aligns with GitLab's values of Diversity, Inclusion, and Belonging [1][2].

Partially covered: Missing details about consequences or specific practices related to misuse of pronouns.

**Retrieved docs:** pronouns, pronouns, people-group-index, talent-assessment | **Judge:** The response accurately reflects GitLab's approach to handling pronouns in the workplace.

### Q07 (ambiguous)

**Q:** How much time off can I take?

**Expected:** Answer must distinguish Flexible PTO from sick time (25 days) and parental leave (16 weeks)

**Answer:** GitLab does not set a specific limit on the amount of Paid Time Off (PTO) a team member can take per year, but special permission is required for time off exceeding 25 consecutive calendar days, including weekends and holidays. Team members are encouraged to take at least two consecutive weeks off and a minimum of 25 days total throughout the year [1]. 

Partially covered: Specific details about sick time or parental leave limits are not included.

**Retrieved docs:** time-off-types, time-away-philosophy, time-off-types, time-away-philosophy | **Judge:** The answer discusses Flexible PTO and the limit for longer time off, but it fails to mention specifics about sick time and parental leave.

### Q08 (ambiguous)

**Q:** What support is available when I join GitLab?

**Expected:** Onboarding program plus an onboarding buddy (and MR buddies for engineers)

**Answer:** GitLab provides several support mechanisms for new team members. There is a dedicated approach for accessibility and accommodations, ensuring new hires have the necessary tools and support to thrive from day one. Team members can access ergonomic equipment and request assistive technology through the Team Member Relations (TMR) team. Additionally, new hires can have onboarding buddies who assist with their adjustment to GitLab and the applications/tools they will use [2][3].

Partially covered: Details on specific programs or additional resources for new hires beyond those mentioned are missing.

**Retrieved docs:** tanewki-tips, tanewki-tips, onboarding-buddies, pronouns | **Judge:** The answer mentions onboarding buddies but lacks specific details about the onboarding program.

### Q09 (multi-document)

**Q:** Compare GitLab's parental leave with its sick leave: how long is each, and when does each start?

**Expected:** Parental leave 16 weeks from day one; sick time 25 days per rolling 12 months from day one

**Answer:** GitLab provides 16 weeks of paid Parental Leave, which begins when a child is born, newly adopted, or placed in foster care during employment, and must be used prior to the child's first birthday or the first anniversary of adoption or foster placement [1]. 

For Sick Leave, each team member is eligible for up to 25 paid sick days from their first day of work, which can be used for personal illness or preventative care [3]. 

Partially covered: The specific start dates for sick leave are not detailed, nor is there information on how the sick leave policy interacts with parental leave.

**Retrieved docs:** leave-types, leave-types, time-off-types, time-off-and-absence | **Judge:** The answer correctly addresses parental leave duration and start but lacks complete details on sick leave.

### Q10 (multi-document)

**Q:** I am relocating to another country for a GitLab role. What do I need to know about visas and relocation support?

**Expected:** Relocation support exists and visa/work-authorisation steps are documented per country

**Answer:** If you are relocating for a GitLab role, be sure that GitLab has an entity in the destination country, as long-term relocations are only supported to countries open for hiring without restrictions. You must have the appropriate right to work documentation or visas for the selected country, and GitLab only sponsors relocations to the Netherlands and does not cover relocation costs for family members. Additionally, a minimum one-year tenure with GitLab is required to be eligible for relocation [1][2].

Partially covered: Missing details include specific procedures for proving work eligibility and any other relocation support details outside of the Netherlands.

**Retrieved docs:** relocation, relocation, talent-assessment, tanewki-tips | **Judge:** The answer correctly mentions visa requirements and GitLab's support for relocations but lacks comprehensive information on broader relocation support.

### Q11 (multi-document)

**Q:** How does GitLab support learning and career growth, and how does that connect to promotions?

**Expected:** Learning and development programs exist; promotions follow the documented process and competencies

**Answer:** GitLab supports learning and career growth through various initiatives, including a Learning and Development team that helps create pathways for growth, mentorship opportunities, and organized skill development sessions such as the Skill of the Month and Manager Challenge [1][2]. The company also emphasizes personal and professional development, which is linked to promotion opportunities, by enabling discussions around motivation and ambitions, and encouraging participants to create Individual Growth Plans (IGPs) [3][4].

Partially covered: Specific details on the connection between these development efforts and the promotion process are missing.

**Retrieved docs:** learning-and-development, engagement, talent-assessment, talent-assessment | **Judge:** The answer correctly identifies learning and development programs but lacks details on the documented promotion process.

### Q12 (unanswerable)

**Q:** What is the Wi-Fi password for the GitLab office in San Francisco?

**Expected:** ABSTAIN — GitLab is all-remote; no office Wi-Fi password exists in the corpus

**Answer:** Not in the knowledge base: the GitLab Handbook pages in this system do not cover this. The closest passages discuss onboarding procedures and remote work guidelines, but do not provide any information on specific Wi-Fi passwords.

**Retrieved docs:** tanewki-tips, all-remote, acceptable-use-policy, relocation | **Judge:** The answer correctly abstains from providing a Wi-Fi password since GitLab is all-remote.

### Q13 (unanswerable)

**Q:** What is the exact salary band for a Senior Backend Engineer in Berlin?

**Expected:** ABSTAIN — no salary band numbers for any role or location are in the corpus

**Answer:** Not in the knowledge base: the GitLab Handbook pages in this system do not cover this. The closest passages discuss talent assessment and job frameworks [2][4], but they do not specify salary bands.

**Retrieved docs:** visas, talent-assessment, visas, talent-assessment | **Judge:** The answer correctly abstains from providing a salary band, which is not present in the retrieved passages.

### Q14 (unanswerable)

**Q:** Can I expense a personal gym membership, and what is the monthly reimbursement limit?

**Expected:** ABSTAIN — no gym reimbursement policy or limit is in the corpus

**Answer:** Not in the knowledge base: the GitLab Handbook pages in this system do not cover this. The closest passages discuss reimbursement procedures and types of expenses that can be submitted, but do not specifically mention personal gym memberships or a reimbursement limit.

**Retrieved docs:** tanewki-tips, offboarding, visas, tanewki-tips | **Judge:** The answer accurately abstains from providing unsupported information regarding gym membership reimbursement.

### Q15 (edge)

**Q:** What happens to my GitLab access and equipment when I leave the company?

**Expected:** Offboarding process: access is revoked and equipment must be returned

**Answer:** When you leave GitLab, you must return any GitLab-owned equipment if requested, regardless of its value. In certain circumstances, such as investigations or violations of company policies, you have no right to retain GitLab-owned computing equipment [1]. Additionally, during the offboarding process, you will receive information about your benefits coverage and final pay, and there is a procedure for laptop wipes [3]. 

Partially covered: Missing specific details on what happens to your access to company systems.

**Retrieved docs:** acceptable-use-policy, tanewki-tips, offboarding, talent-assessment | **Judge:** The answer correctly mentions equipment return but lacks specific details about access revocation.

## Failure analysis

- **Q03** (straightforward): groundedness judged partial. Judge note: The answer correctly describes the role of an onboarding buddy and the time requirement, but lacks some details about their support beyond mentorship.
- **Q07** (ambiguous): fact judged partial; groundedness judged partial. Judge note: The answer discusses Flexible PTO and the limit for longer time off, but it fails to mention specifics about sick time and parental leave.
- **Q08** (ambiguous): fact judged partial; groundedness judged partial. Judge note: The answer mentions onboarding buddies but lacks specific details about the onboarding program.
- **Q09** (multi-document): fact judged partial; groundedness judged partial. Judge note: The answer correctly addresses parental leave duration and start but lacks complete details on sick leave.
- **Q10** (multi-document): fact judged partial; groundedness judged partial. Judge note: The answer correctly mentions visa requirements and GitLab's support for relocations but lacks comprehensive information on broader relocation support.
- **Q11** (multi-document): fact judged partial; groundedness judged partial. Judge note: The answer correctly identifies learning and development programs but lacks details on the documented promotion process.
- **Q15** (edge): fact judged partial; groundedness judged partial. Judge note: The answer correctly mentions equipment return but lacks specific details about access revocation.
