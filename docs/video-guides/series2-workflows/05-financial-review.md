# Workflow 5: Financial Review Autopilot

**Duration:** 5 minutes
**Scenario:** A solo founder connects their database, queries financial data through Chat, runs a full analysis in Workspace, and produces an investor-ready report through a Crew.
**Flow:** Persona (DB connection) → Chat (data exploration) → Workspace (analysis) → Crew (report)

---

## Opening (0:00 - 0:15)

**Voiceover:**
> "Quarter-end is coming. You need to pull numbers, analyze trends, and produce a financial report for your investors. Let's connect Solo to your database and automate the entire review."

---

## Act 1: Connect Your Database (0:15 - 1:00)

**On screen:** Personas → Create Persona

**Steps:**
1. Click **Create Persona**
2. Select **PostgreSQL** type
3. Fill in:
   - Name: "Company Finance DB"
   - Host, port, database, username, password
4. Click **Test Connection** — show success with database version and response time
5. Click **Create**

**Voiceover:**
> "First, create a database persona. I'm connecting to our PostgreSQL database. Enter the credentials, test the connection — it's live. This persona lets me query financial data through natural language in Chat."

---

## Act 2: Explore Data in Chat (1:00 - 2:15)

**On screen:** Chat → select "Company Finance DB" persona

**Steps:**
1. Select the database persona from the dropdown
2. Ask: "What was our total revenue by month for the last 4 quarters?"
3. Show response with monthly revenue table
4. Ask: "What's our customer acquisition cost (CAC) trend? Compare Q3 to Q4"
5. Show response with CAC comparison
6. Ask: "Show me the top 10 customers by lifetime value"
7. Show response with customer data
8. Copy the key data points

**Voiceover:**
> "In Chat with the database persona, I ask business questions in plain English. Monthly revenue, CAC trends, top customers by LTV — the AI translates to SQL and returns clean data. I'm copying the key numbers as input for the full analysis."

---

## Act 3: Full Analysis in Workspace (2:15 - 3:30)

**On screen:** Workspace → New Project

**Steps:**
1. New Project: "Q4 Financial Review"
2. Description: Paste the data points, plus: "Produce a comprehensive Q4 financial review covering: revenue growth analysis, unit economics (CAC, LTV, LTV/CAC ratio), burn rate and runway, key risk factors, and Q1 forecast."
3. Agents:
   - **Financial Analyst** — financial metrics and analysis
   - **Data Analyst** — trend analysis and projections
   - **Risk Manager** — risk identification
4. Execute → Show results
5. Compiled output: structured financial review with metrics, trends, risks, and forecast

**Voiceover:**
> "Workspace takes the raw data and produces a full analysis. Three specialists: Financial Analyst for metrics, Data Analyst for trends and projections, Risk Manager for what could go wrong. The compiled output is a structured financial review — not a chat response, a real analysis."

---

## Act 4: Investor Report via Crew (3:30 - 4:45)

**On screen:** Crews → Create Crew

**Steps:**
1. Crew: "Investor Report Writer"
2. Paste the workspace analysis
3. Description: "Transform this financial analysis into an investor-ready quarterly report. Professional tone, lead with highlights, include forward-looking guidance."
4. Mode: **Sequential**
5. Agents:
   - **CFO Financial Strategist** — frames the narrative for investors
   - **Copywriter** — polishes the language
6. Create → Run
7. Show final output: executive summary, key metrics dashboard (text format), analysis sections, forward guidance

**Voiceover:**
> "The crew transforms analysis into an investor-ready report. CFO Financial Strategist frames the narrative — leading with wins, contextualizing challenges. Copywriter polishes. The result is something you can email to investors or present at a board meeting."

---

## Recap (4:45 - 5:00)

**On screen:** Flow diagram:
```
Persona (DB)      Chat              Workspace          Crew
┌──────────┐   ┌──────────┐   ┌──────────────┐   ┌─────────────┐
│ PostgreSQL│──>│ Query     │──>│ Fin. Analyst │──>│ CFO Advisor │
│ Connection│   │ revenue,  │   │ Data Analyst │   │ Copywriter  │
│           │   │ CAC, LTV  │   │ Risk Manager │   │             │
└──────────┘   └──────────┘   └──────────────┘   └─────────────┘
   Connect        Explore         Analyze            Report
```

**Voiceover:**
> "Database persona connects your data. Chat explores it conversationally. Workspace analyzes with specialists. Crew produces the polished report. From raw database to investor deck — without opening a spreadsheet."

**End card:** "Next: Telegram Bot for Customer Support"
