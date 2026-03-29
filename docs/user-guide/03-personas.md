# Personas

Personas are specialized AI personalities you can create and assign to chat conversations. Each persona has a type, custom instructions, and optional credentials for connecting to databases or external services.

![Personas](../screenshots/004-Personas.png)

---

## Getting Started

1. Navigate to **Personas** from the sidebar.
2. Browse your existing personas or click **Create Persona**.
3. Once created, select a persona from the Chat input area to use it in conversations.

## Persona Types

ContextuAI Solo includes 10 persona types, each designed for a different use case:

| Type | What it does |
|------|-------------|
| **Nexus Agent** | General-purpose AI with custom expertise, personality, and style |
| **Web Researcher** | Searches the web, fetches URLs, and extracts information |
| **PostgreSQL** | Connects to PostgreSQL databases for queries and analysis |
| **MySQL** | Connects to MySQL databases |
| **MSSQL** | Connects to Microsoft SQL Server |
| **Snowflake** | Connects to Snowflake cloud data warehouse |
| **MongoDB** | Connects to MongoDB NoSQL databases |
| **MCP Server** | Connects to Model Context Protocol servers for external tools |
| **API Connector** | Connects to REST APIs, GraphQL endpoints, and webhooks |
| **File Operations** | Reads, writes, and manages files in a directory |

## Creating a Persona

The creation wizard has 2 steps:

![Create Persona](../screenshots/005-CreatePersona.png)

### Step 1: Choose a Type

- Browse the type grid — each card shows an icon, name, and description.
- Use the **search box** to filter types by name.
- Click a type card to select it and move to Step 2.

### Step 2: Configure Details

Fill in the persona details:

- **Name** (required) — Give your persona a recognizable name (e.g., "Sales DB Analyst").
- **Category** — Choose from General, Technical, Creative, Business, or Custom.
- **Description** — A short summary of what this persona does.
- **Credentials** — Type-specific fields appear based on the type you selected:
  - Database types: host, port, database name, username, password
  - API Connector: base URL, API key
  - MCP Server: server URL, transport type
  - Web Researcher: max results setting
- **System Prompt** — Custom instructions that define how the AI behaves when using this persona.

Click **Create** to save.

### Test Connection

For database and integration types (PostgreSQL, MySQL, MSSQL, Snowflake, MongoDB, MCP Server), a **Test Connection** button lets you verify credentials before saving. It shows connection details like response time and database version on success.

## Managing Personas

### Editing

Hover over a persona card and click the **pencil icon** to edit. The edit form opens directly on Step 2 with all fields pre-populated.

### Deleting

Hover over a persona card and click the **trash icon**. A confirmation dialog appears — click **Delete** to confirm.

### Searching and Filtering

- **Search** — Use the search box to filter personas by name or description.
- **Category filter** — Click a category button (All, General, Technical, Creative, Business, Custom) to filter by category.
- Both filters work together.

## Using Personas in Chat

1. Open the **Chat** page.
2. Click the **persona dropdown** in the input area.
3. Select a persona — the AI will now follow that persona's instructions.
4. Select **"None (default)"** to return to the standard AI behavior.

## Tips

- **Start with a Nexus Agent** if you just want to customize the AI's personality and expertise without connecting to external services.
- **Use database personas** to ask questions about your data in plain English — the AI translates your questions into SQL.
- **Keep system prompts specific** — the more detailed your instructions, the more consistent the AI's behavior.
- **Test connections before chatting** — it's frustrating to discover bad credentials mid-conversation.
- **Create category-specific personas** (e.g., "Marketing Writer", "Finance Analyst") to quickly switch between different work contexts.
