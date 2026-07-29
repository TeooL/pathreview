"""PII detection and scrubbing."""

import re
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from safety.monitoring import SafetyMonitor

logger = structlog.get_logger()


class PIIScrubber:
    """Detect and redact personally identifiable information."""

    # Regex patterns for common PII
    PII_PATTERNS = {
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "phone_us": r"\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]?([0-9]{3})[-.]?([0-9]{4})\b",
        "phone_intl": r"\+[0-9]{1,3}[-.]?[0-9]{1,14}",
        "ssn": r"\b(?!000|666)[0-9]{3}-(?!00)[0-9]{2}-(?!0000)[0-9]{4}\b",
        "street_address": r"\b\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Circle|Cir|Park|Pl|Plaza|Place|Drive|Dr|Way|Parkway|Pkwy|Point|Pt|Pike|Run|Summit|Summit|Terrace|Ter|Trail|Trl|Tunnel|Turnpike|View|Vista|Vlg|Village|Vly|Valley)",
    }

    def scrub(self, text: str) -> str:
        """Scrub PII from text.

        Args:
            text: Text to scrub

        Returns:
            Text with PII replaced by [REDACTED]
        """
        scrubbed = text

        for pii_type, pattern in self.PII_PATTERNS.items():
            scrubbed = re.sub(pattern, "[REDACTED]", scrubbed, flags=re.IGNORECASE)

        return scrubbed

    def detect(self, text: str, monitor: "SafetyMonitor | None" = None) -> list[dict]:
        """Detect PII in text.

        Args:
            text: Text to analyze
            monitor: Optional SafetyMonitor to record a pii_detected event

        Returns:
            List of detected PII with type, value, and position
        """
        detected = []

        for pii_type, pattern in self.PII_PATTERNS.items():
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                detected.append({
                    "type": pii_type,
                    "value": match.group(),
                    "start": match.start(),
                    "end": match.end()
                })

        logger.info("pii_detected", count=len(detected), types=len(set(d["type"] for d in detected)))

        if detected and monitor is not None:
            monitor.log_event("pii_detected", {"count": len(detected)})

        return detected
