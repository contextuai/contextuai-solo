"""
Automation Output Service
Processes output actions after automation execution completes.
Supports PDF/PPTX generation, email sending, webhook notifications, and file exports.
"""

import json
import csv
import io
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from models.automation_models import OutputAction, OutputActionType, AutomationExecutionResponse

logger = logging.getLogger(__name__)


class AutomationOutputService:
    """Service for processing output actions after automation execution."""

    def __init__(self):
        self._file_storage = None
        self._doc_service = None

    def _get_file_storage(self):
        if self._file_storage is None:
            from services.file_storage_service import FileStorageService
            self._file_storage = FileStorageService()
        return self._file_storage

    def _get_doc_service(self):
        if self._doc_service is None:
            from services.workspace.document_service import DocumentGenerationService
            self._doc_service = DocumentGenerationService()
        return self._doc_service

    async def process_output_actions(
        self,
        execution: AutomationExecutionResponse,
        output_actions: List[Dict[str, Any]],
        user_id: str
    ) -> List[Dict[str, Any]]:
        """
        Process all output actions for a completed execution.

        Args:
            execution: The completed execution response
            output_actions: List of output action configurations
            user_id: The user who owns this execution

        Returns:
            List of output results with status and details
        """
        results = []
        for action_data in output_actions:
            try:
                action = OutputAction(**action_data) if isinstance(action_data, dict) else action_data
                result = await self._execute_action(action, execution, user_id)
                results.append(result)
            except Exception as e:
                logger.error(f"Output action failed: {e}")
                results.append({
                    "type": action_data.get("type", "unknown") if isinstance(action_data, dict) else str(action_data),
                    "status": "failed",
                    "error": str(e)
                })
        return results

    async def _execute_action(
        self,
        action: OutputAction,
        execution: AutomationExecutionResponse,
        user_id: str
    ) -> Dict[str, Any]:
        """Route to the appropriate action handler."""
        handlers = {
            OutputActionType.GENERATE_PDF: self._generate_pdf,
            OutputActionType.GENERATE_PPTX: self._generate_pptx,
            OutputActionType.SEND_EMAIL: self._send_email,
            OutputActionType.WEBHOOK: self._send_webhook,
            OutputActionType.SAVE_FILE: self._save_file,
            OutputActionType.SLACK_MESSAGE: self._send_slack_message,
        }

        handler = handlers.get(action.type)
        if not handler:
            return {
                "type": action.type.value,
                "status": "failed",
                "error": f"Unknown action type: {action.type}"
            }

        return await handler(execution, action.config, user_id)

    async def _generate_pdf(
        self,
        execution: AutomationExecutionResponse,
        config: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Generate a PDF report from execution results."""
        try:
            doc_service = self._get_doc_service()
            file_storage = self._get_file_storage()

            title = config.get("title", "Automation Report")
            template = config.get("template", "report")

            # Build markdown content from execution results
            markdown = self._build_report_markdown(execution, title)

            # Generate PDF
            pdf_bytes = doc_service.markdown_to_pdf(
                content=markdown,
                template=template,
                title=title,
                agent_count=execution.total_steps
            )

            # Store via FileStorageService
            filename = f"{title.replace(' ', '_')}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
            file_meta = await file_storage.upload_file(
                user_id=user_id,
                filename=filename,
                content=pdf_bytes,
                content_type="application/pdf"
            )

            logger.info(f"PDF generated: {filename} ({len(pdf_bytes)} bytes)")
            return {
                "type": "generate_pdf",
                "status": "success",
                "file_id": file_meta["file_id"],
                "filename": filename,
                "size": len(pdf_bytes)
            }
        except Exception as e:
            logger.error(f"PDF generation failed: {e}")
            return {
                "type": "generate_pdf",
                "status": "failed",
                "error": str(e)
            }

    async def _generate_pptx(
        self,
        execution: AutomationExecutionResponse,
        config: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Generate a PPTX presentation from execution results."""
        try:
            doc_service = self._get_doc_service()
            file_storage = self._get_file_storage()

            title = config.get("title", "Automation Report")

            # Build markdown content from execution results
            markdown = self._build_report_markdown(execution, title)

            # Generate PPTX
            pptx_bytes = doc_service.markdown_to_pptx(
                content=markdown,
                title=title
            )

            # Store via FileStorageService
            filename = f"{title.replace(' ', '_')}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pptx"
            file_meta = await file_storage.upload_file(
                user_id=user_id,
                filename=filename,
                content=pptx_bytes,
                content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
            )

            logger.info(f"PPTX generated: {filename} ({len(pptx_bytes)} bytes)")
            return {
                "type": "generate_pptx",
                "status": "success",
                "file_id": file_meta["file_id"],
                "filename": filename,
                "size": len(pptx_bytes)
            }
        except Exception as e:
            logger.error(f"PPTX generation failed: {e}")
            return {
                "type": "generate_pptx",
                "status": "failed",
                "error": str(e)
            }

    async def _send_email(
        self,
        execution: AutomationExecutionResponse,
        config: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Send email with execution results."""
        try:
            import boto3

            to_addresses = config.get("to", [])
            subject = config.get("subject", f"Automation Report: {execution.automation_id}")
            include_pdf = config.get("include_pdf", False)

            if not to_addresses:
                return {
                    "type": "send_email",
                    "status": "failed",
                    "error": "No recipient addresses configured"
                }

            # Build email body from execution results
            body_text = self._build_email_body(execution)

            # Send via SES
            ses_client = boto3.client("ses", region_name="us-east-1")

            email_params = {
                "Source": config.get("from", "noreply@contextuai.com"),
                "Destination": {"ToAddresses": to_addresses},
                "Message": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": body_text, "Charset": "UTF-8"},
                        "Html": {"Data": self._build_email_html(execution, subject), "Charset": "UTF-8"}
                    }
                }
            }

            response = ses_client.send_email(**email_params)
            message_id = response.get("MessageId", "unknown")

            logger.info(f"Email sent to {len(to_addresses)} recipients (MessageId: {message_id})")
            return {
                "type": "send_email",
                "status": "success",
                "details": {
                    "recipients": len(to_addresses),
                    "message_id": message_id
                }
            }
        except Exception as e:
            logger.error(f"Email sending failed: {e}")
            return {
                "type": "send_email",
                "status": "failed",
                "error": str(e)
            }

    async def _send_webhook(
        self,
        execution: AutomationExecutionResponse,
        config: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Send execution results to a webhook URL."""
        try:
            import httpx

            url = config.get("url")
            method = config.get("method", "POST").upper()
            headers = config.get("headers", {})

            if not url:
                return {
                    "type": "webhook",
                    "status": "failed",
                    "error": "No webhook URL configured"
                }

            # Build webhook payload
            payload = {
                "execution_id": execution.execution_id,
                "automation_id": execution.automation_id,
                "status": execution.status.value if hasattr(execution.status, 'value') else execution.status,
                "started_at": execution.started_at,
                "completed_at": execution.completed_at,
                "duration_ms": execution.duration_ms,
                "total_steps": execution.total_steps,
                "successful_steps": execution.successful_steps,
                "failed_steps": execution.failed_steps,
                "final_result": execution.final_result,
                "error_message": execution.error_message,
                "steps": [
                    {
                        "step_number": step.step_number,
                        "persona": step.persona,
                        "instruction": step.instruction,
                        "status": step.status.value if hasattr(step.status, 'value') else step.status,
                        "result": step.result,
                        "duration_ms": step.duration_ms
                    }
                    for step in execution.steps
                ]
            }

            headers.setdefault("Content-Type", "application/json")

            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == "PUT":
                    response = await client.put(url, json=payload, headers=headers)
                else:
                    response = await client.post(url, json=payload, headers=headers)

            logger.info(f"Webhook sent to {url}: {response.status_code}")
            return {
                "type": "webhook",
                "status": "success",
                "details": {
                    "url": url,
                    "status_code": response.status_code
                }
            }
        except Exception as e:
            logger.error(f"Webhook failed: {e}")
            return {
                "type": "webhook",
                "status": "failed",
                "error": str(e)
            }

    async def _save_file(
        self,
        execution: AutomationExecutionResponse,
        config: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Save execution results as a file (JSON, CSV, or TXT)."""
        try:
            file_storage = self._get_file_storage()

            format_type = config.get("format", "json")
            base_filename = config.get("filename", "automation_results")
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')

            if format_type == "json":
                content = self._format_as_json(execution)
                filename = f"{base_filename}_{timestamp}.json"
                content_type = "application/json"
            elif format_type == "csv":
                content = self._format_as_csv(execution)
                filename = f"{base_filename}_{timestamp}.csv"
                content_type = "text/csv"
            else:
                content = self._format_as_txt(execution)
                filename = f"{base_filename}_{timestamp}.txt"
                content_type = "text/plain"

            content_bytes = content.encode("utf-8")

            file_meta = await file_storage.upload_file(
                user_id=user_id,
                filename=filename,
                content=content_bytes,
                content_type=content_type
            )

            logger.info(f"File saved: {filename} ({len(content_bytes)} bytes)")
            return {
                "type": "save_file",
                "status": "success",
                "file_id": file_meta["file_id"],
                "filename": filename,
                "size": len(content_bytes)
            }
        except Exception as e:
            logger.error(f"File save failed: {e}")
            return {
                "type": "save_file",
                "status": "failed",
                "error": str(e)
            }

    async def _send_slack_message(
        self,
        execution: AutomationExecutionResponse,
        config: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Post execution results to a Slack channel."""
        try:
            from services.slack.slack_bot import send_slack_message

            channel = config.get("channel")
            if not channel:
                return {
                    "type": "slack_message",
                    "status": "failed",
                    "error": "No Slack channel configured"
                }

            status = execution.status.value if hasattr(execution.status, 'value') else execution.status
            status_emoji = ":white_check_mark:" if status == "success" else ":x:" if status == "failed" else ":warning:"

            # Build rich Slack blocks
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{config.get('title', 'Automation Report')}"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Status:* {status_emoji} `{status}`"},
                        {"type": "mrkdwn", "text": f"*Duration:* {execution.duration_ms or 0}ms"},
                        {"type": "mrkdwn", "text": f"*Steps:* {execution.successful_steps}/{execution.total_steps} passed"},
                        {"type": "mrkdwn", "text": f"*Execution:* `{execution.execution_id[:12]}...`"},
                    ]
                },
            ]

            # Add final result summary if available
            if execution.final_result:
                summary = execution.final_result[:2900]  # Slack block text limit ~3000 chars
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Result:*\n{summary}"}
                })

            fallback_text = f"Automation {status}: {execution.successful_steps}/{execution.total_steps} steps passed"

            sent = await send_slack_message(
                channel=channel,
                text=fallback_text,
                blocks=blocks,
            )

            if sent:
                logger.info(f"Slack message sent to {channel}")
                return {
                    "type": "slack_message",
                    "status": "success",
                    "details": {"channel": channel}
                }
            else:
                return {
                    "type": "slack_message",
                    "status": "failed",
                    "error": "Slack not configured or send failed"
                }
        except Exception as e:
            logger.error(f"Slack message failed: {e}")
            return {
                "type": "slack_message",
                "status": "failed",
                "error": str(e)
            }

    # --- Formatting helpers ---

    def _build_report_markdown(self, execution: AutomationExecutionResponse, title: str) -> str:
        """Build markdown report from execution results."""
        lines = [
            f"# {title}",
            "",
            f"**Execution ID:** {execution.execution_id}",
            f"**Status:** {execution.status.value if hasattr(execution.status, 'value') else execution.status}",
            f"**Started:** {execution.started_at}",
            f"**Completed:** {execution.completed_at or 'N/A'}",
            f"**Duration:** {execution.duration_ms or 0}ms",
            f"**Steps:** {execution.successful_steps}/{execution.total_steps} successful",
            "",
        ]

        for step in execution.steps:
            status_icon = "+" if (step.status.value if hasattr(step.status, 'value') else step.status) == "success" else "x"
            lines.append(f"## Step {step.step_number}: @{step.persona}")
            lines.append(f"**Instruction:** {step.instruction}")
            lines.append(f"**Status:** {step.status.value if hasattr(step.status, 'value') else step.status}")
            lines.append(f"**Duration:** {step.duration_ms}ms")
            lines.append("")
            lines.append(step.result)
            lines.append("")

        if execution.final_result:
            lines.append("## Summary")
            lines.append(execution.final_result)

        return "\n".join(lines)

    def _build_email_body(self, execution: AutomationExecutionResponse) -> str:
        """Build plain text email body."""
        status = execution.status.value if hasattr(execution.status, 'value') else execution.status
        lines = [
            f"Automation Execution Report",
            f"{'='*40}",
            f"Status: {status}",
            f"Duration: {execution.duration_ms or 0}ms",
            f"Steps: {execution.successful_steps}/{execution.total_steps} successful",
            "",
        ]

        for step in execution.steps:
            step_status = step.status.value if hasattr(step.status, 'value') else step.status
            lines.append(f"Step {step.step_number} (@{step.persona}): {step_status}")
            lines.append(f"  {step.instruction}")
            lines.append(f"  Result: {step.result[:200]}...")
            lines.append("")

        if execution.final_result:
            lines.append("Final Result:")
            lines.append(execution.final_result)

        return "\n".join(lines)

    def _build_email_html(self, execution: AutomationExecutionResponse, subject: str) -> str:
        """Build HTML email body."""
        status = execution.status.value if hasattr(execution.status, 'value') else execution.status
        status_color = "#22c55e" if status == "success" else "#ef4444" if status == "failed" else "#f59e0b"

        steps_html = ""
        for step in execution.steps:
            step_status = step.status.value if hasattr(step.status, 'value') else step.status
            step_color = "#22c55e" if step_status == "success" else "#ef4444"
            steps_html += f"""
            <tr>
                <td style="padding:8px;border-bottom:1px solid #eee;">{step.step_number}</td>
                <td style="padding:8px;border-bottom:1px solid #eee;">@{step.persona}</td>
                <td style="padding:8px;border-bottom:1px solid #eee;">{step.instruction[:80]}</td>
                <td style="padding:8px;border-bottom:1px solid #eee;color:{step_color};">{step_status}</td>
                <td style="padding:8px;border-bottom:1px solid #eee;">{step.duration_ms}ms</td>
            </tr>"""

        return f"""
        <html>
        <body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
            <h2 style="color:#FF4700;">{subject}</h2>
            <div style="background:#f8f9fa;padding:16px;border-radius:8px;margin-bottom:16px;">
                <p><strong>Status:</strong> <span style="color:{status_color};">{status}</span></p>
                <p><strong>Duration:</strong> {execution.duration_ms or 0}ms</p>
                <p><strong>Steps:</strong> {execution.successful_steps}/{execution.total_steps} successful</p>
            </div>
            <table style="width:100%;border-collapse:collapse;">
                <thead>
                    <tr style="background:#f1f5f9;">
                        <th style="padding:8px;text-align:left;">#</th>
                        <th style="padding:8px;text-align:left;">Persona</th>
                        <th style="padding:8px;text-align:left;">Instruction</th>
                        <th style="padding:8px;text-align:left;">Status</th>
                        <th style="padding:8px;text-align:left;">Duration</th>
                    </tr>
                </thead>
                <tbody>{steps_html}</tbody>
            </table>
            {f'<div style="margin-top:16px;padding:12px;background:#f0fdf4;border-radius:8px;"><strong>Final Result:</strong><br/>{execution.final_result}</div>' if execution.final_result else ''}
            <p style="color:#94a3b8;font-size:12px;margin-top:24px;">Generated by ContextuAI Automations</p>
        </body>
        </html>"""

    def _format_as_json(self, execution: AutomationExecutionResponse) -> str:
        """Format execution results as JSON."""
        data = {
            "execution_id": execution.execution_id,
            "automation_id": execution.automation_id,
            "status": execution.status.value if hasattr(execution.status, 'value') else execution.status,
            "started_at": execution.started_at,
            "completed_at": execution.completed_at,
            "duration_ms": execution.duration_ms,
            "total_steps": execution.total_steps,
            "successful_steps": execution.successful_steps,
            "failed_steps": execution.failed_steps,
            "final_result": execution.final_result,
            "steps": [
                {
                    "step_number": s.step_number,
                    "persona": s.persona,
                    "instruction": s.instruction,
                    "result": s.result,
                    "status": s.status.value if hasattr(s.status, 'value') else s.status,
                    "duration_ms": s.duration_ms
                }
                for s in execution.steps
            ]
        }
        return json.dumps(data, indent=2)

    def _format_as_csv(self, execution: AutomationExecutionResponse) -> str:
        """Format execution step results as CSV."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Step", "Persona", "Instruction", "Status", "Duration (ms)", "Result"])
        for step in execution.steps:
            writer.writerow([
                step.step_number,
                step.persona,
                step.instruction,
                step.status.value if hasattr(step.status, 'value') else step.status,
                step.duration_ms,
                step.result[:500]
            ])
        return output.getvalue()

    def _format_as_txt(self, execution: AutomationExecutionResponse) -> str:
        """Format execution results as plain text."""
        return self._build_email_body(execution)


# Singleton instance
automation_output_service = AutomationOutputService()
