import json
import sqlite3
import uuid
from typing import Any, Dict, List, Optional, Tuple

import anyio


DEFAULT_PROJECT_ID = "default"


class MemoryStore:
    def __init__(self, db_path: str = "infinitebook.sqlite"):
        self.db_path = db_path

    # -------------------------
    # Connection helper
    # -------------------------
    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        # WAL: better concurrency for many short reads/writes
        con.execute("PRAGMA journal_mode=WAL;")
        # FK enforcement is per-connection in SQLite
        con.execute("PRAGMA foreign_keys=ON;")
        return con

    # -------------------------
    # Schema
    # -------------------------
    def init_db(self) -> None:
        with self._connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    language TEXT NOT NULL DEFAULT 'en',
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                )
            """)

            # --- migration: add language column to existing DBs
            cols = {r[1] for r in con.execute("PRAGMA table_info(projects)").fetchall()}
            if "language" not in cols:
                con.execute("ALTER TABLE projects ADD COLUMN language TEXT NOT NULL DEFAULT 'en'")

            # Composite PK ensures uniqueness per-project
            con.execute("""
                CREATE TABLE IF NOT EXISTS kv (
                    project_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    json TEXT NOT NULL,
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                    PRIMARY KEY (project_id, key),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS kv_project_idx ON kv(project_id);")

            con.execute("""
                CREATE TABLE IF NOT EXISTS characters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    kind TEXT NOT NULL,           -- protagonist | antagonist | supporting
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    bio TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS characters_project_idx ON characters(project_id);")

            # Ensure a default project exists (keeps existing endpoints working)
            con.execute(
                "INSERT OR IGNORE INTO projects(id, title, language) VALUES (?, ?, ?)",
                (DEFAULT_PROJECT_ID, "Default", "en"),
            )
            con.commit()

    # -------------------------
    # Async wrappers
    # -------------------------
    async def a_init_db(self) -> None:
        await anyio.to_thread.run_sync(self.init_db)

    async def a_create_project(self, title: str, language: str) -> Dict[str, Any]:
        return await anyio.to_thread.run_sync(self.create_project, title, language)

    async def a_get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        return await anyio.to_thread.run_sync(self.get_project, project_id)

    async def a_get_project_language(self, project_id: str) -> str:
        return await anyio.to_thread.run_sync(self.get_project_language, project_id)

    async def a_list_projects(self) -> List[Dict[str, Any]]:
        return await anyio.to_thread.run_sync(self.list_projects)

    async def a_delete_project(self, project_id: str) -> None:
        await anyio.to_thread.run_sync(self.delete_project, project_id)

    async def a_kv_set(self, key: str, value: Dict[str, Any], *, project_id: str = DEFAULT_PROJECT_ID) -> None:
        await anyio.to_thread.run_sync(self.kv_set, key, value, project_id)

    async def a_kv_get(self, key: str, *, project_id: str = DEFAULT_PROJECT_ID) -> Optional[Dict[str, Any]]:
        return await anyio.to_thread.run_sync(self.kv_get, key, project_id)

    async def a_kv_delete(self, key: str, *, project_id: str = DEFAULT_PROJECT_ID) -> None:
        await anyio.to_thread.run_sync(self.kv_delete, key, project_id)

    async def a_reset_all(self, *, project_id: str = DEFAULT_PROJECT_ID) -> None:
        await anyio.to_thread.run_sync(self.reset_all, project_id)

    async def a_save_characters(self, payload: Dict[str, Any], *, project_id: str = DEFAULT_PROJECT_ID) -> None:
        await anyio.to_thread.run_sync(self.save_characters, payload, project_id)

    async def a_list_characters_grouped(self, *, project_id: str = DEFAULT_PROJECT_ID) -> Dict[str, List[Dict[str, Any]]]:
        return await anyio.to_thread.run_sync(self.list_characters_grouped, project_id)

    async def a_delete_character(self, char_id: int, *, project_id: str = DEFAULT_PROJECT_ID) -> None:
        await anyio.to_thread.run_sync(self.delete_character, char_id, project_id)

    async def a_update_character(
        self,
        char_id: int,
        patch: Dict[str, Any],
        *,
        project_id: str = DEFAULT_PROJECT_ID
    ) -> Optional[Dict[str, Any]]:
        return await anyio.to_thread.run_sync(self.update_character, char_id, patch, project_id)

    async def a_load_state(self, chapter: int = 1, *, project_id: str = DEFAULT_PROJECT_ID) -> Dict[str, Any]:
        return await anyio.to_thread.run_sync(self.load_state, chapter, project_id)

    async def a_kv_set_raw(self, key: str, raw_json: str, *, project_id: str = DEFAULT_PROJECT_ID) -> None:
        await anyio.to_thread.run_sync(self.kv_set_raw, key, raw_json, project_id)

    async def a_list_beat_texts(self, chapter: int = 1, *, project_id: str = DEFAULT_PROJECT_ID) -> dict[int, str]:
        return await anyio.to_thread.run_sync(self.list_beat_texts, chapter, project_id)

    async def a_clear_beat_text(self, chapter: int, beat_index: int, *, project_id: str = DEFAULT_PROJECT_ID) -> None:
        await anyio.to_thread.run_sync(self.clear_beat_text, chapter, beat_index, project_id)

    async def a_clear_beat_texts_from(
        self, chapter: int, from_beat_index: int, *, project_id: str = DEFAULT_PROJECT_ID
    ) -> None:
        await anyio.to_thread.run_sync(self.clear_beat_texts_from, chapter, from_beat_index, project_id)

    async def a_get_prev_chapter_continuity(self, chapter: int, *, project_id: str = DEFAULT_PROJECT_ID) -> Optional[str]:
        return await anyio.to_thread.run_sync(self.get_prev_chapter_continuity, chapter, project_id)

    async def a_get_prev_chapter_ending_excerpt(
        self, chapter: int, max_chars: int = 4500, *, project_id: str = DEFAULT_PROJECT_ID
    ) -> Optional[str]:
        return await anyio.to_thread.run_sync(self.get_prev_chapter_ending_excerpt, chapter, max_chars, project_id)

    async def a_get_chapter_beat_texts_ordered(self, chapter: int, *, project_id: str = DEFAULT_PROJECT_ID) -> List[str]:
        return await anyio.to_thread.run_sync(self.get_chapter_beat_texts_ordered, chapter, project_id)

    async def a_get_last_written_beat_text(self, chapter: int, *, project_id: str = DEFAULT_PROJECT_ID) -> str:
        return await anyio.to_thread.run_sync(self.get_last_written_beat_text, chapter, project_id)

    async def a_project_exists(self, project_id: str) -> bool:
        return await anyio.to_thread.run_sync(self.project_exists, project_id)

    # -------------------------
    # Project ops (sync)
    # -------------------------
    def create_project(self, title: str, language: str) -> Dict[str, Any]:
        project_id = uuid.uuid4().hex
        with self._connect() as con:
            con.execute(
                "INSERT INTO projects(id, title, language) VALUES(?, ?, ?)",
                (project_id, title, language),
            )
            con.commit()
        return {"id": project_id, "title": title, "language": language}

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as con:
            row = con.execute(
                "SELECT id, title, language, created_at FROM projects WHERE id = ? LIMIT 1",
                (project_id,),
            ).fetchone()
        if not row:
            return None
        return {"id": row[0], "title": row[1], "language": row[2], "created_at": row[3]}

    def get_project_language(self, project_id: str) -> str:
        with self._connect() as con:
            row = con.execute(
                "SELECT language FROM projects WHERE id = ? LIMIT 1",
                (project_id,),
            ).fetchone()
        lang = (row[0] if row else "") or "en"
        return str(lang).strip().lower() or "en"

    def list_projects(self) -> List[Dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT id, title, language, created_at FROM projects ORDER BY created_at DESC"
            ).fetchall()
        return [{"id": r[0], "title": r[1], "language": r[2], "created_at": r[3]} for r in rows]

    def delete_project(self, project_id: str) -> None:
        if project_id == DEFAULT_PROJECT_ID:
            # Keep default around during transition
            return
        with self._connect() as con:
            con.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            con.commit()

    # -------------------------
    # KV (sync)
    # -------------------------
    def kv_set(self, key: str, value: Dict[str, Any], project_id: str = DEFAULT_PROJECT_ID) -> None:
        raw = json.dumps(value, ensure_ascii=False)
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO kv(project_id, key, json, updated_at)
                VALUES (?, ?, ?, strftime('%s','now'))
                ON CONFLICT(project_id, key) DO UPDATE SET
                    json=excluded.json,
                    updated_at=strftime('%s','now')
                """,
                (project_id, key, raw),
            )
            con.commit()

    def kv_get(self, key: str, project_id: str = DEFAULT_PROJECT_ID) -> Optional[Dict[str, Any]]:
        with self._connect() as con:
            row = con.execute(
                "SELECT json FROM kv WHERE project_id = ? AND key = ?",
                (project_id, key),
            ).fetchone()
        if not row:
            return None
        return json.loads(row[0])

    def kv_delete(self, key: str, project_id: str = DEFAULT_PROJECT_ID) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM kv WHERE project_id = ? AND key = ?", (project_id, key))
            con.commit()

    def kv_set_raw(self, key: str, raw_json: str, project_id: str = DEFAULT_PROJECT_ID) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO kv(project_id, key, json, updated_at)
                VALUES (?, ?, ?, strftime('%s','now'))
                ON CONFLICT(project_id, key) DO UPDATE SET
                    json=excluded.json,
                    updated_at=strftime('%s','now')
                """,
                (project_id, key, raw_json),
            )
            con.commit()

    def reset_all(self, project_id: str = DEFAULT_PROJECT_ID) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM kv WHERE project_id = ?", (project_id,))
            con.execute("DELETE FROM characters WHERE project_id = ?", (project_id,))
            con.commit()

    # -------------------------
    # Characters (sync)
    # -------------------------
    def save_characters(self, payload: Dict[str, Any], project_id: str = DEFAULT_PROJECT_ID) -> None:
        def rows(kind: str, items: List[Dict[str, Any]]) -> List[Tuple[str, str, str, str, str]]:
            out = []
            for x in items:
                out.append((project_id, kind, x["name"], x["role"], x["bio"]))
            return out

        protagonists = payload.get("protagonists", [])
        antagonists = payload.get("antagonists", [])
        supporting = payload.get("supporting", [])

        all_rows = (
            rows("protagonist", protagonists)
            + rows("antagonist", antagonists)
            + rows("supporting", supporting)
        )

        with self._connect() as con:
            con.execute("DELETE FROM characters WHERE project_id = ?", (project_id,))
            if all_rows:
                con.executemany(
                    "INSERT INTO characters(project_id, kind, name, role, bio) VALUES (?, ?, ?, ?, ?)",
                    all_rows,
                )
            con.commit()

    def list_characters_grouped(self, project_id: str = DEFAULT_PROJECT_ID) -> Dict[str, List[Dict[str, Any]]]:
        with self._connect() as con:
            cur = con.execute(
                "SELECT id, kind, name, role, bio FROM characters WHERE project_id = ? ORDER BY id ASC",
                (project_id,),
            )
            items = [{"id": r[0], "kind": r[1], "name": r[2], "role": r[3], "bio": r[4]} for r in cur.fetchall()]

        grouped = {"protagonists": [], "antagonists": [], "supporting": []}
        for c in items:
            if c["kind"] == "protagonist":
                grouped["protagonists"].append(c)
            elif c["kind"] == "antagonist":
                grouped["antagonists"].append(c)
            else:
                grouped["supporting"].append(c)
        return grouped

    def delete_character(self, char_id: int, project_id: str = DEFAULT_PROJECT_ID) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM characters WHERE id = ? AND project_id = ?", (char_id, project_id))
            con.commit()

    def update_character(self, char_id: int, patch: Dict[str, Any], project_id: str = DEFAULT_PROJECT_ID) -> Optional[Dict[str, Any]]:
        allowed = {"name", "role", "bio", "kind"}
        fields = {k: v for k, v in patch.items() if k in allowed}
        if not fields:
            return None

        set_sql = ", ".join([f"{k} = ?" for k in fields.keys()])
        values = list(fields.values()) + [char_id, project_id]

        with self._connect() as con:
            con.execute(f"UPDATE characters SET {set_sql} WHERE id = ? AND project_id = ?", values)
            row = con.execute(
                "SELECT id, kind, name, role, bio FROM characters WHERE id = ? AND project_id = ?",
                (char_id, project_id),
            ).fetchone()
            con.commit()

        if not row:
            return None
        return {"id": row[0], "kind": row[1], "name": row[2], "role": row[3], "bio": row[4]}

    # -------------------------
    # State helpers (sync)
    # -------------------------
    def load_state(self, chapter: int = 1, project_id: str = DEFAULT_PROJECT_ID) -> Dict[str, Any]:
        selected = self.kv_get("selected", project_id=project_id) or None
        plot = self.kv_get("plot", project_id=project_id) or None
        characters = self.list_characters_grouped(project_id=project_id)
        beats_plan = self.kv_get(f"beats_ch{chapter}", project_id=project_id) or None
        beat_texts = self.list_beat_texts(chapter=chapter, project_id=project_id)

        return {
            "project_id": project_id,
            "selected": selected,
            "plot": plot,
            "characters": characters,
            "chapter": chapter,
            "beats": beats_plan,
            "beat_texts": beat_texts,
        }

    def list_beat_texts(self, chapter: int = 1, project_id: str = DEFAULT_PROJECT_ID) -> dict[int, str]:
        prefix = f"ch{chapter}_beat_"
        like_pat = prefix + "%"

        with self._connect() as con:
            rows = con.execute(
                "SELECT key, json FROM kv WHERE project_id = ? AND key LIKE ?",
                (project_id, like_pat),
            ).fetchall()

        out: dict[int, str] = {}
        for key, raw in rows:
            try:
                idx = int(key.replace(prefix, ""))
                obj = json.loads(raw)
                if isinstance(obj, dict) and isinstance(obj.get("text"), str):
                    out[idx] = obj["text"]
            except Exception:
                continue
        return out

    def clear_beat_text(self, chapter: int, beat_index: int, project_id: str = DEFAULT_PROJECT_ID) -> None:
        key = f"ch{chapter}_beat_{beat_index}"
        with self._connect() as con:
            con.execute("DELETE FROM kv WHERE project_id = ? AND key = ?", (project_id, key))
            con.commit()

    def clear_beat_texts_from(self, chapter: int, from_beat_index: int, project_id: str = DEFAULT_PROJECT_ID) -> None:
        prefix = f"ch{chapter}_beat_"
        like_pat = prefix + "%"

        with self._connect() as con:
            rows = con.execute(
                "SELECT key FROM kv WHERE project_id = ? AND key LIKE ?",
                (project_id, like_pat),
            ).fetchall()

            keys_to_delete: list[tuple[str, str]] = []
            for (k,) in rows:
                try:
                    idx = int(k.replace(prefix, ""))
                    if idx >= from_beat_index:
                        keys_to_delete.append((project_id, k))
                except Exception:
                    continue

            if keys_to_delete:
                con.executemany("DELETE FROM kv WHERE project_id = ? AND key = ?", keys_to_delete)
            con.commit()

    def get_prev_chapter_continuity(self, chapter: int, project_id: str = DEFAULT_PROJECT_ID) -> Optional[str]:
        prev = chapter - 1
        if prev < 1:
            return None

        obj = self.kv_get(f"ch{prev}_continuity", project_id=project_id)
        if obj is None:
            return None

        if isinstance(obj, str):
            return obj

        if isinstance(obj, dict):
            if isinstance(obj.get("text"), str):
                return obj["text"]
            bullets = obj.get("bullets")
            if isinstance(bullets, list):
                bullets = [b for b in bullets if isinstance(b, str) and b.strip()]
                if bullets:
                    return "\n".join(f"- {b.strip()}" for b in bullets)

        return None

    def get_prev_chapter_ending_excerpt(self, chapter: int, max_chars: int = 4500, project_id: str = DEFAULT_PROJECT_ID) -> Optional[str]:
        prev = chapter - 1
        if prev < 1:
            return None

        prefix = f"ch{prev}_beat_"
        like_pat = prefix + "%"

        with self._connect() as con:
            rows = con.execute(
                "SELECT key, json FROM kv WHERE project_id = ? AND key LIKE ?",
                (project_id, like_pat),
            ).fetchall()

        if not rows:
            return None

        parsed: list[tuple[int, str]] = []
        for key, raw in rows:
            try:
                idx = int(key.replace(prefix, ""))
                obj = json.loads(raw)
                txt = obj.get("text") if isinstance(obj, dict) else None
                if isinstance(txt, str) and txt.strip():
                    parsed.append((idx, txt))
            except Exception:
                continue

        if not parsed:
            return None

        parsed.sort(key=lambda x: x[0])
        last_idx = parsed[-1][0]

        texts = []
        for idx in (last_idx - 1, last_idx):
            for j, t in parsed:
                if j == idx:
                    texts.append(t)
                    break

        merged = "\n\n".join(texts).strip()
        if not merged:
            return None

        if len(merged) > max_chars:
            merged = merged[-max_chars:]

        return merged

    def get_chapter_beat_texts_ordered(self, chapter: int, project_id: str = DEFAULT_PROJECT_ID) -> List[str]:
        prefix = f"ch{chapter}_beat_"
        like_pat = prefix + "%"

        with self._connect() as con:
            rows = con.execute(
                "SELECT key, json FROM kv WHERE project_id = ? AND key LIKE ?",
                (project_id, like_pat),
            ).fetchall()

        parsed: List[Tuple[int, str]] = []
        for key, raw in rows:
            try:
                idx = int(key.replace(prefix, ""))
                obj = json.loads(raw)
                txt = obj.get("text") if isinstance(obj, dict) else None
                if isinstance(txt, str) and txt.strip():
                    parsed.append((idx, txt))
            except Exception:
                continue

        parsed.sort(key=lambda x: x[0])
        return [t for _, t in parsed]

    def get_last_written_beat_text(self, chapter: int, project_id: str = DEFAULT_PROJECT_ID) -> str:
        prefix = f"ch{chapter}_beat_"
        like_pat = prefix + "%"

        with self._connect() as con:
            rows = con.execute(
                "SELECT key, json FROM kv WHERE project_id = ? AND key LIKE ?",
                (project_id, like_pat),
            ).fetchall()

        best_i = None
        best_text = ""

        for key, raw in rows:
            if not isinstance(key, str) or not key.startswith(prefix):
                continue
            try:
                i = int(key[len(prefix):])
            except Exception:
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                continue

            txt = obj.get("text") if isinstance(obj, dict) else None
            if not isinstance(txt, str) or not txt.strip():
                continue

            if best_i is None or i > best_i:
                best_i = i
                best_text = txt

        return best_text

    def project_exists(self, project_id: str) -> bool:
        with self._connect() as con:
            row = con.execute("SELECT 1 FROM projects WHERE id = ? LIMIT 1", (project_id,)).fetchone()
        return bool(row)

    def scoped(self, project_id: str):
        return _ScopedStore(self, project_id)


class _ScopedStore:
    """
    Adapter that keeps old signatures (no project_id arg),
    but routes every call to a fixed project_id.
    """
    def __init__(self, store: MemoryStore, project_id: str):
        self._s = store
        self.project_id = project_id

    # KV
    async def a_kv_set(self, key: str, value: Dict[str, Any]) -> None:
        await self._s.a_kv_set(key, value, project_id=self.project_id)

    async def a_kv_get(self, key: str) -> Optional[Dict[str, Any]]:
        return await self._s.a_kv_get(key, project_id=self.project_id)

    async def a_kv_delete(self, key: str) -> None:
        await self._s.a_kv_delete(key, project_id=self.project_id)

    async def a_kv_set_raw(self, key: str, raw_json: str) -> None:
        await self._s.a_kv_set_raw(key, raw_json, project_id=self.project_id)

    # Characters
    async def a_save_characters(self, payload: Dict[str, Any]) -> None:
        await self._s.a_save_characters(payload, project_id=self.project_id)

    async def a_list_characters_grouped(self) -> Dict[str, List[Dict[str, Any]]]:
        return await self._s.a_list_characters_grouped(project_id=self.project_id)

    async def a_delete_character(self, char_id: int) -> None:
        await self._s.a_delete_character(char_id, project_id=self.project_id)

    async def a_update_character(self, char_id: int, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return await self._s.a_update_character(char_id, patch, project_id=self.project_id)

    # State / beats helpers
    async def a_load_state(self, chapter: int = 1) -> Dict[str, Any]:
        return await self._s.a_load_state(chapter=chapter, project_id=self.project_id)

    async def a_list_beat_texts(self, chapter: int = 1) -> dict[int, str]:
        return await self._s.a_list_beat_texts(chapter=chapter, project_id=self.project_id)

    async def a_clear_beat_text(self, chapter: int, beat_index: int) -> None:
        await self._s.a_clear_beat_text(chapter, beat_index, project_id=self.project_id)

    async def a_clear_beat_texts_from(self, chapter: int, from_beat_index: int) -> None:
        await self._s.a_clear_beat_texts_from(chapter, from_beat_index, project_id=self.project_id)

    async def a_get_prev_chapter_continuity(self, chapter: int) -> Optional[str]:
        return await self._s.a_get_prev_chapter_continuity(chapter, project_id=self.project_id)

    async def a_get_prev_chapter_ending_excerpt(self, chapter: int, max_chars: int = 4500) -> Optional[str]:
        return await self._s.a_get_prev_chapter_ending_excerpt(chapter, max_chars=max_chars, project_id=self.project_id)

    async def a_get_chapter_beat_texts_ordered(self, chapter: int) -> List[str]:
        return await self._s.a_get_chapter_beat_texts_ordered(chapter, project_id=self.project_id)

    async def a_get_last_written_beat_text(self, chapter: int) -> str:
        return await self._s.a_get_last_written_beat_text(chapter, project_id=self.project_id)
