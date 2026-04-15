# Workflow 2: Weekly Content Machine

**Duration:** 7 minutes
**Scenario:** A solo founder sets up a repeatable content pipeline that produces and distributes content across Twitter/X, LinkedIn, and Instagram every week.
**Flow:** Blueprint → Crew (content creation) → Multi-channel publish (Twitter + LinkedIn + Instagram)

---

## Opening (0:00 - 0:20)

**On screen:** Calendar view mockup showing "Content day" every Monday

**Voiceover:**
> "You're a solo founder. Every week you need to post on LinkedIn, Twitter, and Instagram — but you barely have time to run the business, let alone create content. Let's build a content machine that runs every Monday in under 10 minutes."

---

## Act 1: Create a Custom Blueprint (0:20 - 1:30)

**On screen:** Blueprints → Create Blueprint

**Steps:**
1. Click **Create Blueprint**
2. Name: "Weekly Multi-Channel Content"
3. Category: Content
4. Tags: "weekly, social, multi-channel, content"
5. Content:
```markdown
## Weekly Content Pipeline

### Objective
Create one core piece of content and adapt it for 3 platforms.

### Steps
1. **Topic Selection** — Pick a trending topic in our industry that
   aligns with our expertise and audience interests
2. **Core Content** — Write a detailed LinkedIn article (800-1200 words)
   with data points, personal insights, and a clear takeaway
3. **Twitter Thread** — Distill into a 5-7 tweet thread with hooks,
   data highlights, and a CTA
4. **Instagram Caption** — Write a punchy 150-word caption with
   relevant hashtags and a visual content suggestion
5. **Quality Review** — Check brand voice consistency, factual accuracy,
   and platform-specific formatting across all three pieces

### Expected Output
Three platform-ready pieces of content from one core idea.
```
6. Click **Create**

**Voiceover:**
> "First, I'm saving my workflow as a blueprint so I never have to think about the structure again. Five steps: pick a topic, write the core article, adapt for Twitter, adapt for Instagram, and quality review. Create it once, use it forever."

---

## Act 2: Set Up Connections (1:30 - 2:30)

**On screen:** Connections page

**Steps:**
1. Show LinkedIn already connected (from previous setup)
2. Connect **Twitter/X**: paste API Key, API Secret, Access Token, Access Token Secret → Save
3. Connect **Instagram**: enter App ID, App Secret → Sign in with Instagram
4. Show all three with "Connected" badges

**Voiceover:**
> "Make sure your channels are connected. I already have LinkedIn. Let me add Twitter — paste the four credentials from the developer portal. And Instagram — enter the app credentials and sign in. All three are now live."

---

## Act 3: Build the Content Crew (2:30 - 4:30)

**On screen:** Crews → Create Crew

**Steps:**
1. Click **Create Crew**
2. Name: "Weekly Content Machine"
3. Click **"Use Blueprint"** → select "Weekly Multi-Channel Content"
4. Show description auto-filled from blueprint
5. Model: Select a strong model (Claude Sonnet or Qwen 3 14B)

**Execution Mode:**
6. Select **Sequential** — each agent builds on the previous

**Agent Team (from library):**
7. **Trend Analyst** — identifies the week's topic
8. **Content Strategist** — writes the core LinkedIn article
9. **Copywriter** — creates the Twitter thread
10. **Social Media Manager** — writes the Instagram caption
11. **Brand Voice Guardian** — reviews everything for consistency

**Connections:**
12. Select all three: LinkedIn, Twitter/X, Instagram
13. Enable **"Require approval"** on all three

**Review & Create:**
14. Show the full summary — 5 agents, 3 channels, sequential mode
15. Click **Create Crew**

**Voiceover:**
> "Now the crew. I use my blueprint to pre-fill the workflow, then add five agents in sequence — Trend Analyst picks the topic, Content Strategist writes the article, Copywriter creates the Twitter thread, Social Media Manager handles Instagram, and Brand Voice Guardian reviews everything. All three channels connected with approval required."

---

## Act 4: Run It (4:30 - 6:00)

**On screen:** Run the crew → progress modal

**Steps:**
1. Click **Run** on the crew card
2. Show progress modal:
   - Trend Analyst: identifies "AI-powered customer success" as the topic (completed)
   - Content Strategist: writes 1000-word LinkedIn article (running → completed)
   - Copywriter: creates 6-tweet thread (running → completed)
   - Social Media Manager: writes Instagram caption with hashtags (running → completed)
   - Brand Voice Guardian: reviews and flags minor adjustments (running → completed)
3. Show final output — three pieces of content clearly separated

**Approval Flow:**
4. LinkedIn post appears for approval → Review → **Approve**
5. Twitter thread appears → Review → **Approve**
6. Instagram caption appears → Review → **Approve**

**Voiceover:**
> "Run the crew. Watch the pipeline — topic research, article, Twitter thread, Instagram caption, quality review. Five agents, one workflow. Now the approval queue: review each piece before it goes live. LinkedIn article looks great — approve. Twitter thread is punchy — approve. Instagram caption with hashtags — approve. Three platforms, one session."

---

## Recap & Diagram (6:00 - 7:00)

**On screen:** Flow diagram:
```
Blueprint                  Crew (Sequential)                     Channels
┌──────────────┐    ┌────────────────────────────┐    ┌─────────────────┐
│ Weekly Multi- │───>│ 1. Trend Analyst            │───>│ LinkedIn ✓      │
│ Channel       │    │ 2. Content Strategist       │    │ Twitter/X ✓     │
│ Content       │    │ 3. Copywriter               │    │ Instagram ✓     │
│               │    │ 4. Social Media Manager     │    │ (all approved)  │
│               │    │ 5. Brand Voice Guardian     │    │                 │
└──────────────┘    └────────────────────────────┘    └─────────────────┘
```

**Voiceover:**
> "The pattern: a blueprint defines the workflow, a crew of five specialists executes it, and three channels distribute the content — all with your approval. Every Monday, just hit Run. One click, three platforms, five expert agents. That's your weekly content machine."

**Pro tip callout:**
> "Pro tip: Duplicate this crew and change the Trend Analyst's instructions to focus on different topics — product updates, industry news, customer stories. Build a library of content crews for different content themes."

**End card:** "Next: Client Proposal Pipeline"
