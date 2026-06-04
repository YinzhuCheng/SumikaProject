from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .budget import BudgetManager
from .multimodal import MultimodalProcessor
from .onebot import OneBotHub
from .openrouter import OpenRouterClient
from .persona import Persona
from .proactive import ProactiveScheduler
from .search import SearchTool
from .settings import get_settings
from .storage import Store

settings = get_settings()
store = Store(settings.data_dir / "sumika.sqlite3")
persona = Persona.load(settings.persona_config)
for seed in persona.world_memory_seed:
    if seed not in [row["content"] for row in store.world_memories(limit=100)]:
        store.add_world_memory(seed, "seed")

budget = BudgetManager(settings, store)
openrouter = OpenRouterClient(settings, store)
search_tool = SearchTool(settings, store, budget)
multimodal = MultimodalProcessor(settings, budget)
hub = OneBotHub(settings, store, persona, budget, openrouter, search_tool, multimodal)
scheduler = ProactiveScheduler(settings, store, persona, hub)

app = FastAPI(title="Sumika Agent", version="0.1.0")
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.on_event("startup")
async def startup() -> None:
    scheduler.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    await scheduler.stop()


def require_admin(authorization: str | None = Header(default=None)) -> None:
    expected = f"Bearer {settings.admin_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="admin token required")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "name": persona.name, "onebot_clients": len(hub._clients)}


@app.get("/api/status")
async def status(_: None = Depends(require_admin)) -> dict[str, Any]:
    state = budget.state()
    try:
        or_status = await openrouter.key_status()
    except Exception as exc:
        or_status = {"ok": False, "error": str(exc)}
    return {
        "persona": {"name": persona.name, "nickname": persona.nickname},
        "openrouter": or_status,
        "budget": {
            "interface": state.interface,
            "level": state.level,
            "month_used_gib": round(state.month_used_gib, 4),
            "soft_limit_gib": state.soft_limit_gib,
            "hard_limit_gib": state.hard_limit_gib,
        },
        "onebot_clients": len(hub._clients),
        "settings": {
            "proactive_enabled": settings.proactive_enabled,
            "search_enabled": settings.search_enabled,
            "ocr_enabled": settings.ocr_enabled,
            "asr_enabled": settings.asr_enabled,
        },
    }


@app.post("/api/onebot/action")
async def onebot_action(payload: dict[str, Any], _: None = Depends(require_admin)) -> dict[str, Any]:
    action = str(payload.get("action") or "").strip()
    params = payload.get("params") or {}
    timeout = float(payload.get("timeout") or 30.0)
    if not action:
        raise HTTPException(status_code=400, detail="action required")
    if not isinstance(params, dict):
        raise HTTPException(status_code=400, detail="params must be an object")
    try:
        return await hub.call_action(action, params, timeout=timeout)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="OneBot action timed out") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.websocket("/onebot/ws")
async def onebot_ws(websocket: WebSocket) -> None:
    auth = websocket.headers.get("authorization") or ""
    header_token = auth.removeprefix("Bearer ").strip() if auth.lower().startswith("bearer ") else auth
    token = websocket.query_params.get("access_token") or header_token
    if settings.onebot_access_token and token != settings.onebot_access_token:
        await websocket.close(code=1008)
        return
    await hub.connect(websocket)


@app.get("/api/memory/world")
async def world_memory(_: None = Depends(require_admin)) -> list[dict[str, Any]]:
    return store.world_memories(limit=100)


@app.post("/api/memory/world")
async def add_world_memory(payload: dict[str, Any], _: None = Depends(require_admin)) -> dict[str, Any]:
    content = str(payload.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content required")
    store.add_world_memory(content, "admin")
    return {"ok": True}


@app.get("/api/memory/users")
async def user_memories(_: None = Depends(require_admin)) -> list[dict[str, Any]]:
    return store.list_user_memories(limit=200)


@app.get("/api/approvals")
async def approvals(_: None = Depends(require_admin)) -> list[dict[str, Any]]:
    return store.list_approvals()


@app.post("/api/approvals/{approval_id}/{decision}")
async def decide_approval(
    approval_id: int, decision: str, _: None = Depends(require_admin)
) -> dict[str, Any]:
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="decision must be approve or reject")
    row = store.set_approval_status(approval_id, decision)
    if not row:
        raise HTTPException(status_code=404, detail="approval not found")
    approve = decision == "approve"
    if row["request_type"] == "friend":
        await hub.send_action(
            "set_friend_add_request",
            {"flag": row["flag"], "approve": approve, "remark": persona.nickname if approve else ""},
        )
    elif row["request_type"] == "group":
        await hub.send_action(
            "set_group_add_request",
            {"flag": row["flag"], "sub_type": "invite", "approve": approve, "reason": ""},
        )
    return {"ok": True, "approval": row}


@app.get("/api/whitelist")
async def whitelist(_: None = Depends(require_admin)) -> list[dict[str, Any]]:
    return store.list_whitelist()


@app.post("/api/whitelist")
async def set_whitelist(payload: dict[str, Any], _: None = Depends(require_admin)) -> dict[str, Any]:
    target_type = str(payload.get("target_type") or "")
    target_id = str(payload.get("target_id") or "")
    enabled = bool(payload.get("enabled", True))
    if target_type not in {"private", "group"} or not target_id:
        raise HTTPException(status_code=400, detail="target_type private/group and target_id required")
    store.set_whitelist(target_type, target_id, enabled, str(payload.get("label") or ""))
    return {"ok": True}
