from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PrinterRecord:
    """Represents a discovered printer and its capabilities."""
    ip_address: str = ""
    hostname: str = ""
    name: str = ""
    protocols: list[str] = field(default_factory=list)
    supported_formats: list[str] = field(default_factory=list)
    resolutions: list[str] = field(default_factory=list)
    color_supported: bool | str = "unknown"
    duplex_supported: bool | str = "unknown"
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ip_address": self.ip_address,
            "hostname": self.hostname,
            "name": self.name,
            "protocols": self.protocols,
            "supported_formats": self.supported_formats,
            "resolutions": self.resolutions,
            "color_supported": self.color_supported,
            "duplex_supported": self.duplex_supported,
            "raw_metadata": self.raw_metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PrinterRecord:
        return cls(
            ip_address=data.get("ip_address", ""),
            hostname=data.get("hostname", ""),
            name=data.get("name", ""),
            protocols=data.get("protocols", []),
            supported_formats=data.get("supported_formats", []),
            resolutions=data.get("resolutions", []),
            color_supported=data.get("color_supported", "unknown"),
            duplex_supported=data.get("duplex_supported", "unknown"),
            raw_metadata=data.get("raw_metadata", {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, json_str: str) -> PrinterRecord:
        return cls.from_dict(json.loads(json_str))
