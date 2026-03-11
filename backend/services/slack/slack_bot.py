"""
Slack Bot Service — Slash commands, events, and interactive components.

Integrates ContextuAI automations with Slack via the Bolt framework.
Single /slack/events endpoint handles all Slack interactions.
"""

import os
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Env vars (set in .env / Docker)
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")

# Guard: only initialise when credentials are configured
_slack_app = None
_slack_handler = None


def _is_configured() -> bool:
    return bool(SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET)


def get_slack_app():
    """Lazy-initialise the Slack Bolt async app."""
    global _slack_app
    if _slack_app is not None:
        return _slack_app
    if not _is_configured():
        return None

    from slack_bolt.async_app import AsyncApp

    _slack_app = AsyncApp(
        token=SLACK_BOT_TOKEN,
        signing_secret=SLACK_SIGNING_SECRET,
    )
    _register_handlers(_slack_app)
    logger.info("Slack Bolt app initialised")
    return _slack_app


def get_slack_handler():
    """Get (or create) the FastAPI request handler."""
    global _slack_handler
    if _slack_handler is not None:
        return _slack_handler

    app = get_slack_app()
    if app is None:
        return None

    from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

    _slack_handler = AsyncSlackRequestHandler(app)
    return _slack_handler


# ------------------------------------------------------------------
# Handler registration
# ------------------------------------------------------------------

def _register_handlers(app):
    """Wire up all slash-command, event, and action handlers."""

    # ---- /contextuai slash command ----
    @app.command("/contextuai")
    async def handle_command(ack, command, respond, client):
        await ack()

        text = (command.get("text") or "").strip()
        user_id = command["user_id"]
        channel_id = command["channel_id"]

        if not text or text in ("help", "?"):
            await respond(
                text=(
                    "*ContextuAI Commands*\n"
                    "• `/contextuai run <name>` — trigger an automation\n"
                    "• `/contextuai list` — list your automations\n"
                    "• `/contextuai status <id>` — check execution status\n"
                    "• `/contextuai help` — show this message"
                ),
                response_type="ephemeral",
            )
            return

        # --- /contextuai run <name_or_id> ---
        if text.startswith("run "):
            automation_ref = text[4:].strip().strip('"').strip("'")
            await _handle_run(respond, user_id, channel_id, automation_ref)
            return

        # --- /contextuai list ---
        if text == "list":
            await _handle_list(respond, user_id)
            return

        # --- /contextuai status <execution_id> ---
        if text.startswith("status "):
            exec_id = text[7:].strip()
            await _handle_status(respond, exec_id)
            return

        await respond(
            text=f"Unknown sub-command: `{text}`. Try `/contextuai help`.",
            response_type="ephemeral",
        )

    # ---- @mention ----
    @app.event("app_mention")
    async def handle_mention(event, say):
        user_id = event["user"]
        text = event.get("text", "")

        # Strip the mention prefix to get the user's intent
        clean = re.sub(r"<@[A-Z0-9]+>", "", text).strip()

        if not clean:
            await say(
                f"Hey <@{user_id}>! Try `/contextuai run \"automation name\"` "
                "to trigger an automation, or `/contextuai help` for more."
            )
            return

        # Treat mentions as ad-hoc run requests
        if clean.lower().startswith("run "):
            automation_ref = clean[4:].strip().strip('"').strip("'")
            await say(
                f":rocket: <@{user_id}> requested automation `{automation_ref}`. "
                "Dispatching..."
            )
            await _dispatch_automation(
                automation_ref=automation_ref,
                slack_user_id=user_id,
                channel_id=event["channel"],
            )
        else:
            await say(
                f"<@{user_id}> I'm not sure what you mean. "
                "Try: `@ContextuAI run \"daily-report\"`"
            )

    # ---- Catch-all message handler (required to prevent unhandled event warnings) ----
    @app.event("message")
    async def handle_message():
        pass

    # ---- Interactive: button actions ----
    @app.action("rerun_automation")
    async def handle_rerun(ack, action, body, respond):
        await ack()
        automation_id = action["value"]
        user_id = body["user"]["id"]
        await respond(
            text=f":arrows_counterclockwise: Re-running automation `{automation_id}`...",
            replace_original=False,
        )
        await _dispatch_automation(
            automation_ref=automation_id,
            slack_user_id=user_id,
            channel_id=body.get("channel", {}).get("id"),
        )

    @app.action("cancel_automation")
    async def handle_cancel(ack, action, respond):
        await ack()
        await respond(
            text=f":x: Automation request cancelled.",
            replace_original=True,
        )


# ------------------------------------------------------------------
# Business logic helpers
# ------------------------------------------------------------------

