"""Mobile push notification service using zero-setup ntfy protocol."""

import logging
from typing import Any
import requests

from config.settings import settings
from tools.registry import register_tool

logger = logging.getLogger("SARATHI.MobileNotify")


@register_tool(
    name="send_mobile_notification",
    description="Sends an instantaneous push notification alert to the user's mobile device phone via ntfy."
)
def send_mobile_notification(
    message: str,
    title: str = "SARATHI AI Alert",
    priority: str = "default",
    topic: str | None = None
) -> dict[str, Any]:
    """
    Sends an instantaneous push notification to the user's mobile device via ntfy.sh.
    Zero registration or API keys required.
    User simply opens or subscribes to the topic URL on mobile.
    """
    target_topic = topic or getattr(settings, "MOBILE_NOTIFY_TOPIC", "sarathi_parth_alerts")
    url = f"https://ntfy.sh/{target_topic}"

    try:
        response = requests.post(
            url,
            data=message.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": priority,
                "Tags": "robot,loudspeaker"
            },
            timeout=10
        )
        if response.status_code == 200:
            logger.info(f"Mobile notification sent to {target_topic}: '{message[:40]}...'")
            return {
                "status": "success",
                "topic": target_topic,
                "url": f"https://ntfy.sh/{target_topic}",
                "message": message
            }
        return {"status": "error", "code": response.status_code, "text": response.text}
    except Exception as e:
        logger.error(f"Failed to send mobile notification: {e}")
        return {"status": "error", "error": str(e)}
