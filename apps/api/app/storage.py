import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .config import settings
from .schemas import Manual, ManualCreate, User


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    path = Path(settings.database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            create table if not exists users (
                id text primary key,
                name text not null,
                role text not null,
                org_type text not null,
                branch_id text
            );
            create table if not exists manuals (
                id text primary key,
                title text not null,
                category text not null,
                body text not null,
                visibility text not null,
                status text not null,
                branch_id text,
                tags_json text not null,
                version integer not null,
                updated_at text not null
            );
            create table if not exists manual_versions (
                id text primary key,
                manual_id text not null,
                version integer not null,
                body text not null,
                created_at text not null
            );
            create table if not exists chunks (
                id text primary key,
                manual_id text not null,
                manual_version integer not null,
                chunk_index integer not null,
                text text not null,
                embedding_json text not null,
                created_at text not null
            );
            create table if not exists audit_logs (
                id text primary key,
                user_id text not null,
                query text not null,
                answer text not null,
                source_chunks_json text not null,
                filtered_out_count integer not null,
                created_at text not null
            );
            create table if not exists golden_questions (
                id text primary key,
                user_id text not null,
                query text not null,
                expected_manual_ids_json text not null
            );
            """
        )
        if not conn.execute("select 1 from users limit 1").fetchone():
            seed(conn)


def seed(conn: sqlite3.Connection) -> None:
    users = [
        ("admin_hq", "管理者 山田", "admin", "headquarters", None),
        ("manager_hq", "本社マネージャー 佐藤", "manager", "headquarters", None),
        ("manager_shibuya", "渋谷店マネージャー 鈴木", "manager", "branch", "shibuya"),
        ("nailist_shibuya", "渋谷店ネイリスト 田中", "nailist", "branch", "shibuya"),
        ("nailist_shinjuku", "新宿店ネイリスト 高橋", "nailist", "branch", "shinjuku"),
    ]
    conn.executemany("insert into users values (?, ?, ?, ?, ?)", users)

    manuals = [
        ("manual-service", "接客基本マニュアル", "接客", "company", "published", None, ["接客", "カウンセリング"], "来店時は30秒以内に笑顔で挨拶し、予約名を確認します。初回のお客様には生活習慣、爪の悩み、希望デザイン、アレルギー有無を確認します。施術後は次回来店目安とホームケアを案内します。"),
        ("manual-treatment", "ジェルネイル施術マニュアル", "施術", "company", "published", None, ["ジェル", "施術"], "プレパレーションでは甘皮処理、油分除去、サンディングを丁寧に行います。ベースジェルは薄く均一に塗布し、硬化時間はメーカー指定を守ります。浮きが起きやすいお客様には先端のエッジを必ず包みます。"),
        ("manual-hygiene", "衛生管理マニュアル", "衛生管理", "company", "published", None, ["消毒", "清掃"], "施術前後に手指消毒を行い、使用済み器具は洗浄後に消毒します。施術台、ライト、アームレストはお客様ごとに拭き上げます。出血があった場合は店長へ報告し、該当器具を隔離します。"),
        ("manual-reservation", "予約・キャンセル対応", "予約", "company", "published", None, ["予約", "キャンセル"], "予約変更は前日18時まで無料で受け付けます。10分以上の遅刻はメニュー短縮、20分以上はキャンセル扱いにする場合があります。無断キャンセルが2回続いたお客様は次回予約時に事前決済を案内します。"),
        ("manual-claim", "クレーム一次対応", "クレーム", "manager_only", "published", None, ["クレーム", "店長"], "仕上がり不満や施術後の浮きの連絡を受けた場合、まず謝意を示し、来店日、担当者、症状、写真の有無を確認します。返金判断はスタッフ単独で行わず、店長または本社へエスカレーションします。"),
        ("manual-training", "スタッフ教育マニュアル", "社内ルール", "manager_only", "published", None, ["教育", "評価"], "新人スタッフは入社後2週間で衛生管理、接客、ジェル基礎を確認します。技術チェックは店長が実施し、課題は週次面談で記録します。"),
        ("manual-kpi", "本社KPI・売上分析", "社内ルール", "headquarters", "published", None, ["KPI", "売上"], "本社では月次で客単価、再来率、指名率、キャンセル率を確認します。キャンペーン方針は全社KPIへの影響を見て決定します。支店には必要な範囲だけ共有します。"),
        ("manual-shibuya-local", "渋谷店ローカル運用", "予約", "branch", "published", "shibuya", ["渋谷店", "運用"], "渋谷店は土日祝の当日キャンセルが多いため、前日リマインドを必ず送信します。近隣イベント日は15分単位の遅刻許容を店長判断で調整できます。"),
        ("manual-shinjuku-local", "新宿店ローカル運用", "予約", "branch", "published", "shinjuku", ["新宿店", "運用"], "新宿店は平日夜の予約が集中するため、19時以降の長時間メニューは事前確認を行います。駅混雑による遅延連絡があった場合は店長へ共有します。"),
        ("manual-incident", "個人情報事故対応", "社内ルール", "admin_only", "published", None, ["個人情報", "監査"], "顧客情報の誤送信、紛失、外部共有が疑われる場合は即時に管理者へ報告します。事実確認、影響範囲、再発防止策を記録し、必要に応じて法務へ連携します。"),
    ]
    for item in manuals:
        create_manual(
            ManualCreate(
                title=item[1],
                category=item[2],
                visibility=item[3],
                status=item[4],
                branch_id=item[5],
                tags=item[6],
                body=item[7],
            ),
            manual_id=item[0],
            conn=conn,
        )

    golden = [
        ("g1", "nailist_shibuya", "ジェルが浮いたと連絡が来たらどうする？", ["manual-treatment"]),
        ("g2", "manager_shibuya", "ジェルが浮いたクレームの返金判断は？", ["manual-claim"]),
        ("g3", "manager_shibuya", "渋谷店でイベント日に遅刻連絡があったら？", ["manual-shibuya-local"]),
        ("g4", "nailist_shinjuku", "キャンセル料の例外対応は？", ["manual-reservation", "manual-shinjuku-local"]),
        ("g5", "manager_hq", "月次で確認するKPIは？", ["manual-kpi"]),
    ]
    conn.executemany(
        "insert into golden_questions values (?, ?, ?, ?)",
        [(gid, uid, q, json.dumps(expected, ensure_ascii=False)) for gid, uid, q, expected in golden],
    )


def row_to_user(row: sqlite3.Row) -> User:
    return User(**dict(row))


def row_to_manual(row: sqlite3.Row) -> Manual:
    data = dict(row)
    data["tags"] = json.loads(data.pop("tags_json"))
    return Manual(**data)


def get_user(user_id: str) -> User:
    with connect() as conn:
        row = conn.execute("select * from users where id = ?", (user_id,)).fetchone()
    if row is None:
        raise KeyError(f"unknown user: {user_id}")
    return row_to_user(row)


def list_users() -> list[User]:
    with connect() as conn:
        rows = conn.execute("select * from users order by role, id").fetchall()
    return [row_to_user(row) for row in rows]


def create_manual(data: ManualCreate, manual_id: str | None = None, conn: sqlite3.Connection | None = None) -> Manual:
    own_conn = conn is None
    conn = conn or connect()
    mid = manual_id or str(uuid.uuid4())
    updated_at = now_iso()
    conn.execute(
        "insert into manuals values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            mid,
            data.title,
            data.category,
            data.body,
            data.visibility,
            data.status,
            data.branch_id,
            json.dumps(data.tags, ensure_ascii=False),
            1,
            updated_at,
        ),
    )
    conn.execute(
        "insert into manual_versions values (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), mid, 1, data.body, updated_at),
    )
    if own_conn:
        conn.commit()
        conn.close()
    return Manual(id=mid, version=1, updated_at=updated_at, **data.model_dump())


def update_manual(manual_id: str, data: ManualCreate) -> Manual:
    with connect() as conn:
        current = get_manual(manual_id, conn)
        version = current.version + 1
        updated_at = now_iso()
        conn.execute(
            """
            update manuals
            set title = ?, category = ?, body = ?, visibility = ?, status = ?, branch_id = ?,
                tags_json = ?, version = ?, updated_at = ?
            where id = ?
            """,
            (
                data.title,
                data.category,
                data.body,
                data.visibility,
                data.status,
                data.branch_id,
                json.dumps(data.tags, ensure_ascii=False),
                version,
                updated_at,
                manual_id,
            ),
        )
        conn.execute(
            "insert into manual_versions values (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), manual_id, version, data.body, updated_at),
        )
    return Manual(id=manual_id, version=version, updated_at=updated_at, **data.model_dump())


def get_manual(manual_id: str, conn: sqlite3.Connection | None = None) -> Manual:
    own_conn = conn is None
    conn = conn or connect()
    row = conn.execute("select * from manuals where id = ?", (manual_id,)).fetchone()
    if own_conn:
        conn.close()
    if row is None:
        raise KeyError(f"unknown manual: {manual_id}")
    return row_to_manual(row)


def list_manuals() -> list[Manual]:
    with connect() as conn:
        rows = conn.execute("select * from manuals order by updated_at desc").fetchall()
    return [row_to_manual(row) for row in rows]


def replace_chunks(manual: Manual, chunks: Iterable[tuple[str, list[float]]]) -> int:
    with connect() as conn:
        conn.execute("delete from chunks where manual_id = ?", (manual.id,))
        count = 0
        for index, (text, embedding) in enumerate(chunks):
            conn.execute(
                "insert into chunks values (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    manual.id,
                    manual.version,
                    index,
                    text,
                    json.dumps(embedding),
                    now_iso(),
                ),
            )
            count += 1
    return count


def list_chunks() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            select c.*, m.title manual_title, m.category, m.visibility, m.status,
                   m.branch_id, m.tags_json, m.version current_manual_version
            from chunks c
            join manuals m on m.id = c.manual_id
            order by c.created_at desc
            """
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["embedding"] = json.loads(item.pop("embedding_json"))
        item["tags"] = json.loads(item.pop("tags_json"))
        result.append(item)
    return result


def create_audit_log(user_id: str, query: str, answer: str, sources: list[dict], filtered_out_count: int) -> str:
    audit_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            "insert into audit_logs values (?, ?, ?, ?, ?, ?, ?)",
            (
                audit_id,
                user_id,
                query,
                answer,
                json.dumps(sources, ensure_ascii=False),
                filtered_out_count,
                now_iso(),
            ),
        )
    return audit_id


def list_audit_logs() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("select * from audit_logs order by created_at desc").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["source_chunks"] = json.loads(item.pop("source_chunks_json"))
        result.append(item)
    return result


def list_golden_questions() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("select * from golden_questions order by id").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["expected_manual_ids"] = json.loads(item.pop("expected_manual_ids_json"))
        result.append(item)
    return result

