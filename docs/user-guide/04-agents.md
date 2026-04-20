# Agents

The Agent Library contains 96 pre-built business agents organized by department. Each agent is a specialized AI role with a detailed system prompt, recommended tools, and domain expertise. You can also create your own custom agents.

![Agent Library](../screenshots/006-AgentLibrary.png)

---

## Getting Started

1. Navigate to **Agents** from the sidebar.
2. Browse or search the library to find agents relevant to your business.
3. Click any agent card to view its full details and system prompt.
4. Use agents in [Crews](05-crews.md) or [Workspace](07-workspace.md) projects.

## Agent Categories

| Category | Agents | Examples |
|----------|--------|----------|
| **C-Suite** | 12 | CEO Advisor, CFO Analyst, CTO Strategist, CMO, CHRO |
| **Marketing & Sales** | 11 | Content Strategist, Copywriter, SEO Specialist, Sales Engineer |
| **Social Engagement** | 12 | Social Media Responder, Brand Voice Guardian, Sentiment Analyzer |
| **Startup & Venture** | 10 | Fundraising Advisor, Growth Hacker, Pitch Deck Architect |
| **Specialized** | 9 | Solutions Architect, Competitive Intelligence, AI Ethics Advisor |
| **Data Analytics** | 6 | Data Analyst, Data Scientist, BI Analyst |
| **Design & UX** | 6 | UI Designer, UX Researcher, Brand Designer |
| **Finance & Operations** | 6 | Financial Analyst, Pricing Strategist, Risk Manager |
| **Product Management** | 6 | Product Manager, Agile Coach, Technical Writer |
| **Legal & Compliance** | 5 | General Counsel, Privacy Officer, Contract Specialist |
| **IT & Security** | 5 | SOC Analyst, Penetration Tester, Network Architect |
| **HR & People** | 5 | Talent Acquisition, People Operations, L&D Specialist |

## Browsing and Searching

### Search

Use the search box to find agents by name, role, description, or category. The search is case-insensitive and updates results in real-time.

### Filter by Role

Click a role pill to filter agents:

- **All** — show every agent
- **Researcher** — agents focused on finding and analyzing information
- **Writer** — content creation and copywriting agents
- **Analyst** — data analysis and strategic assessment agents
- **Designer** — UI, UX, and brand design agents
- **Developer** — engineering-focused agents
- **Reviewer** — quality assurance and review agents
- **Planner** — strategy and project planning agents

Each pill shows a count badge (e.g., "Analyst (15)").

Search and role filters work together — you can search within a filtered role.

## Agent Cards

Each card displays:

- **Agent name** and **role badge** (color-coded)
- **Description** (up to 3 lines)
- **Tools** the agent can use (e.g., Web Search, Database, Calculator)
- **Category badge** (e.g., Marketing-Sales, C-Suite)
- **Creation date**
- **Public/Private indicator** (globe or lock icon)

## Agent Details

Click any agent card to open the detail panel on the right side. Here you can view and edit:

- Name, role, and description
- **System prompt** — the full instructions that define the agent's behavior
- **Tools** — toggle which tools the agent has access to (Web Search, Database, Files, Calculator, Code Interpreter)
- **Model** — override which AI model this agent uses
- **Category** — organizational label

## Creating a Custom Agent

![Create Agent](../screenshots/007-CreateAgent.png)

1. Click **Create Agent** in the top-right corner.
2. Fill in the form:
   - **Name** (required) — e.g., "Market Researcher"
   - **Role** (required) — select from the dropdown
   - **Description** — what the agent does
   - **System Prompt** — detailed instructions (a template is suggested based on the role you select)
   - **Tools** — check which tools the agent should have
   - **Model** — optionally pick a specific AI model
   - **Category** — for organization
3. Click **Create Agent**.

### Role-Based Templates

When you select a role, a suggested system prompt template appears. Click **"Use suggested template"** to auto-fill the system prompt with a starting point tailored to that role.

## Tips

- **Don't create agents from scratch** unless you need something unique — the 96 pre-built agents cover most business functions.
- **Combine agents in Crews** for multi-step tasks. For example, pair a "Market Researcher" with a "Content Strategist" and a "Copywriter" for end-to-end content creation.
- **Customize system prompts** in the detail panel to fine-tune an existing agent's behavior for your specific business context.
- **Use the search** when you know roughly what you need — typing "pricing" will find the Pricing Strategist even if you don't know the exact name.
- **Check the agent's tools** — an agent with "Web Search" enabled can pull real-time information, while one without it relies only on its training data.
