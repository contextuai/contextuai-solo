"""
Email integration tools for Strands Agent.
Provides SMTP send and IMAP read capabilities.
"""

import logging
import time
from typing import Dict, Any, Optional, List
from strands.tools import tool

logger = logging.getLogger(__name__)


class EmailTools:
    """
    Email operation tools for sending and reading email.

    Features:
    - Send emails via SMTP
    - Search inbox via IMAP
    - Read individual emails
    - List mail folders
    """

    def __init__(self, persona_id: str, credentials: Dict[str, Any]):
        """
        Initialize Email tools with persona credentials.

        Args:
            persona_id: Unique persona identifier
            credentials: Email connection credentials:
                - smtp_host: SMTP server hostname
                - smtp_port: SMTP port (default 587)
                - imap_host: IMAP server hostname
                - email: Email address
                - password: App password or account password
                - use_tls: Whether to use TLS (default True)
        """
        self.persona_id = persona_id
        self.credentials = credentials
        self.smtp_host = credentials.get("smtp_host", "")
        self.smtp_port = int(credentials.get("smtp_port", 587))
        self.imap_host = credentials.get("imap_host", "")
        self.email_address = credentials.get("email", "")
        self.password = credentials.get("password", "")
        self.use_tls = credentials.get("use_tls", True)

        # Auto-detect SMTP if only IMAP provided
        if not self.smtp_host and self.imap_host:
            self.smtp_host = self.imap_host.replace("imap.", "smtp.")

        logger.info(f"EmailTools initialized for persona {persona_id}, email: {self.email_address}")

    def get_tools(self):
        """Return all Email operation tools as a list for Strands Agent."""
        return [
            self.send_email,
            self.search_inbox,
            self.read_email,
            self.list_folders,
            self.test_connection,
        ]

    @tool
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test email connection by verifying IMAP login.

        Returns:
            Dictionary with connection status:
            {
                "success": bool,
                "response_time_ms": float,
                "imap_host": str,
                "email": str,
                "error": Optional[str]
            }
        """
        try:
            import imaplib

            start_time = time.time()

            if self.use_tls:
                imap = imaplib.IMAP4_SSL(self.imap_host)
            else:
                imap = imaplib.IMAP4(self.imap_host)

            imap.login(self.email_address, self.password)
            response_time = round((time.time() - start_time) * 1000)
            imap.logout()

            return {
                "success": True,
                "response_time_ms": response_time,
                "imap_host": self.imap_host,
                "email": self.email_address,
            }

        except Exception as e:
            logger.error(f"Email connection test failed: {e}", exc_info=True)
            return {"success": False, "error": f"Connection failed: {str(e)}"}

    @tool
    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        html: bool = False
    ) -> Dict[str, Any]:
        """
        Send an email via SMTP.

        Args:
            to: Recipient email address (comma-separated for multiple)
            subject: Email subject line
            body: Email body text
            cc: Optional CC recipients (comma-separated)
            html: Whether the body is HTML (default: plain text)

        Returns:
            Dictionary with send result:
            {
                "success": bool,
                "to": str,
                "subject": str,
                "error": Optional[str]
            }
        """
        if not self.smtp_host:
            return {"success": False, "error": "SMTP host not configured"}

        try:
            import aiosmtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart()
            msg["From"] = self.email_address
            msg["To"] = to
            msg["Subject"] = subject
            if cc:
                msg["Cc"] = cc

            content_type = "html" if html else "plain"
            msg.attach(MIMEText(body, content_type))

            recipients = [addr.strip() for addr in to.split(",")]
            if cc:
                recipients.extend([addr.strip() for addr in cc.split(",")])

            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.email_address,
                password=self.password,
                use_tls=self.use_tls if self.smtp_port == 465 else False,
                start_tls=self.use_tls if self.smtp_port != 465 else False,
            )

            return {"success": True, "to": to, "subject": subject}

        except Exception as e:
            logger.error(f"Error sending email: {e}", exc_info=True)
            return {"success": False, "error": str(e), "to": to, "subject": subject}

    @tool
    async def search_inbox(
        self,
        query: Optional[str] = None,
        folder: str = "INBOX",
        limit: int = 20,
        unread_only: bool = False
    ) -> Dict[str, Any]:
        """
        Search email inbox via IMAP.

        Args:
            query: Search query (e.g., subject text or sender). If not provided, lists recent emails.
            folder: Mail folder to search (default: "INBOX")
            limit: Maximum emails to return (default: 20, max: 50)
            unread_only: Only return unread messages (default: False)

        Returns:
            Dictionary with search results:
            {
                "success": bool,
                "emails": List of { uid, subject, from, date, is_read },
                "count": int,
                "folder": str,
                "error": Optional[str]
            }
        """
        limit = min(limit, 50)
        try:
            import imaplib
            import email as email_lib
            from email.header import decode_header

            if self.use_tls:
                imap = imaplib.IMAP4_SSL(self.imap_host)
            else:
                imap = imaplib.IMAP4(self.imap_host)

            imap.login(self.email_address, self.password)
            imap.select(folder, readonly=True)

            # Build search criteria
            criteria = []
            if unread_only:
                criteria.append("UNSEEN")
            if query:
                criteria.append(f'(OR SUBJECT "{query}" FROM "{query}")')

            search_str = " ".join(criteria) if criteria else "ALL"
            status, msg_ids = imap.search(None, search_str)

            if status != "OK":
                imap.logout()
                return {"success": False, "error": "Search failed", "emails": [], "count": 0}

            ids = msg_ids[0].split()
            # Get most recent emails
            ids = ids[-limit:] if len(ids) > limit else ids
            ids.reverse()  # Most recent first

            emails_list = []
            for uid in ids:
                status, msg_data = imap.fetch(uid, "(RFC822.HEADER FLAGS)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue

                raw_header = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
                msg = email_lib.message_from_bytes(raw_header)

                # Decode subject
                subject_parts = decode_header(msg.get("Subject", ""))
                subject = ""
                for part, encoding in subject_parts:
                    if isinstance(part, bytes):
                        subject += part.decode(encoding or "utf-8", errors="replace")
                    else:
                        subject += str(part)

                # Check flags for read status
                flags_str = ""
                for item in msg_data:
                    if isinstance(item, bytes) and b"FLAGS" in item:
                        flags_str = item.decode()
                        break

                emails_list.append({
                    "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
                    "subject": subject[:200],
                    "from": msg.get("From", "")[:100],
                    "date": msg.get("Date", ""),
                    "is_read": "\\Seen" in flags_str,
                })

            imap.logout()

            return {
                "success": True,
                "emails": emails_list,
                "count": len(emails_list),
                "folder": folder,
            }

        except Exception as e:
            logger.error(f"Error searching inbox: {e}", exc_info=True)
            return {"success": False, "error": str(e), "emails": [], "count": 0, "folder": folder}

    @tool
    async def read_email(
        self,
        uid: str,
        folder: str = "INBOX"
    ) -> Dict[str, Any]:
        """
        Read a specific email by UID.

        Args:
            uid: Email UID (from search_inbox results)
            folder: Mail folder (default: "INBOX")

        Returns:
            Dictionary with email content:
            {
                "success": bool,
                "subject": str,
                "from": str,
                "to": str,
                "date": str,
                "body": str (plain text content, truncated to 10000 chars),
                "error": Optional[str]
            }
        """
        try:
            import imaplib
            import email as email_lib
            from email.header import decode_header

            if self.use_tls:
                imap = imaplib.IMAP4_SSL(self.imap_host)
            else:
                imap = imaplib.IMAP4(self.imap_host)

            imap.login(self.email_address, self.password)
            imap.select(folder, readonly=True)

            status, msg_data = imap.fetch(uid.encode() if isinstance(uid, str) else uid, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                imap.logout()
                return {"success": False, "error": f"Email UID {uid} not found"}

            raw_msg = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw_msg)

            # Decode subject
            subject_parts = decode_header(msg.get("Subject", ""))
            subject = ""
            for part, encoding in subject_parts:
                if isinstance(part, bytes):
                    subject += part.decode(encoding or "utf-8", errors="replace")
                else:
                    subject += str(part)

            # Extract body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    if ct == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body = payload.decode(charset, errors="replace")
                            break
                # Fallback to HTML if no plain text
                if not body:
                    for part in msg.walk():
                        if part.get_content_type() == "text/html":
                            payload = part.get_payload(decode=True)
                            if payload:
                                charset = part.get_content_charset() or "utf-8"
                                body = payload.decode(charset, errors="replace")
                                break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")

            imap.logout()

            return {
                "success": True,
                "subject": subject,
                "from": msg.get("From", ""),
                "to": msg.get("To", ""),
                "date": msg.get("Date", ""),
                "body": body[:10000],
            }

        except Exception as e:
            logger.error(f"Error reading email: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    @tool
    async def list_folders(self) -> Dict[str, Any]:
        """
        List available mail folders/labels.

        Returns:
            Dictionary with folder list:
            {
                "success": bool,
                "folders": List[str],
                "count": int,
                "error": Optional[str]
            }
        """
        try:
            import imaplib

            if self.use_tls:
                imap = imaplib.IMAP4_SSL(self.imap_host)
            else:
                imap = imaplib.IMAP4(self.imap_host)

            imap.login(self.email_address, self.password)
            status, folder_list = imap.list()
            imap.logout()

            if status != "OK":
                return {"success": False, "error": "Failed to list folders", "folders": [], "count": 0}

            folders = []
            for item in folder_list:
                if isinstance(item, bytes):
                    # Parse IMAP folder response: (\\flags) "/" "folder_name"
                    decoded = item.decode("utf-8", errors="replace")
                    parts = decoded.rsplit('" ', 1)
                    if len(parts) == 2:
                        folder_name = parts[1].strip().strip('"')
                        folders.append(folder_name)

            return {"success": True, "folders": folders, "count": len(folders)}

        except Exception as e:
            logger.error(f"Error listing folders: {e}", exc_info=True)
            return {"success": False, "error": str(e), "folders": [], "count": 0}