async def _handle_run(respond, user_id: str, channel_id: str, automation_ref: str):
    """Trigger an automation from Slack."""
    result = await _dispatch_automation(
        automation_ref=automation_ref,
        slack_user_id=user_id,
        channel_id=channel_id,
    )

    if result and result.get("success"):
        await respond(
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f":rocket: *Automation triggered*\n"
                            f"• Name: `{automation_ref}`\n"
                            f"• Task ID: `{result.get('task_id', 'N/A')}`\n"
                            f"• Requested by: <@{user_id}>"
                        ),
                    },
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Re-run"},
                            "style": "primary",
                            "action_id": "rerun_automation",
                            "value": result.get("automation_id", automation_ref),
                        },
                    ],
                },
            ],
            text=f"Automation triggered: {automation_ref}",
            response_type="in_channel",
        )
    else:
        error = result.get("error", "Unknown error") if result else "Automation not found or inactive"
        await respond(
            text=f":warning: Failed to trigger `{automation_ref}`: {error}",
            response_type="ephemeral",
        )


async def _handle_list(respond, user_id: str):
    """List automations available to the Slack user."""
    try:
        from database import get_database
        from repositories import AutomationRepository

        db = await get_database()
        repo = AutomationRepository(db)

        # Try to find automations by slack metadata or just list active ones
        automations = await repo.get_all(
            filter={"status": "active"},
            sort=[("name", 1)],
        )

        if not automations:
            await respond(text="No active automations found.", response_type="ephemeral")
            return

        lines = [f"*Active Automations ({len(automations)})*\n"]
        for a in automations[:20]:  # Cap at 20
            trigger = a.get("trigger_type", "manual")
            lines.append(f"• `{a.get('name', 'Unnamed')}` — {trigger} (ID: `{a.get('id', a.get('_id', '?'))}`)")

        await respond(text="\n".join(lines), response_type="ephemeral")
    except Exception as e:
        logger.error(f"Slack list error: {e}")
        await respond(text=f":warning: Error listing automations: {e}", response_type="ephemeral")


async def _handle_status(respond, exec_id: str):
    """Check execution status."""
    try:
        from database import get_database

        db = await get_database()
        doc = await db.automation_executions.find_one({"task_id": exec_id})
        if not doc:
            doc = await db.automation_executions.find_one({"_id": exec_id})

        if not doc:
            await respond(text=f"Execution `{exec_id}` not found.", response_type="ephemeral")
            return

        status = doc.get("status", "unknown")
        emoji = {
            "completed": ":white_check_mark:",
            "running": ":hourglass_flowing_sand:",
            "failed": ":x:",
            "pending": ":clock1:",
        }.get(status, ":question:")

        await respond(
            text=(
                f"{emoji} *Execution Status*\n"
                f"• ID: `{exec_id}`\n"
                f"• Status: `{status}`\n"
                f"• Started: {doc.get('started_at', 'N/A')}\n"
                f"• Finished: {doc.get('completed_at', 'N/A')}"
            ),
            response_type="ephemeral",
        )
    except Exception as e:
        logger.error(f"Slack status check error: {e}")
        await respond(text=f":warning: Error: {e}", response_type="ephemeral")


async def _dispatch_automation(
    automation_ref: str,
    slack_user_id: str,
    channel_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Find and dispatch an automation by name or ID.

    Returns dict with success/error info.
    """
    try:
        from database import get_database
        from repositories import AutomationRepository

        db = await get_database()
        repo = AutomationRepository(db)

        # Try by ID first, then by name
        automation = await repo.get_by_id(automation_ref)
        if not automation:
            # Search by name (case-insensitive)
            automation = await repo.collection.find_one({
                "name": {"$regex": f"^{re.escape(automation_ref)}$", "$options": "i"},
                "status": "active",
            })
            if automation:
                automation = repo._convert_id(automation)

        if not automation:
            return {"success": False, "error": "Automation not found"}

        if automation.get("status") != "active":
            return {"success": False, "error": "Automation is not active"}

        # Dispatch via Celery
        from tasks.automation_tasks import execute_automation

        user_id = automation.get("user_id", automation.get("created_by", "slack"))
        payload = {
            "trigger_source": "slack",
            "slack_user_id": slack_user_id,
            "slack_channel_id": channel_id,
        }
        task = execute_automation.delay(str(automation["id"]), user_id, payload)

        return {
            "success": True,
            "automation_id": str(automation["id"]),
            "task_id": task.id,
        }
    except Exception as e:
        logger.error(f"Failed to dispatch automation from Slack: {e}")
        return {"success": False, "error": str(e)}


# ------------------------------------------------------------------
# Proactive messaging (called from automation output actions)
# ------------------------------------------------------------------

async def send_slack_message(
    channel: str,
    text: str,
    blocks: Optional[list] = None,
) -> bool:
    """
    Send a proactive message to a Slack channel.

    Can be used as an output action after automation execution.
    """
    if not _is_configured():
        logger.warning("Slack not configured, skipping message send")
        return False

    try:
        from slack_sdk.web.async_client import AsyncWebClient

        client = AsyncWebClient(token=SLACK_BOT_TOKEN)
        await client.chat_postMessage(
            channel=channel,
            text=text,
            blocks=blocks,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send Slack message: {e}")
        return False
