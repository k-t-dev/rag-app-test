"use client";

import { BookOpen, ClipboardList, FileText, Gauge, LockKeyhole, RefreshCw, Save, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

type User = {
  id: string;
  name: string;
  role: "admin" | "manager" | "nailist";
  org_type: "headquarters" | "branch";
  branch_id: string | null;
};

type Manual = {
  id: string;
  title: string;
  category: string;
  body: string;
  visibility: "company" | "headquarters" | "branch" | "manager_only" | "admin_only";
  status: "draft" | "published" | "archived";
  branch_id: string | null;
  tags: string[];
  version: number;
  updated_at: string;
  can_edit?: boolean;
};

type Source = {
  chunk_id: string;
  manual_id: string;
  manual_title: string;
  manual_version: number;
  text: string;
  vector_score: number;
  keyword_score: number;
  hybrid_score: number;
  rerank_score: number;
};

type EvaluationResult = {
  user_id: string;
  query: string;
  expected_manual_ids: string[];
  retrieved_manual_ids: string[];
  recall: number;
  precision: number;
  top_k_hit: boolean;
  leaked_manual_ids: string[];
};

const emptyManual: Manual = {
  id: "",
  title: "",
  category: "接客",
  body: "",
  visibility: "company",
  status: "published",
  branch_id: null,
  tags: [],
  version: 1,
  updated_at: "",
};

export default function Page() {
  const [users, setUsers] = useState<User[]>([]);
  const [userId, setUserId] = useState("admin_hq");
  const [tab, setTab] = useState<"search" | "manuals" | "evaluation" | "audit">("search");
  const [manuals, setManuals] = useState<Manual[]>([]);
  const [selected, setSelected] = useState<Manual>(emptyManual);
  const [query, setQuery] = useState("ジェルが浮いたと連絡が来たらどうする？");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [evaluations, setEvaluations] = useState<EvaluationResult[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const currentUser = useMemo(() => users.find((user) => user.id === userId), [users, userId]);

  async function loadBase(nextUserId = userId) {
    setError("");
    const [loadedUsers, loadedManuals] = await Promise.all([
      api<User[]>("/users"),
      api<Manual[]>(`/manuals?user_id=${nextUserId}`),
    ]);
    setUsers(loadedUsers);
    setManuals(loadedManuals);
    if (loadedManuals.length > 0) setSelected(loadedManuals[0]);
  }

  useEffect(() => {
    loadBase().catch((err) => setError(err.message));
  }, []);

  async function runAnswer() {
    setLoading(true);
    setError("");
    try {
      const result = await api<{ answer: string; sources: Source[]; filtered_out_count: number; audit_log_id: string }>("/answer", {
        method: "POST",
        body: JSON.stringify({ user_id: userId, query, top_k: 5 }),
      });
      setAnswer(`${result.answer}\n\n権限フィルタで除外されたチャンク数: ${result.filtered_out_count}`);
      setSources(result.sources);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function saveManual() {
    setLoading(true);
    setError("");
    try {
      const payload = {
        title: selected.title,
        category: selected.category,
        body: selected.body,
        visibility: selected.visibility,
        status: selected.status,
        branch_id: selected.visibility === "branch" ? selected.branch_id : null,
        tags: selected.tags,
      };
      const saved = selected.id
        ? await api<Manual>(`/manuals/${selected.id}?user_id=${userId}`, { method: "PUT", body: JSON.stringify(payload) })
        : await api<Manual>(`/manuals?user_id=${userId}`, { method: "POST", body: JSON.stringify(payload) });
      setSelected(saved);
      await loadBase(userId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function ingestManual() {
    setLoading(true);
    setError("");
    try {
      await api(`/manuals/${selected.id}/ingest?user_id=${userId}`, { method: "POST" });
      await loadBase(userId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function runEvaluation() {
    setLoading(true);
    setError("");
    try {
      const result = await api<{ results: EvaluationResult[] }>(`/evaluations/run?user_id=${userId}`, { method: "POST" });
      setEvaluations(result.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function loadAudit() {
    setLoading(true);
    setError("");
    try {
      setAuditLogs(await api<any[]>(`/audit-logs?user_id=${userId}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  function changeUser(nextUserId: string) {
    setUserId(nextUserId);
    loadBase(nextUserId).catch((err) => setError(err.message));
  }

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">Nail Knowledge RAG</div>
        <div className="row">
          <label>ログイン切替</label>
          <select value={userId} onChange={(event) => changeUser(event.target.value)}>
            {users.map((user) => (
              <option key={user.id} value={user.id}>
                {user.name}
              </option>
            ))}
          </select>
          <div className="muted">
            {currentUser?.role} / {currentUser?.org_type}
            {currentUser?.branch_id ? ` / ${currentUser.branch_id}` : ""}
          </div>
        </div>
        <nav className="nav">
          <button className={tab === "search" ? "active" : ""} onClick={() => setTab("search")}>
            <Search size={16} /> 検索・回答
          </button>
          <button className={tab === "manuals" ? "active" : ""} onClick={() => setTab("manuals")}>
            <FileText size={16} /> マニュアル管理
          </button>
          <button className={tab === "evaluation" ? "active" : ""} onClick={() => setTab("evaluation")}>
            <Gauge size={16} /> 評価
          </button>
          <button className={tab === "audit" ? "active" : ""} onClick={() => { setTab("audit"); loadAudit(); }}>
            <ClipboardList size={16} /> 監査ログ
          </button>
        </nav>
      </aside>

      <main className="main">
        <div className="topbar">
          <div>
            <h1>RBAC / ABAC 社内マニュアル検索</h1>
            <div className="muted">権限フィルタ済みのチャンクだけをRerankとLLMに渡します。</div>
          </div>
          <span className="pill"><LockKeyhole size={14} /> OpenAI APIキーはAPI側で手動設定</span>
        </div>

        {error && <div className="panel error">{error}</div>}

        {tab === "search" && (
          <div className="grid">
            <section className="panel">
              <h2>質問</h2>
              <div className="row">
                <label>社内マニュアルへの質問</label>
                <textarea value={query} onChange={(event) => setQuery(event.target.value)} />
              </div>
              <button className="primary" disabled={loading} onClick={runAnswer}>
                <Search size={16} /> 回答生成
              </button>
            </section>
            <section className="panel">
              <h2>回答</h2>
              <div className="answer">{answer || "まだ回答はありません。"}</div>
              {sources.map((source) => (
                <div className="source" key={source.chunk_id}>
                  <strong>{source.manual_title}</strong> <span className="pill">v{source.manual_version}</span>
                  <p>{source.text}</p>
                  <div className="muted">
                    vector {source.vector_score} / keyword {source.keyword_score} / hybrid {source.hybrid_score} / rerank {source.rerank_score}
                  </div>
                </div>
              ))}
            </section>
          </div>
        )}

        {tab === "manuals" && (
          <div className="grid">
            <section className="panel">
              <div className="actions" style={{ justifyContent: "space-between" }}>
                <h2>マニュアル一覧</h2>
                <button onClick={() => setSelected(emptyManual)}>
                  <BookOpen size={16} /> 新規
                </button>
              </div>
              <table className="table">
                <thead>
                  <tr><th>タイトル</th><th>範囲</th><th>版</th></tr>
                </thead>
                <tbody>
                  {manuals.map((manual) => (
                    <tr key={manual.id} onClick={() => setSelected(manual)}>
                      <td>{manual.title}<br /><span className="muted">{manual.category}</span></td>
                      <td>{manual.visibility}<br /><span className="muted">{manual.branch_id ?? "全体"}</span></td>
                      <td>v{manual.version}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
            <section className="panel">
              <h2>編集</h2>
              <div className="row"><label>タイトル</label><input value={selected.title} onChange={(e) => setSelected({ ...selected, title: e.target.value })} /></div>
              <div className="row"><label>カテゴリ</label><select value={selected.category} onChange={(e) => setSelected({ ...selected, category: e.target.value })}>
                {["接客", "施術", "衛生管理", "予約", "クレーム", "社内ルール"].map((item) => <option key={item}>{item}</option>)}
              </select></div>
              <div className="row"><label>公開範囲</label><select value={selected.visibility} onChange={(e) => setSelected({ ...selected, visibility: e.target.value as Manual["visibility"] })}>
                <option value="company">全社公開</option>
                <option value="headquarters">本社限定</option>
                <option value="branch">支店限定</option>
                <option value="manager_only">マネージャー限定</option>
                <option value="admin_only">管理者限定</option>
              </select></div>
              <div className="row"><label>支店</label><select value={selected.branch_id ?? ""} onChange={(e) => setSelected({ ...selected, branch_id: e.target.value || null })}>
                <option value="">なし</option><option value="shibuya">渋谷店</option><option value="shinjuku">新宿店</option>
              </select></div>
              <div className="row"><label>状態</label><select value={selected.status} onChange={(e) => setSelected({ ...selected, status: e.target.value as Manual["status"] })}>
                <option value="published">公開</option><option value="draft">下書き</option><option value="archived">アーカイブ</option>
              </select></div>
              <div className="row"><label>本文</label><textarea value={selected.body} onChange={(e) => setSelected({ ...selected, body: e.target.value })} /></div>
              <div className="actions">
                <button className="primary" disabled={loading} onClick={saveManual}><Save size={16} /> 保存</button>
                <button disabled={loading || !selected.id} onClick={ingestManual}><RefreshCw size={16} /> 再Embedding</button>
              </div>
            </section>
          </div>
        )}

        {tab === "evaluation" && (
          <section className="panel">
            <div className="actions" style={{ justifyContent: "space-between" }}>
              <h2>検索品質評価</h2>
              <button className="primary" disabled={loading} onClick={runEvaluation}>評価実行</button>
            </div>
            <p className="muted">Recallは検索漏れ、Precisionはノイズの少なさ、漏洩件数は権限外文書の混入を表します。</p>
            <table className="table">
              <thead><tr><th>ユーザー</th><th>質問</th><th>Recall</th><th>Precision</th><th>Hit</th><th>漏洩</th></tr></thead>
              <tbody>
                {evaluations.map((row) => (
                  <tr key={`${row.user_id}-${row.query}`}>
                    <td>{row.user_id}</td><td>{row.query}</td><td>{row.recall}</td><td>{row.precision}</td><td>{row.top_k_hit ? "Yes" : "No"}</td><td>{row.leaked_manual_ids.length}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        {tab === "audit" && (
          <section className="panel">
            <h2>監査ログ</h2>
            <table className="table">
              <thead><tr><th>時刻</th><th>ユーザー</th><th>質問</th><th>参照</th></tr></thead>
              <tbody>
                {auditLogs.map((log) => (
                  <tr key={log.id}>
                    <td>{log.created_at}</td><td>{log.user_id}</td><td>{log.query}</td><td>{log.source_chunks?.map((s: Source) => s.manual_title).join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}
      </main>
    </div>
  );
}

