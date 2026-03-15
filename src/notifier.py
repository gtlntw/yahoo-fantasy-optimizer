"""
Email Notification module.

Sends the optimizer results to the user via SMTP so the script
can run headlessly on a schedule.
"""

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)

def send_email(subject: str, body: str, to_address: str) -> bool:
    """
    Send an email notification using SMTP.
    Requires SMTP_USER and SMTP_PASS environment variables.
    Defaults to Gmail's SMTP server.
    """
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    
    if not smtp_user or not smtp_pass:
        logger.error("❌ SMTP_USER or SMTP_PASS environment variables are not set. Cannot send email.")
        return False
        
    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_address
    
    try:
        logger.info(f"📧 Sending email notification to {to_address} via {smtp_server}...")
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
            
        logger.info("✅ Email sent successfully!")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to send email: {e}")
        return False
