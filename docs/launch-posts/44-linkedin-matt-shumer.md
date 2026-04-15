# LinkedIn — Matt Shumer / Agent Design

**Target:** Comment on Matt Shumer's LinkedIn posts about AI agents, prompt engineering, or agent architectures

---

Designing 93 business agents taught me more about prompting than any course.

Each agent in ContextuAI Solo is a markdown file with:
- A system prompt tuned for a specific business role
- Recommended model size (some roles need reasoning, others need speed)
- Tool configurations
- Category classification

The agents span 13 business categories: C-suite strategy, marketing & sales, finance & operations, HR, legal, product, research, creative, data analytics, IT security, and more.

**What I learned:**

1. **Role specificity matters more than length.** "You are a CFO analyzing cash flow" beats a 2000-word generic finance prompt.

2. **Model matching is underrated.** Some agents work great on 1.5B models (simple formatting tasks). Others need 14B+ (strategic analysis with nuance).

3. **Multi-agent crews expose prompt weaknesses.** When Agent A's output feeds Agent B, vague prompts compound. Sequential execution is the best debugging tool for prompt quality.

4. **Users don't want to prompt.** The 93 pre-built agents exist so users never write a system prompt. Pick a role, start chatting.

All open source — inspect every prompt, fork and customize.

GitHub: https://github.com/contextuai/contextuai-solo
