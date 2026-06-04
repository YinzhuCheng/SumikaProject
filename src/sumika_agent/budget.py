from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .settings import Settings
from .storage import Store

GIB = 1024**3


@dataclass
class BudgetState:
    interface: str
    tx_bytes: int
    baseline_bytes: int
    month_used_bytes: int
    soft_limit_bytes: int
    hard_limit_bytes: int
    level: str

    @property
    def month_used_gib(self) -> float:
        return self.month_used_bytes / GIB

    @property
    def soft_limit_gib(self) -> float:
        return self.soft_limit_bytes / GIB

    @property
    def hard_limit_gib(self) -> float:
        return self.hard_limit_bytes / GIB


class BudgetManager:
    def __init__(self, settings: Settings, store: Store):
        self.settings = settings
        self.store = store

    def _month_key(self) -> str:
        return datetime.now(self.settings.zoneinfo).strftime("%Y-%m")

    def _detect_interface(self) -> str:
        configured = self.settings.egress_interface
        if configured != "auto":
            return configured
        candidates = []
        for route in Path("/proc/net/route").read_text(encoding="utf-8").splitlines()[1:]:
            parts = route.split()
            if len(parts) >= 2 and parts[1] == "00000000":
                candidates.append(parts[0])
        return candidates[0] if candidates else "eth0"

    def _read_tx_bytes(self, interface: str) -> int:
        path = Path("/sys/class/net") / interface / "statistics" / "tx_bytes"
        if path.exists():
            return int(path.read_text(encoding="utf-8").strip())
        return 0

    def state(self) -> BudgetState:
        interface = self._detect_interface()
        tx_bytes = self._read_tx_bytes(interface)
        key = f"egress_baseline:{self._month_key()}:{interface}"
        baseline = self.store.get_json(key)
        if baseline is None or tx_bytes < int(baseline):
            baseline = tx_bytes
            self.store.set_json(key, baseline)
        used = max(0, tx_bytes - int(baseline))
        soft = int(self.settings.egress_monthly_soft_gib * GIB)
        hard = int(self.settings.egress_monthly_hard_gib * GIB)
        ratio = used / hard if hard else 0
        if used >= hard:
            level = "hard_stop"
        elif used >= soft:
            level = "soft_stop"
        elif ratio >= 0.7:
            level = "conserve"
        else:
            level = "normal"
        return BudgetState(interface, tx_bytes, int(baseline), used, soft, hard, level)

    def allow_text(self) -> bool:
        return self.state().level != "hard_stop"

    def allow_search(self) -> bool:
        return self.state().level in {"normal"}

    def allow_media(self) -> bool:
        return self.state().level in {"normal", "conserve"}

    def allow_proactive(self) -> bool:
        return self.state().level in {"normal", "conserve"}

    def note_estimated_egress(self, name: str, bytes_count: int) -> None:
        bucket = datetime.now(self.settings.zoneinfo).strftime("%Y-%m-%d")
        self.store.increment_counter(bucket, f"egress_estimate:{name}", max(0, bytes_count))
