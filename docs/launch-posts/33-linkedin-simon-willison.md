# LinkedIn — Simon Willison / SQLite Story

**Target:** Comment on Simon Willison's LinkedIn posts about SQLite, local-first, or data tools

---

Your SQLite advocacy influenced a major architecture decision in my project.

I migrated ContextuAI Solo from MongoDB to SQLite by writing a compatibility layer that translates MongoDB's Motor API calls and query operators ($set, $in, $regex, $gt) to SQL/JSON expressions. The entire backend — 93+ business agents, multi-agent crews, user data — runs on a single .db file on the user's machine.

The result: a desktop AI assistant where all data is local, portable, and inspectable. No cloud database, no connection strings, no managed service costs.

SQLite isn't just for small projects. It powers the entire data layer of a production desktop app with complex querying needs.

GitHub: https://github.com/contextuai/contextuai-solo
