"""
TRINETRA Security Appliance - Email Alert Service
Provides high-priority security alert emails featuring the official TRINETRA branding logo,
incident snapshot attachments, and rich HTML alert layout.
"""

import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from pathlib import Path
from typing import Dict, Any, Optional, List

from app.config import settings

logger = logging.getLogger("guardbox.email_service")

# Path to logo assets
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LOGO_PATH = ASSETS_DIR / "trinetra_logo.png"
EMBLEM_PATH = ASSETS_DIR / "trinetra_emblem.png"


class EmailAlertService:
    def __init__(self):
        self.enabled = settings.EMAIL_NOTIFICATIONS_ENABLED
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_from = settings.SMTP_FROM
        self.smtp_use_tls = settings.SMTP_USE_TLS
        self.recipients = [
            e.strip() for e in settings.ALERT_RECIPIENT_EMAILS.split(",") if e.strip()
        ]

    def is_configured(self) -> bool:
        """Check if SMTP credentials and recipients are configured."""
        return bool(self.smtp_host and self.smtp_user and self.smtp_password and self.recipients)

    def send_security_alert_email(
        self,
        alert_code: str,
        camera_name: str,
        event_type: str,
        severity: str = "HIGH",
        timestamp: Optional[str] = None,
        motion_area: float = 0.0,
        snapshot_path: Optional[str] = None,
        custom_recipients: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Send a rich, branded security alert email with embedded TRINETRA logo and snapshot.
        """
        targets = custom_recipients if custom_recipients else self.recipients
        if not targets:
            logger.info("No email alert recipients configured; skipping email dispatch.")
            return {"status": "skipped", "reason": "no_recipients"}

        if not (self.smtp_host and self.smtp_user and self.smtp_password):
            logger.warning("SMTP credentials not configured in .env; skipping email alert.")
            return {"status": "skipped", "reason": "smtp_unconfigured"}

        subject = f"🚨 [{severity}] TRINETRA Security Alert: {event_type} on {camera_name} ({alert_code})"

        msg = MIMEMultipart("related")
        msg["Subject"] = subject
        msg["From"] = self.smtp_from
        msg["To"] = ", ".join(targets)

        # Build HTML content
        is_critical = severity.upper() in ("CRITICAL", "HIGH", "EMERGENCY")
        badge_bg = "#dc2626" if is_critical else "#f59e0b"
        badge_text = "EMERGENCY ALERT" if is_critical else "SECURITY WARNING"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body {{ font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif; background-color: #07111C; margin: 0; padding: 20px; color: #E1E7EC; }}
            .container {{ max-width: 600px; margin: 0 auto; background: #0D1B2A; border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.6); }}
            .header {{ background: linear-gradient(135deg, #14283A 0%, #07111C 100%); padding: 24px; text-align: center; border-bottom: 2px solid #00CA9E; }}
            .logo-img {{ max-width: 260px; height: auto; display: block; margin: 0 auto 12px auto; }}
            .brand-sub {{ color: #00CA9E; font-size: 13px; font-weight: 600; letter-spacing: 1.5px; text-transform: uppercase; }}
            .content {{ padding: 28px 24px; }}
            .badge {{ display: inline-block; background: {badge_bg}; color: #ffffff; font-weight: 800; font-size: 12px; padding: 6px 14px; border-radius: 20px; letter-spacing: 1px; margin-bottom: 16px; }}
            .alert-title {{ font-size: 22px; font-weight: 700; color: #FFFFFF; margin: 0 0 16px 0; }}
            .info-table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; }}
            .info-table td {{ padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.06); font-size: 14px; }}
            .info-label {{ color: #8C9BAE; font-weight: 500; width: 140px; }}
            .info-val {{ color: #FFFFFF; font-weight: 600; }}
            .snapshot-box {{ margin: 20px 0; text-align: center; background: #07111C; padding: 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.1); }}
            .snapshot-box img {{ max-width: 100%; height: auto; border-radius: 6px; }}
            .footer {{ background: #07111C; padding: 18px; text-align: center; font-size: 12px; color: #64748B; border-top: 1px solid rgba(255,255,255,0.05); }}
            .btn-view {{ display: inline-block; background: #00CA9E; color: #07111C; font-weight: 700; text-decoration: none; padding: 12px 28px; border-radius: 6px; margin-top: 12px; font-size: 14px; }}
          </style>
        </head>
        <body>
          <div class="container">
            <div class="header">
              <img src="cid:trinetra_logo" alt="TRINETRA Logo" class="logo-img" />
              <div class="brand-sub">Advanced Security & Surveillance</div>
            </div>
            <div class="content">
              <div><span class="badge">{badge_text}</span></div>
              <h1 class="alert-title">{event_type} Detected</h1>
              <table class="info-table">
                <tr><td class="info-label">Alert Code</td><td class="info-val" style="font-family: monospace; color: #00CA9E;">{alert_code}</td></tr>
                <tr><td class="info-label">Camera</td><td class="info-val">{camera_name}</td></tr>
                <tr><td class="info-label">Timestamp</td><td class="info-val">{timestamp or 'Realtime Detection'}</td></tr>
                <tr><td class="info-label">Severity</td><td class="info-val" style="color: {'#ef4444' if is_critical else '#f59e0b'};">{severity}</td></tr>
                <tr><td class="info-label">Motion Area</td><td class="info-val">{int(motion_area):,} px²</td></tr>
              </table>

              {"<div class='snapshot-box'><p style='color: #8C9BAE; font-size: 12px; margin-top:0;'>SECURITY EVIDENCE SNAPSHOT</p><img src='cid:alert_snapshot' alt='Security Snapshot' /></div>" if (snapshot_path and os.path.exists(snapshot_path)) else ""}

              <div style="text-align: center; margin-top: 24px;">
                <p style="color: #94A3B8; font-size: 13px; margin: 0 0 12px 0;">Please check your TRINETRA Mobile App immediately to verify camera feed or acknowledge alert.</p>
              </div>
            </div>
            <div class="footer">
              TRINETRA Security Appliance • Local & Edge AI Protection<br/>
              Generated by TRINETRA Hardware Security System
            </div>
          </div>
        </body>
        </html>
        """

        msg_alternative = MIMEMultipart("alternative")
        msg_alternative.attach(MIMEText(html_body, "html"))
        msg.attach(msg_alternative)

        # Attach Embedded Logo
        logo_file = LOGO_PATH if LOGO_PATH.exists() else EMBLEM_PATH
        if logo_file.exists():
            try:
                with open(logo_file, "rb") as f:
                    logo_img = MIMEImage(f.read())
                    logo_img.add_header("Content-ID", "<trinetra_logo>")
                    logo_img.add_header("Content-Disposition", "inline", filename=logo_file.name)
                    msg.attach(logo_img)
            except Exception as e:
                logger.error(f"Failed to attach inline logo to alert email: {e}")

        # Attach Snapshot Image if available
        if snapshot_path and os.path.exists(snapshot_path):
            try:
                with open(snapshot_path, "rb") as sf:
                    snap_img = MIMEImage(sf.read())
                    snap_img.add_header("Content-ID", "<alert_snapshot>")
                    snap_img.add_header("Content-Disposition", "inline", filename=os.path.basename(snapshot_path))
                    msg.attach(snap_img)
            except Exception as se:
                logger.error(f"Failed to attach snapshot image to email: {se}")

        # Dispatch via SMTP
        try:
            if self.smtp_use_tls:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=10)

            server.login(self.smtp_user, self.smtp_password)
            server.sendmail(self.smtp_from, targets, msg.as_string())
            server.quit()

            logger.info(f"Successfully dispatched TRINETRA alert email for {alert_code} to {targets}")
            return {"status": "sent", "recipients": targets, "alert_code": alert_code}
        except Exception as e:
            logger.error(f"SMTP failed to send security alert email: {e}")
            return {"status": "failed", "error": str(e)}


# Global Singleton
email_alert_service = EmailAlertService()
