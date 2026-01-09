"""local_es.py – Local Elasticsearch implementation (cross‑platform, UTF‑8‑safe)

This module simulates a subset of Elasticsearch by persisting documents as JSON
files on the local filesystem.  The design goals are:

* **Robust cross‑platform behaviour** (Windows/POSIX) – atomic writes with
  `os.replace`, no reliance on POSIX‑only semantics.
* **UTF‑8 persistence** – files created in legacy encodings are lazily migrated.
* **Data‑safety first** – *never* overwrite an existing index unless explicitly
  requested; corrupted files are preserved via ``.bak`` before we attempt any
  recovery so historic logs are not silently lost.

Only the subset of APIs that OxyGent actually uses is implemented.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
import locale
import logging
import os
from typing import Any, Dict, Optional

import aiofiles
import aiofiles.os
from aiofiles import tempfile

from oxygent.config import Config

from .base_es import BaseEs

logger = logging.getLogger(__name__)


class LocalEs(BaseEs):
    """Very small file‑system‑backed ES shim."""

    def __init__(self) -> None:  # noqa: D401 – simple init
        self.data_dir: str = os.path.join(Config.get_cache_save_dir(), "local_es_data")
        os.makedirs(self.data_dir, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    # Utilities (paths, atomic IO helpers)
    # ------------------------------------------------------------------

    def _index_path(self, index_name: str) -> str:
        return os.path.join(self.data_dir, f"{index_name}.json")

    def _mapping_path(self, index_name: str) -> str:
        return os.path.join(self.data_dir, f"{index_name}_mapping.json")

    async def _write_json_atomic(self, path: str, data: Dict[str, Any]) -> None:
        """Write *data* to *path* atomically, UTF‑8 encoded."""
        async with tempfile.NamedTemporaryFile(
            mode="w", delete=False, dir=self.data_dir, suffix=".tmp", encoding="utf-8"
        ) as tf:
            await tf.write(json.dumps(data, ensure_ascii=False, indent=2))
            tmp_path = tf.name
        try:
            await aiofiles.os.replace(tmp_path, path)
        finally:
            if await aiofiles.os.path.exists(tmp_path):
                await aiofiles.os.unlink(tmp_path)

    # ------------------------------------------------------------------
    # Encoding‑aware read helper (returns **None** on unrecoverable corruption)
    # ------------------------------------------------------------------

    async def _read_json_safe(self, path: str) -> Optional[Dict[str, Any]]:
        if not await aiofiles.os.path.exists(path):
            return {}

        # a) try utf‑8
        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                return json.loads(await f.read())
        except UnicodeDecodeError:
            pass  # Will fallback.
        except json.JSONDecodeError:
            logger.error("JSON corrupted (utf‑8) → %s", path)
            return None  # unrecoverable corruption

        # b) fallback – system code‑page
        fallback_enc = locale.getpreferredencoding(False) or "utf-8"
        try:
            async with aiofiles.open(path, "r", encoding=fallback_enc) as f:
                raw = await f.read()
            data = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.error("JSON corrupted (%s) → %s", fallback_enc, path)
            return None

        # c) successful fallback – migrate
        try:
            await self._write_json_atomic(path, data)
        except Exception as err:  # noqa: BLE001 – non‑critical
            logger.warning("Could not rewrite %s as UTF‑8: %s", path, err)
        return data

    # ------------------------------------------------------------------
    # Public ES‑like API
    # ------------------------------------------------------------------

    async def index_exists(self, index_name: str) -> bool:
        """Check if an index exists by verifying its data file.

        Args:
            index_name: Name of the index to check

        Returns:
            True if the index exists, False otherwise
        """
        index_path = self._index_path(index_name)
        return await aiofiles.os.path.exists(index_path)

    async def create_index(
        self, index_name: str, body: dict[str, Any]
    ) -> dict[str, bool]:
        """Create a new index with the given name and mapping body.
        
        Args:
            index_name: Name of the index to create
            body: Index configuration including mappings and settings
            
        Returns:
            Dictionary with acknowledged flag
        """
        if not index_name or not body:
            raise ValueError("index_name and body must not be empty")

        # 1) persist mapping (overwrite OK – mapping updates should be explicit)
        await self._write_json_atomic(self._mapping_path(index_name), body)

        # 2) create empty index *only if it does not exist* – avoids wiping logs
        index_path = self._index_path(index_name)
        if not await aiofiles.os.path.exists(index_path):
            await self._write_json_atomic(index_path, {})
        return {"acknowledged": True}

    async def insert(
        self,
        index_name: str,
        doc_id: str,
        body: dict[str, Any],
        *,
        update_mode: bool,
    ) -> dict[str, str]:
        data_path = self._index_path(index_name)
        backup_path = f"{data_path}.bak"

        lock = self._locks.setdefault(index_name, asyncio.Lock())
        async with lock:
            # --- load existing data ---
            data = await self._read_json_safe(data_path)

            if data is None:  # unrecoverable corruption; try backup once
                if await aiofiles.os.path.exists(backup_path):
                    await aiofiles.os.replace(backup_path, data_path)
                    data = await self._read_json_safe(data_path)

            if data is None:
                # still corrupted – preserve original file, switch to fresh store
                corrupt_path = f"{data_path}.corrupt"
                await aiofiles.os.rename(data_path, corrupt_path)
                logger.error(
                    "Index %s is corrupted – moved to %s", index_name, corrupt_path
                )
                data = {}

            # --- apply mutation ---
            if update_mode:
                merged = data.get(doc_id, {})
                merged.update(body)
                data[doc_id] = merged
            else:
                data[doc_id] = body

            # --- backup & persist ---
            if await aiofiles.os.path.exists(data_path):
                await aiofiles.os.replace(data_path, backup_path)
            await self._write_json_atomic(data_path, data)

        return {"_id": doc_id, "result": "updated" if update_mode else "created"}

    async def index(self, index_name: str, doc_id: str, body: dict[str, Any]):
        return await self.insert(index_name, doc_id, body, update_mode=False)

    async def update(self, index_name: str, doc_id: str, body: dict[str, Any]):
        return await self.insert(index_name, doc_id, body, update_mode=True)

    async def exists(self, index_name: str, doc_id: str) -> bool:
        data = await self._read_json_safe(self._index_path(index_name)) or {}
        return doc_id in data

    async def search(self, index_name: str, body: dict[str, Any]):
        data = await self._read_json_safe(self._index_path(index_name)) or {}
        query = body.get("query", {})
        docs = self._build_docs(data)
        filtered_docs = self._filter_docs(docs, query)
        docs = self._sort_docs(filtered_docs, body.get("sort", []))
        result_size = body.get("size", 10)
        result_docs = docs[:result_size]

        # Apply _source filtering if specified
        source_fields = body.get("_source")
        if source_fields and isinstance(source_fields, list):
            result_docs = self._apply_source_filtering(result_docs, source_fields)

        # handle aggregations（if needed）
        aggs = body.get("aggs", {})
        result = {"hits": {"hits": result_docs, "total": {"value": len(filtered_docs)}}}

        if aggs:
            # support aggregations statistics
            agg_results = {}
            for agg_name, agg_config in aggs.items():
                if "terms" in agg_config:
                    # terms aggregation
                    field = agg_config["terms"]["field"]
                    buckets = {}
                    for doc in filtered_docs:
                        source = doc.get("_source", {})
                        # extract nested field values
                        value = source
                        for part in field.split("."):
                            if isinstance(value, dict):
                                value = value.get(part, "")
                            else:
                                value = ""
                                break
                        if value is None:
                            value = ""
                        value_str = str(value)
                        buckets[value_str] = buckets.get(value_str, 0) + 1

                    agg_results[agg_name] = {
                        "buckets": [
                            {"key": k, "doc_count": v}
                            for k, v in buckets.items()
                        ]
                    }
                elif "filter" in agg_config:
                    # filter aggregation
                    filter_query = agg_config["filter"]
                    filtered_count = len(self._filter_docs(filtered_docs, filter_query))
                    agg_results[agg_name] = {"doc_count": filtered_count}
                elif "top_hits" in agg_config:
                    # top_hits aggregation (simplified version)
                    top_docs = docs[:agg_config["top_hits"].get("size", 1)]
                    agg_results[agg_name] = {
                        "hits": {"hits": top_docs}
                    }

            if agg_results:
                result["aggregations"] = agg_results

        return result

    # ------------------------------------------------------------------
    # Helpers for naive query execution
    # ------------------------------------------------------------------

    @staticmethod
    def _build_docs(data: dict[str, Any]):
        return [{"_id": k, "_source": v} for k, v in data.items()]

    @staticmethod
    def _apply_source_filtering(docs: list[dict[str, Any]], source_fields: list[str]):
        """Filter _source fields to only include specified fields."""
        filtered_docs = []
        for doc in docs:
            filtered_doc = doc.copy()
            filtered_source = {}
            for field in source_fields:
                if field in doc["_source"]:
                    filtered_source[field] = doc["_source"][field]
            filtered_doc["_source"] = filtered_source
            filtered_docs.append(filtered_doc)
        return filtered_docs

    def _filter_docs(self, docs: list[dict[str, Any]], query: dict[str, Any]) -> list[dict[str, Any]]:
        if not query:
            return docs

        # Support match query for full-text search (case-insensitive substring match)
        if "match" in query:
            match_query = query["match"]
            # Handle both simple match: {"field": "value"} and complex match: {"field": {"query": "value", "operator": "and"}}
            if isinstance(match_query, dict):
                field_name = None
                search_value = None
                operator = "or"  # default operator

                for k, v in match_query.items():
                    if isinstance(v, dict):
                        field_name = k
                        search_value = v.get("query", "")
                        operator = v.get("operator", "or")
                    else:
                        field_name = k
                        search_value = v

                if field_name and search_value:
                    search_terms = str(search_value).lower().split()
                    filtered_docs = []
                    for doc in docs:
                        field_value = str(doc["_source"].get(field_name, "")).lower()
                        if operator == "and":
                            # All terms must be present
                            if all(term in field_value for term in search_terms):
                                filtered_docs.append(doc)
                        else:
                            # At least one term must be present (or)
                            if any(term in field_value for term in search_terms):
                                filtered_docs.append(doc)
                    return filtered_docs
            return docs

        if "term" in query:
            k, v = next(iter(query["term"].items()))
            if k == "_id":
                return [d for d in docs if d["_id"] == v]
            return [d for d in docs if d["_source"].get(k) == v]

        if "terms" in query:
            k, vlist = next(iter(query["terms"].items()))
            return [d for d in docs if d["_source"].get(k) in vlist]

        if "bool" in query:
            bool_query = query["bool"]
            filtered_docs = docs.copy()

            # Process "must" conditions (must match - affects scoring)
            if "must" in bool_query:
                must_conditions = bool_query["must"]
                for condition in must_conditions:
                    filtered_docs = self._filter_docs(filtered_docs, condition)

            # Process "filter" conditions (filter context - no scoring, but must match)
            if "filter" in bool_query:
                filter_conditions = bool_query["filter"]
                for condition in filter_conditions:
                    filtered_docs = self._filter_docs(filtered_docs, condition)

            return filtered_docs

        if "range" in query:
            range_conditions = query["range"]
            filtered_docs = []
            for doc in docs:
                match = True
                for field, range_params in range_conditions.items():
                    value = doc["_source"].get(field, "")
                    value_str = str(value)

                    # Parse document timestamp
                    parsed_dt = None
                    try:
                        # Try full format with microseconds (26 chars like "2025-12-30 18:19:38.050895")
                        # Try without microseconds (19 chars like "2025-12-30 18:19:38")
                        time_formats = [
                            "%Y-%m-%d %H:%M:%S.%f",  # Full format with 6 microseconds
                            "%Y-%m-%d %H:%M:%S",     # Without microseconds
                        ]
                        for fmt in time_formats:
                            try:
                                parsed_dt = datetime.strptime(value_str, fmt)
                                break
                            except Exception:
                                continue
                    except Exception:
                        pass

                    # Actual range filtering logic
                    try:
                        if parsed_dt:
                            for op, threshold in range_params.items():
                                threshold_str = str(threshold)

                                # Parse threshold timestamp - try multiple formats
                                threshold_dt = None
                                for fmt in time_formats:
                                    try:
                                        threshold_dt = datetime.strptime(threshold_str, fmt)
                                        break
                                    except Exception:
                                        continue

                                if threshold_dt is None:
                                    continue

                                if op == "gte" and parsed_dt < threshold_dt:
                                    match = False
                                    break
                                elif op == "lte" and parsed_dt > threshold_dt:
                                    match = False
                                    break
                                elif op == "gt" and parsed_dt <= threshold_dt:
                                    match = False
                                    break
                                elif op == "lt" and parsed_dt >= threshold_dt:
                                    match = False
                                    break

                                if not match:
                                    break
                    except Exception:
                        # Fallback to string comparison
                        for op, threshold in range_params.items():
                            if op == "gte" and str(value) < str(threshold):
                                match = False
                                break
                            if op == "lte" and str(value) > str(threshold):
                                match = False
                                break
                            if op == "gt" and str(value) <= str(threshold):
                                match = False
                                break
                            if op == "lt" and str(value) >= str(threshold):
                                match = False
                                break
                if match:
                    filtered_docs.append(doc)

            return filtered_docs

        return docs

    async def find_node_safe(self, index_name: str, trace_id: str, node_id: str):
        result = await self.get_by_node_id(index_name, node_id)
        if result:
            if result["_source"].get("trace_id") == trace_id:
                return result
            else:
                logger.warning(
                    f"Node {node_id} found but trace_id mismatch: expected {trace_id}, got {result['_source'].get('trace_id')}"
                )

        compound_query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"trace_id": trace_id}},
                        {"term": {"node_id": node_id}},
                    ]
                }
            },
            "size": 1,
        }

        search_result = await self.search(index_name, compound_query)
        hits = search_result.get("hits", {}).get("hits", [])
        return hits[0] if hits else None

    def _match_single_condition(
        self, doc: dict[str, Any], condition: dict[str, Any]
    ) -> bool:
        if "term" in condition:
            k, v = next(iter(condition["term"].items()))
            if k == "_id":
                return doc["_id"] == v
            return doc["_source"].get(k) == v

        if "terms" in condition:
            k, vlist = next(iter(condition["terms"].items()))
            return doc["_source"].get(k) in vlist

        # Support match query in single condition context
        if "match" in condition:
            match_query = condition["match"]
            if isinstance(match_query, dict):
                field_name = None
                search_value = None
                operator = "or"

                for k, v in match_query.items():
                    if isinstance(v, dict):
                        field_name = k
                        search_value = v.get("query", "")
                        operator = v.get("operator", "or")
                    else:
                        field_name = k
                        search_value = v

                if field_name and search_value:
                    field_value = str(doc["_source"].get(field_name, "")).lower()
                    search_terms = str(search_value).lower().split()
                    if operator == "and":
                        return all(term in field_value for term in search_terms)
                    else:
                        return any(term in field_value for term in search_terms)

        return False

    @staticmethod
    def _sort_docs(docs: list[dict[str, Any]], spec: list[dict[str, Any]]):
        for s in reversed(spec):
            for field, order in s.items():
                reverse = order.get("order", "asc") == "desc"
                docs.sort(key=lambda d: d["_source"].get(field), reverse=reverse)
        return docs

    async def get_by_node_id(
        self, index_name: str, node_id: str
    ) -> Optional[dict[str, Any]]:
        data = await self._read_json_safe(self._index_path(index_name)) or {}

        for doc_id, doc_content in data.items():
            if isinstance(doc_content, dict) and doc_content.get("node_id") == node_id:
                return {"_id": doc_id, "_source": doc_content}

        return None

    async def update_by_node_id(
        self, index_name: str, node_id: str, updates: dict[str, Any]
    ) -> dict[str, str]:
        data_path = self._index_path(index_name)
        backup_path = f"{data_path}.bak"

        lock = self._locks.setdefault(index_name, asyncio.Lock())
        async with lock:
            data = await self._read_json_safe(data_path) or {}

            target_doc_id = None
            for doc_id, doc_content in data.items():
                if (
                    isinstance(doc_content, dict)
                    and doc_content.get("node_id") == node_id
                ):
                    target_doc_id = doc_id
                    break

            if target_doc_id is None:
                return {"_id": "", "result": "not_found"}

            data[target_doc_id].update(updates)

            if await aiofiles.os.path.exists(data_path):
                await aiofiles.os.replace(data_path, backup_path)
            await self._write_json_atomic(data_path, data)

            return {"_id": target_doc_id, "result": "updated"}

    async def delete(self, index_name: str, doc_id: str) -> dict[str, str]:
        """Delete a document from the index.

        Args:
            index_name: Name of the index
            doc_id: ID of the document to delete

        Returns:
            Result of the delete operation
        """
        data_path = self._index_path(index_name)
        backup_path = f"{data_path}.bak"

        lock = self._locks.setdefault(index_name, asyncio.Lock())
        async with lock:
            data = await self._read_json_safe(data_path) or {}

            if doc_id not in data:
                return {"_id": doc_id, "result": "not_found"}

            del data[doc_id]

            if await aiofiles.os.path.exists(data_path):
                await aiofiles.os.replace(data_path, backup_path)
            await self._write_json_atomic(data_path, data)

            return {"_id": doc_id, "result": "deleted"}

    async def close(self) -> bool:  # noqa: D401 – nothing to clean
        return True
