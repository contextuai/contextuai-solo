// Minimal Telegram bot using grammy.
// 1. Get a token from @BotFather on Telegram.
// 2. Copy .env.example to .env and paste the token.
// 3. `npm install && node bot.js`.

import { Bot } from "grammy";

const token = process.env.BOT_TOKEN;
if (!token) {
  console.error("BOT_TOKEN env var is required. See .env.example.");
  process.exit(1);
}

const bot = new Bot(token);

bot.command("start", (ctx) =>
  ctx.reply("Hi! I'm a starter bot. Try /ping.")
);

bot.command("ping", (ctx) => ctx.reply("pong"));

bot.on("message:text", (ctx) =>
  ctx.reply(`You said: ${ctx.message.text}`)
);

bot.start();
console.log("Bot is up. Press Ctrl+C to stop.");
