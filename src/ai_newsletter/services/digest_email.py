import asyncio
import logging

import markdown
import resend

from src.ai_newsletter.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

resend.api_key = settings.resend_api_key


async def send_digest_email(to_email: str, topic: str, content: str, digest_id: str):
    html_content = markdown.markdown(content)
    try:
        params = {
            "from": "Dropread <digest@dropread.site>",
            "to": [to_email],
            "subject": f"Your digest: {topic}",
            "html": f"""
                <html><body style="font-family:sans-serif;max-width:680px;margin:auto;padding:24px;color:#1a1a1a;">
                    <h1 style="font-size:24px;margin-bottom:24px;">{topic}</h1>
                    {html_content}
                    <hr style="margin-top:40px;border:none;border-top:1px solid #e2e8f0;">
                </body></html>
            """,
        }
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: resend.Emails.send(params)
        )
        logger.info(f"Email sent to {to_email} for digest {digest_id}")
    except Exception as e:
        logger.error(f"Failed to send email for {digest_id}: {e}")
