from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import storage
from .authz import can_edit_manual, can_read_manual, can_view_audit_log
from .config import settings
from .rag import OpenAIKeyMissing, answer, api_error_for_openai_missing, ingest_manual, run_evaluation, search
from .schemas import AnswerRequest, AnswerResponse, Manual, ManualCreate, ManualUpdate, SearchRequest


app = FastAPI(title="Nail Knowledge RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    storage.init_db()
    # サンプルデータはAPIキーなしでも検索評価を試せるよう、初回だけデモEmbeddingで取り込む。
    # 実運用では各マニュアルの「再Embedding」でOpenAI Embeddingへ置き換える。
    if not storage.list_chunks():
        for manual in storage.list_manuals():
            ingest_manual(manual, use_demo_embeddings=True)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "openai_configured": bool(settings.openai_api_key)}


@app.get("/users")
def users() -> list[dict]:
    return [user.model_dump() for user in storage.list_users()]


@app.post("/auth/mock-login")
def mock_login(payload: dict) -> dict:
    user = storage.get_user(payload["user_id"])
    return user.model_dump()


@app.get("/manuals")
def manuals(user_id: str) -> list[dict]:
    user = storage.get_user(user_id)
    return [manual.model_dump() for manual in storage.list_manuals() if can_read_manual(user, manual)]


@app.get("/manuals/{manual_id}")
def manual_detail(manual_id: str, user_id: str) -> dict:
    user = storage.get_user(user_id)
    manual = storage.get_manual(manual_id)
    if not can_read_manual(user, manual):
        raise HTTPException(status_code=403, detail="このマニュアルを閲覧する権限がありません。")
    data = manual.model_dump()
    data["can_edit"] = can_edit_manual(user, manual)
    return data


@app.post("/manuals")
def create_manual(payload: ManualCreate, user_id: str) -> dict:
    user = storage.get_user(user_id)
    target = Manual(id="new", version=1, updated_at="", **payload.model_dump())
    if not can_edit_manual(user, target):
        raise HTTPException(status_code=403, detail="マニュアル作成権限がありません。")
    manual = storage.create_manual(payload)
    return manual.model_dump()


@app.put("/manuals/{manual_id}")
def update_manual(manual_id: str, payload: ManualUpdate, user_id: str) -> dict:
    user = storage.get_user(user_id)
    current = storage.get_manual(manual_id)
    if not can_edit_manual(user, current):
        raise HTTPException(status_code=403, detail="このマニュアルを編集する権限がありません。")
    target = Manual(id=manual_id, version=current.version, updated_at=current.updated_at, **payload.model_dump())
    if not can_edit_manual(user, target):
        raise HTTPException(status_code=403, detail="更新後の公開範囲に対する編集権限がありません。")
    manual = storage.update_manual(manual_id, ManualCreate(**payload.model_dump()))
    return manual.model_dump()


@app.post("/manuals/{manual_id}/ingest")
def ingest(manual_id: str, user_id: str) -> dict:
    user = storage.get_user(user_id)
    manual = storage.get_manual(manual_id)
    if not can_edit_manual(user, manual):
        raise HTTPException(status_code=403, detail="このマニュアルを再Embeddingする権限がありません。")
    try:
        count = ingest_manual(manual)
    except OpenAIKeyMissing as exc:
        raise api_error_for_openai_missing(exc) from exc
    return {"manual_id": manual.id, "version": manual.version, "chunks": count}


@app.post("/search")
def search_endpoint(payload: SearchRequest) -> dict:
    user = storage.get_user(payload.user_id)
    try:
        sources, filtered_out = search(user, payload.query, payload.top_k)
    except OpenAIKeyMissing as exc:
        raise api_error_for_openai_missing(exc) from exc
    return {"sources": [source.model_dump() for source in sources], "filtered_out_count": filtered_out}


@app.post("/answer", response_model=AnswerResponse)
def answer_endpoint(payload: AnswerRequest) -> AnswerResponse:
    user = storage.get_user(payload.user_id)
    try:
        text, sources, filtered_out, audit_id = answer(user, payload.query, payload.top_k)
    except OpenAIKeyMissing as exc:
        raise api_error_for_openai_missing(exc) from exc
    return AnswerResponse(answer=text, sources=sources, filtered_out_count=filtered_out, audit_log_id=audit_id)


@app.post("/evaluations/run")
def evaluation(user_id: str) -> dict:
    user = storage.get_user(user_id)
    if user.role not in {"admin", "manager"}:
        raise HTTPException(status_code=403, detail="評価実行権限がありません。")
    return {"results": [result.model_dump() for result in run_evaluation()]}


@app.get("/audit-logs")
def audit_logs(user_id: str) -> list[dict]:
    requester = storage.get_user(user_id)
    logs = storage.list_audit_logs()
    visible = []
    for log in logs:
        target = storage.get_user(log["user_id"])
        if can_view_audit_log(requester, target):
            visible.append(log)
    return visible
