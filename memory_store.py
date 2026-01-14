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

    async def a_load_state(self) -> Dict[str, Any]:
        return await anyio.to_thread.run_sync(self.load_state)

    async def a_kv_set_raw(self, key: str, raw_json: str) -> None:
        await anyio.to_thread.run_sync(self.kv_set_raw, key, raw_json)

    async def a_list_beat_texts(self, chapter: int = 1) -> dict[int, str]:
        return await anyio.to_thread.run_sync(self.list_beat_texts, chapter)

    async def a_clear_beat_text(self, chapter: int, beat_index: int) -> None:
        await anyio.to_thread.run_sync(self.clear_beat_text, chapter, beat_index)

    async def a_clear_beat_texts_from(self, chapter: int, from_beat_index: int) -> None:
        await anyio.to_thread.run_sync(self.clear_beat_texts_from, chapter, from_beat_index)

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

    def load_state(self) -> Dict[str, Any]:
        selected = self.kv_get("selected") or None
        plot = self.kv_get("plot") or None
        beats_ch1 = self.kv_get("beats_ch1") or None
        characters = self.list_characters_grouped()
        beat_texts_ch1 = self.list_beat_texts(chapter=1)
        return {
            "selected": selected,
            "plot": plot,
            "characters": characters,
            "beats_ch1": beats_ch1,
            "beat_texts_ch1": beat_texts_ch1,
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
                "SELECT key, json FROM kv WHERE key LIKE ? ORDER BY key ASC",
                (like_pat,),
            ).fetchall()

        out: dict[int, str] = {}
        for key, raw in rows:
            try:
                idx_str = key.replace(prefix, "")
                idx = int(idx_str)
                obj = json.loads(raw)
                if isinstance(obj, dict) and "text" in obj:
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
        """
        Deletes ch{chapter}_beat_{i} for all i >= from_beat_index.
        Avoid relying on lexicographic ordering (beat_10 vs beat_2), parse indexes.
        """
        prefix = f"ch{chapter}_beat_"
        like_pat = prefix + "%"

        with sqlite3.connect(self.db_path) as con:
            rows = con.execute("SELECT key FROM kv WHERE key LIKE ?", (like_pat,)).fetchall()

            keys_to_delete = []
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
