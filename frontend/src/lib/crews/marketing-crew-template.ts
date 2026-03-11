/**
 * Marketing Crew Template
 *
 * A pre-configured crew template for the "Daily Marketing Engine" —
 * an autonomous crew that runs once per day to analyze AI industry trends,
 * create platform-optimized content, and distribute it to connected channels.
 *
 * This is a showcase/dogfooding feature: ContextuAI Solo marketing itself
 * using its own crew system.
 *
 * Usage:
 *   import { MARKETING_CREW_TEMPLATE } from "@/lib/crews/marketing-crew-template";
 *   // Pass to crewsApi.create() or pre-fill the CrewBuilder form
 */

export const MARKETING_CREW_TEMPLATE = {
  name: "Daily Marketing Engine",
  description:
    "Autonomous crew that generates and distributes AI-focused content daily. Analyzes trends, creates platform-optimized posts, and publishes to connected channels.",
  agents: [
    {
      name: "AI Industry Trend Analyst",
      role: "Researcher",
      task: "Scan AI industry news, identify 3-5 trending topics relevant to business AI adoption, and rank them by engagement potential and timeliness.",
      order: 1,
    },
    {
      name: "AI Content Strategist",
      role: "Writer",
      task: "Using the top trends identified, create 1 LinkedIn post (150-300 words), 1 Twitter thread (5-8 tweets), and 1 short blog outline. Apply brand voice settings. Include hooks, data points, and CTAs.",
      order: 2,
    },
    {
      name: "Distribution Channel Manager",
      role: "Publisher",
      task: "Format the created content for each connected platform (Telegram, Discord, LinkedIn). Adapt formatting, add hashtags, and prepare for publishing. If channels are connected, queue for distribution.",
      order: 3,
    },
  ],
  execution_config: {
    mode: "sequential" as const,
    max_rounds: 1,
    timeout_seconds: 600,
  },
  schedule: {
    enabled: true,
    cron: "0 9 * * *", // Every day at 9 AM
    timezone: "UTC",
    description: "Daily at 9:00 AM UTC",
  },
};
