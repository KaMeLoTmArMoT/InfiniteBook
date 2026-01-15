import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

import anyio


class MemoryStore:
    def __init__(self, db_path: str = "infinitebook.sqlite"):
        self.db_path = db_path

    def init_db(self) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute("PRAGMA foreign_keys=ON;")

            con.execute("""
                CREATE TABLE IF NOT EXISTS kv (
                    key TEXT PRIMARY KEY,
                    json TEXT NOT NULL,
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                )
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS characters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,           -- protagonist | antagonist | supporting
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    bio TEXT NOT NULL
                )
            """)

            con.commit()

    # -------------------------
    # Async wrappers (non-blocking for FastAPI event loop)
    # -------------------------
    async def a_init_db(self) -> None:
        await anyio.to_thread.run_sync(self.init_db)

    async def a_kv_set(self, key: str, value: Dict[str, Any]) -> None:
        await anyio.to_thread.run_sync(self.kv_set, key, value)

    async def a_kv_get(self, key: str) -> Optional[Dict[str, Any]]:
        return await anyio.to_thread.run_sync(self.kv_get, key)

    async def a_kv_delete(self, key: str) -> None:
        await anyio.to_thread.run_sync(self.kv_delete, key)

    async def a_reset_all(self) -> None:
        await anyio.to_thread.run_sync(self.reset_all)

    async def a_save_characters(self, payload: Dict[str, Any]) -> None:
        await anyio.to_thread.run_sync(self.save_characters, payload)

    async def a_list_characters_grouped(self) -> Dict[str, List[Dict[str, Any]]]:
        return await anyio.to_thread.run_sync(self.list_characters_grouped)

    async def a_delete_character(self, char_id: int) -> None:
        await anyio.to_thread.run_sync(self.delete_character, char_id)

    async def a_update_character(self, char_id: int, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return await anyio.to_thread.run_sync(self.update_character, char_id, patch)

    async def a_load_state(self, chapter: int = 1) -> Dict[str, Any]:
        return await anyio.to_thread.run_sync(self.load_state, chapter)

    async def a_kv_set_raw(self, key: str, raw_json: str) -> None:
        await anyio.to_thread.run_sync(self.kv_set_raw, key, raw_json)

    async def a_list_beat_texts(self, chapter: int = 1) -> dict[int, str]:
        return await anyio.to_thread.run_sync(self.list_beat_texts, chapter)

    async def a_clear_beat_text(self, chapter: int, beat_index: int) -> None:
        await anyio.to_thread.run_sync(self.clear_beat_text, chapter, beat_index)

    async def a_clear_beat_texts_from(self, chapter: int, from_beat_index: int) -> None:
        await anyio.to_thread.run_sync(self.clear_beat_texts_from, chapter, from_beat_index)

    async def a_get_prev_chapter_continuity(self, chapter: int) -> Optional[str]:
        return await anyio.to_thread.run_sync(self.get_prev_chapter_continuity, chapter)

    async def a_get_prev_chapter_ending_excerpt(self, chapter: int, max_chars: int = 4500) -> Optional[str]:
        return await anyio.to_thread.run_sync(self.get_prev_chapter_ending_excerpt, chapter, max_chars)

    async def a_get_chapter_beat_texts_ordered(self, chapter: int) -> List[str]:
        return await anyio.to_thread.run_sync(self.get_chapter_beat_texts_ordered, chapter)

    # -------------------------
    # Sync implementation
    # -------------------------
    def kv_set(self, key: str, value: Dict[str, Any]) -> None:
        raw = json.dumps(value, ensure_ascii=False)
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                """
                INSERT INTO kv(key, json, updated_at)
                VALUES (?, ?, strftime('%s','now'))
                ON CONFLICT(key) DO UPDATE SET
                    json=excluded.json,
                    updated_at=strftime('%s','now')
                """,
                (key, raw),
            )
            con.commit()

    def kv_get(self, key: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as con:
            row = con.execute("SELECT json FROM kv WHERE key = ?", (key,)).fetchone()
            if not row:
                return None
            return json.loads(row[0])

    def kv_delete(self, key: str) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute("DELETE FROM kv WHERE key = ?", (key,))
            con.commit()

    def reset_all(self) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute("DELETE FROM kv")
            con.execute("DELETE FROM characters")
            con.commit()

    def save_characters(self, payload: Dict[str, Any]) -> None:
        """
        Expected payload:
        {
          "protagonists": [{name, role, bio}, ...],
          "antagonists":  [{name, role, bio}, ...],
          "supporting":   [{name, role, bio}, ...]
        }
        """
        def rows(kind: str, items: List[Dict[str, Any]]) -> List[Tuple[str, str, str, str]]:
            out = []
            for x in items:
                out.append((kind, x["name"], x["role"], x["bio"]))
            return out

        protagonists = payload.get("protagonists", [])
        antagonists = payload.get("antagonists", [])
        supporting = payload.get("supporting", [])

        with sqlite3.connect(self.db_path) as con:
            con.execute("DELETE FROM characters")
            con.executemany(
                "INSERT INTO characters(kind, name, role, bio) VALUES (?, ?, ?, ?)",
                rows("protagonist", protagonists) + rows("antagonist", antagonists) + rows("supporting", supporting),
            )
            con.commit()

    def list_characters_grouped(self) -> Dict[str, List[Dict[str, Any]]]:
        with sqlite3.connect(self.db_path) as con:
            cur = con.execute("SELECT id, kind, name, role, bio FROM characters ORDER BY id ASC")
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

    def delete_character(self, char_id: int) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute("DELETE FROM characters WHERE id = ?", (char_id,))
            con.commit()

    def update_character(self, char_id: int, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {"name", "role", "bio", "kind"}
        fields = {k: v for k, v in patch.items() if k in allowed}

        if not fields:
            return None

        set_sql = ", ".join([f"{k} = ?" for k in fields.keys()])
        values = list(fields.values()) + [char_id]

        with sqlite3.connect(self.db_path) as con:
            con.execute(f"UPDATE characters SET {set_sql} WHERE id = ?", values)
            row = con.execute("SELECT id, kind, name, role, bio FROM characters WHERE id = ?", (char_id,)).fetchone()
            con.commit()

        if not row:
            return None
        return {"id": row[0], "kind": row[1], "name": row[2], "role": row[3], "bio": row[4]}

    def load_state(self, chapter: int = 1) -> Dict[str, Any]:
        selected = self.kv_get("selected") or None
        plot = self.kv_get("plot") or None
        characters = self.list_characters_grouped()
        beats_plan = self.kv_get(f"beats_ch{chapter}") or None
        beat_texts = self.list_beat_texts(chapter=chapter)

        return {
            "selected": selected,
            "plot": plot,
            "characters": characters,
            "chapter": chapter,
            "beats": beats_plan,
            "beat_texts": beat_texts,
        }

    def kv_set_raw(self, key: str, raw_json: str) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                """
                INSERT INTO kv(key, json, updated_at)
                VALUES (?, ?, strftime('%s', 'now')) ON CONFLICT(key) DO
                UPDATE SET
                    json=excluded.json,
                    updated_at=strftime('%s','now')
                """,
                (key, raw_json),
            )
            con.commit()

    def list_beat_texts(self, chapter: int = 1) -> dict[int, str]:
        prefix = f"ch{chapter}_beat_"
        like_pat = prefix + "%"

        with sqlite3.connect(self.db_path) as con:
            rows = con.execute(
                "SELECT key, json FROM kv WHERE key LIKE ?",
                (like_pat,),
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

    def clear_beat_text(self, chapter: int, beat_index: int) -> None:
        key = f"ch{chapter}_beat_{beat_index}"
        with sqlite3.connect(self.db_path) as con:
            con.execute("DELETE FROM kv WHERE key = ?", (key,))
            con.commit()

    def clear_beat_texts_from(self, chapter: int, from_beat_index: int) -> None:
        prefix = f"ch{chapter}_beat_"
        like_pat = prefix + "%"

        with sqlite3.connect(self.db_path) as con:
            rows = con.execute("SELECT key FROM kv WHERE key LIKE ?", (like_pat,)).fetchall()

            keys_to_delete: list[tuple[str]] = []
            for (k,) in rows:
                try:
                    idx = int(k.replace(prefix, ""))
                    if idx >= from_beat_index:
                        keys_to_delete.append((k,))
                except Exception:
                    continue

            if keys_to_delete:
                con.executemany("DELETE FROM kv WHERE key = ?", keys_to_delete)
            con.commit()

    def get_prev_chapter_continuity(self, chapter: int) -> Optional[str]:
        """
        Returns continuity capsule for chapter-1, stored under:
          ch{prev}_continuity  -> {"bullets": [...]} or {"text": "..."} or raw string
        """
        prev = chapter - 1
        if prev < 1:
            return None

        obj = self.kv_get(f"ch{prev}_continuity")
        if obj is None:
            return None

        # accept a few formats
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

    def get_prev_chapter_ending_excerpt(self, chapter: int, max_chars: int = 4500) -> Optional[str]:
        """
        Returns tail excerpt from previous chapter prose:
          ch{prev}_beat_{i} values are JSON with {"text": "..."}.
        We concatenate last 1-2 beats (if present) and slice tail.
        """
        prev = chapter - 1
        if prev < 1:
            return None

        # find max beat index that exists for prev chapter
        prefix = f"ch{prev}_beat_"
        like_pat = prefix + "%"

        with sqlite3.connect(self.db_path) as con:
            rows = con.execute("SELECT key, json FROM kv WHERE key LIKE ?", (like_pat,)).fetchall()

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

        # take last 2 beats if available
        texts = []
        for idx in (last_idx - 1, last_idx):
            for j, t in parsed:
                if j == idx:
                    texts.append(t)
                    break

        merged = "\n\n".join(texts).strip()
        if not merged:
            return None

        # slice tail (last N chars) [web:492]
        if len(merged) > max_chars:
            merged = merged[-max_chars:]

        return merged

    def get_chapter_beat_texts_ordered(self, chapter: int) -> List[str]:
        prefix = f"ch{chapter}_beat_"
        like_pat = prefix + "%"

        with sqlite3.connect(self.db_path) as con:
            rows = con.execute("SELECT key, json FROM kv WHERE key LIKE ?", (like_pat,)).fetchall()

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
