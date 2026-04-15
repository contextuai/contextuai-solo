# Workflow 6: Telegram Bot for Customer Support

**Duration:** 5 minutes
**Scenario:** A small business owner sets up a Telegram bot powered by a custom persona and crew that handles inbound customer questions and escalates complex ones.
**Flow:** Persona (brand expert) → Connection (Telegram) → Crew (inbound support) → Approval for escalations

---

## Opening (0:00 - 0:15)

**Voiceover:**
> "You run a small online business and customers message you on Telegram all day — product questions, order status, returns. Let's build an AI support bot that handles routine questions and flags the complex ones for you."

---

## Act 1: Create a Support Persona (0:15 - 1:00)

**On screen:** Personas → Create Persona

**Steps:**
1. Click **Create Persona** → select **Nexus Agent**
2. Name: "Customer Support — TechGear Store"
3. Category: Business
4. System Prompt:
```
You are the customer support agent for TechGear Store, an online electronics retailer.

Rules:
- Always be friendly, helpful, and professional
- For product questions: answer from your knowledge of our catalog (laptops, accessories, audio gear)
- For order status: ask for the order number and explain you'll check with the team
- For returns: explain our 30-day return policy and provide return instructions
- For complex issues or complaints: acknowledge the concern and say "I'm escalating this to our team for personal attention"
- Never make up order statuses or tracking numbers
- Keep responses concise — 2-3 sentences max
```
5. Click **Create**

**Voiceover:**
> "First, create a support persona with clear rules. I'm defining our store's personality, what it can answer, and when to escalate. The system prompt is the playbook — the AI follows these instructions for every customer interaction."

---

## Act 2: Connect Telegram (1:00 - 1:40)

**On screen:** Connections → Telegram

**Steps:**
1. Expand Telegram card
2. Paste the bot token (pre-created via BotFather)
3. Save → show "Connected" badge
4. Show direction toggles: **Inbound** ON, **Outbound** ON

**Voiceover:**
> "Connect your Telegram bot — paste the token from BotFather. Enable both inbound and outbound so the bot can receive and respond to messages."

---

## Act 3: Build the Support Crew (1:40 - 3:00)

**On screen:** Crews → Create Crew

**Steps:**
1. Crew: "Customer Support Bot"
2. Description: "Handle inbound Telegram messages from customers. Answer product questions, explain return policy, and escalate complex issues. Use the TechGear Store support persona guidelines."
3. Execution mode: **Sequential**
4. Agents:
   - **FAQ Auto-Responder** — handles common questions (product info, policies)
   - **Triage Agent** — classifies the request (simple / complex / complaint)
   - **Social Media Responder** — crafts the reply in the right tone
5. Connections: Select **Telegram**
   - Inbound enabled (receive customer messages)
   - Outbound enabled (send replies)
   - **"Require approval"** checked for outbound

6. Review: 3 agents, Telegram (inbound + outbound with approval)
7. Create

**Voiceover:**
> "The crew has three agents. FAQ Auto-Responder handles routine questions. Triage Agent classifies whether it's simple, complex, or a complaint. Social Media Responder crafts the reply. Telegram is connected with approval required — every response gets your sign-off before it's sent. Once you trust the quality, you can turn off approval."

---

## Act 4: Test It Live (3:00 - 4:15)

**On screen:** Split screen — Telegram app on left, Solo on right

**Steps:**
1. Open Telegram → send a message to the bot: "Do you have USB-C laptop chargers?"
2. Show the crew processing the inbound message in Solo
3. Show the drafted reply for approval: "Yes! We carry several USB-C laptop chargers. Our most popular is the 100W GaN charger ($45) — it works with MacBook, Dell, and Lenovo. Would you like me to share the product link?"
4. Approve → show reply appearing in Telegram
5. Send another: "I want to return my order, it's been 3 weeks"
6. Show crew processing → draft: "Happy to help with your return! Since it's within our 30-day window, here's what to do: [return instructions]. Would you like me to start the process?"
7. Approve → reply sent
8. Send a complaint: "This is the third time my order arrived damaged. I'm furious."
9. Show crew processing → draft: "I'm truly sorry about this recurring issue — that's unacceptable. I'm escalating this to our team immediately for personal attention. You'll hear from us within 24 hours."
10. Approve → reply sent

**Voiceover:**
> "Let's test it live. A customer asks about chargers — the crew drafts a helpful, specific reply. Approve and it's sent. A return request — the crew explains the policy and offers to help. A complaint — it escalates with empathy. Every response is reviewed before the customer sees it."

---

## Closing (4:15 - 5:00)

**On screen:** Crew dashboard showing the support crew with completed runs

**Voiceover:**
> "Once you're confident in the quality, disable approval and let the bot handle routine questions automatically. Keep approval on for escalations. You just built a 24/7 support bot — powered by AI agents that understand your brand, your policies, and your customers."

**On screen:** Flow diagram:
```
Customer          Telegram         Crew (Sequential)          You
┌──────────┐   ┌──────────┐   ┌──────────────────┐   ┌──────────────┐
│ "Do you  │──>│ Inbound  │──>│ FAQ Responder    │──>│ Review draft │
│  have    │   │ message  │   │ Triage Agent     │   │ Approve /    │
│  USB-C?" │   │          │   │ Social Responder │   │ Edit         │
└──────────┘   └──────────┘   └──────────────────┘   └──────────────┘
                                                          │
                                                     ┌────▼──────┐
                                                     │ Reply sent │
                                                     │ via Telegram│
                                                     └───────────┘
```

**End card:** "Next: Competitive Intel to Board Deck"
