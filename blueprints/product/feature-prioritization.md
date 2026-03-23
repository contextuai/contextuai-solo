# Feature Prioritization (RICE Scoring)

A systematic approach to feature prioritization using the RICE scoring framework. This blueprint helps product teams move beyond gut feelings and stakeholder politics by evaluating every feature candidate against four objective dimensions: Reach, Impact, Confidence, and Effort.

## Objective

Produce a ranked feature backlog scored with RICE methodology, identifying the highest-value features to build next and flagging quick wins that can be shipped immediately.

## Steps

### 1. Build the Feature List
Gather all feature requests, ideas, and proposals from every source: customer feedback, support tickets, sales team input, competitor analysis, internal brainstorms, and existing backlog items. Consolidate duplicates and ensure each feature is described clearly enough that anyone on the team can understand what it entails. Aim for a list of 15-30 candidates to make the exercise meaningful.

### 2. Score Reach
For each feature, estimate how many users or customers it will affect within a defined time period (typically one quarter). Use concrete data wherever possible: active user counts, segment sizes, funnel metrics. If a feature affects all users, score it at your total active user count. If it targets a specific segment, use that segment's size. Document your assumptions so scores can be challenged and refined.

### 3. Score Impact
Rate the expected impact on individual users when they encounter the feature. Use a standardized scale: 3 = massive impact (transforms the experience), 2 = high impact (significant improvement), 1 = medium impact (noticeable improvement), 0.5 = low impact (minor convenience), 0.25 = minimal impact. Consider how the feature affects key business metrics like conversion, retention, or satisfaction. Be rigorous about distinguishing nice-to-haves from genuine game-changers.

### 4. Score Confidence
Assess how confident you are in your Reach and Impact estimates. Use a percentage: 100% = high confidence backed by data, 80% = moderate confidence based on strong signals, 50% = low confidence mostly based on intuition. This score penalizes features where you are guessing and rewards those grounded in evidence. If confidence is below 50%, consider running a quick validation experiment before committing resources.

### 5. Score Effort
Estimate the total person-months of work required to ship the feature, including design, development, testing, and launch activities. Be honest about hidden complexity: integrations, migrations, edge cases, and documentation. Larger effort scores reduce the RICE score, so this naturally favors simpler solutions. Break down ambiguous features into smaller pieces if the effort is hard to estimate as a whole.

### 6. Calculate RICE Scores and Stack Rank
Apply the formula: RICE = (Reach x Impact x Confidence) / Effort. Sort all features by their RICE score from highest to lowest. Review the top 10 for sanity: does the ranking match your intuition? If not, revisit the individual scores to find where estimates may be off. The goal is not blind obedience to the formula but informed decision-making.

### 7. Identify Quick Wins
Highlight features with high RICE scores and low effort (under 0.5 person-months). These quick wins can often be shipped immediately while larger initiatives are being planned. Create a separate "quick wins" track to maintain momentum and show progress while the team works on higher-effort items.

## Expected Output

A spreadsheet or table with all features scored across Reach, Impact, Confidence, and Effort, the calculated RICE score, a stack-ranked priority list, and a separate quick-wins list ready for immediate execution.

## Recommended Agents

- **Product Manager** — Leads the scoring exercise, synthesizes input from all stakeholders, and makes final prioritization calls.
- **Data Analyst** — Provides quantitative data for Reach and Impact estimates and validates Confidence levels with evidence.
- **CTO** — Contributes accurate Effort estimates and flags technical risks or dependencies that affect feasibility.
