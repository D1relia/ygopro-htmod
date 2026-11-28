from __future__ import annotations

import argparse
from collections import Counter
import concurrent.futures
import glob
import io
import json
import os
import random
import re
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unicodedata
import zipfile

import requests
from PIL import Image

# ==================== 可按需调整的参数 ====================
CDN_BASE = "https://cdn.233.momobako.com/ygoimg"
CARDS_ZIP_URL = "https://ygocdb.com/api/v0/cards.zip"
CARDS_MD5_URL = "https://ygocdb.com/api/v0/cards.zip.md5"

LANG_CONFIG = {
    "jp": {
        "name": "日文卡图 (OCG)",
        "sources": ["jp"],
        "ypk": "jp_pics.ypk",
        "cache": "_jp_pics_cache",
        "state": "_jp_pics_state.json",
    },
    "sc": {
        "name": "简中卡图 (SC 官图优先 + 最新中文高清兜底)",
        "sources": ["sc", "ygopro"],
        "ypk": "sc_pics.ypk",
        "cache": "_sc_pics_cache",
        "state": "_sc_pics_state.json",
    },
}

MAX_WORKERS = 8          # 并发线程数（配合全局 QPS 限速，4 线程足够跑满）
MAX_QPS = 15.0            # 全局每秒最大请求数（稳妥值 6~10，遇限流会自动降速）
MIN_QPS = 4            # 触发限流后的最低保底速率
CONNECT_TIMEOUT = 10     # 连接超时（秒）
READ_TIMEOUT = 20        # 读取超时（秒）
META_TIMEOUT = 20        # metadata / cards.zip 拉取超时（秒）
RETRY_TIMES = 4          # 单张重试次数
MAX_WIDTH = 400          # 输出 JPG 最大宽度（0 为保留原尺寸）
JPG_QUALITY = 85         # JPG 压缩质量
# ========================================================

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

EXPANSIONS_DIR = os.path.join(BASE_DIR, "expansions")
LOOSE_PICS_DIR = os.path.join(EXPANSIONS_DIR, "pics")
BACKUP_PICS_DIR = os.path.join(EXPANSIONS_DIR, "_htmod_pics_backup")
OVERRIDE_MANIFEST_PATH = os.path.join(EXPANSIONS_DIR, "_htmod_override_manifest.json")
CARDS_MAP_CACHE_PATH = os.path.join(EXPANSIONS_DIR, "_ygocdb_cards_map.json")
OWN_YPK_NAMES = {cfg["ypk"].lower() for cfg in LANG_CONFIG.values()}

_thread_local = threading.local()
_RESAMPLE_LANCZOS = getattr(Image, "Resampling", Image).LANCZOS
_YPK_PIC_RE = re.compile(r"(?:^|/)pics/(\d+)\.(?:jpg|jpeg|png)$", re.IGNORECASE)
_NAME_CLEAN_RE = re.compile(r"[\s·・•‧･\-－—–_“”「」『』\"'：:，,。\.！!？?（）()【】\[\]~～]+")


class AdaptiveRateLimiter:
    """全局 QPS 节流 + 同波去重冷却，避免单次波动把速率瞬间打到底。"""

    def __init__(self, max_qps: float = MAX_QPS, min_qps: float = MIN_QPS):
        self._lock = threading.Lock()
        self._base_interval = 1.0 / max(0.5, max_qps)
        self._max_interval = 1.0 / max(0.2, min_qps)
        self._interval = self._base_interval
        self._next_slot = 0.0
        self._cooldown_until = 0.0
        self._consec_ok = 0
        self._consec_throttle = 0
        self.throttle_hits = 0
        self.stop_event = threading.Event()

    @property
    def current_qps(self) -> float:
        with self._lock:
            return 1.0 / self._interval

    def wait(self) -> bool:
        while not self.stop_event.is_set():
            with self._lock:
                now = time.monotonic()
                if now < self._cooldown_until:
                    sleep_for = self._cooldown_until - now
                elif now < self._next_slot:
                    sleep_for = self._next_slot - now
                else:
                    self._next_slot = now + self._interval
                    return True
            self.stop_event.wait(min(sleep_for, 0.5))
        return False

    def on_success(self) -> None:
        with self._lock:
            self._consec_ok += 1
            self._consec_throttle = 0
            # 连续成功 12 张即加快回速
            if self._consec_ok >= 12 and self._interval > self._base_interval:
                self._interval = max(self._base_interval, self._interval * 0.85)
                self._consec_ok = 0

    def on_throttle(self, retry_after: float | None = None, severe: bool = False) -> None:
        with self._lock:
            now = time.monotonic()
            # 同一波请求已在冷却期内时直接忽略，防止 8 线程连续扣 8 次
            if now < self._cooldown_until:
                return
            self._consec_ok = 0
            self._consec_throttle += 1
            self.throttle_hits += 1
            self._interval = min(self._max_interval, self._interval * (1.35 if severe else 1.15))
            if retry_after and retry_after > 0:
                cool = min(30.0, retry_after + random.uniform(0.3, 1.0))
            else:
                base = min(12.0, (2.5 if severe else 1.2) * (1.4 ** min(self._consec_throttle - 1, 3)))
                cool = base + random.uniform(0.2, 0.8)
            self._cooldown_until = now + cool


def get_session() -> requests.Session:
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=4)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "image/webp,image/*,*/*;q=0.8",
        })
        _thread_local.session = s
    return _thread_local.session


def reset_session() -> requests.Session:
    old = getattr(_thread_local, "session", None)
    if old is not None:
        try:
            old.close()
        except Exception:
            pass
        delattr(_thread_local, "session")
    return get_session()


def _parse_retry_after(header_val: str | None) -> float | None:
    if not header_val:
        return None
    try:
        return max(0.0, float(header_val.strip()))
    except ValueError:
        return None


def normalize_name(name: str) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", name).strip().lower()
    return _NAME_CLEAN_RE.sub("", s)


def read_cdb_file(cdb_path: str) -> tuple[set[int], dict[int, set[str]]]:
    ids: set[int] = set()
    names: dict[int, set[str]] = {}
    conn = None
    try:
        conn = sqlite3.connect(f"file:{cdb_path}?mode=ro", uri=True)
        cur = conn.cursor()
        try:
            cur.execute("SELECT id FROM datas WHERE id > 0")
            for (cid,) in cur.fetchall():
                ids.add(int(cid))
        except sqlite3.Error:
            pass
        try:
            cur.execute("SELECT id, name FROM texts WHERE id > 0")
            for cid, cname in cur.fetchall():
                cid_i = int(cid)
                ids.add(cid_i)
                if cname:
                    names.setdefault(cid_i, set()).add(str(cname))
        except sqlite3.Error:
            pass
    except sqlite3.Error:
        pass
    finally:
        if conn is not None:
            conn.close()
    return ids, names


def merge_name_maps(target: dict[int, set[str]], incoming: dict[int, set[str]]) -> None:
    for cid, cnames in incoming.items():
        target.setdefault(cid, set()).update(cnames)


def collect_ids_from_decks() -> set[int]:
    deck_dir = os.path.join(BASE_DIR, "deck")
    ids: set[int] = set()
    if not os.path.isdir(deck_dir):
        print(f"[提示] 未找到卡组目录: {deck_dir}")
        return ids
    for ydk_path in glob.glob(os.path.join(deck_dir, "**", "*.ydk"), recursive=True):
        try:
            with open(ydk_path, "r", encoding="utf-8-sig", errors="ignore") as f:
                for line in f:
                    s = line.strip()
                    if s.isdigit():
                        cid = int(s)
                        if cid > 0:
                            ids.add(cid)
        except OSError:
            pass
    return ids


def collect_from_local_cdbs() -> tuple[set[int], dict[int, set[str]]]:
    cdb_paths = []
    main_cdb = os.path.join(BASE_DIR, "cards.cdb")
    if os.path.isfile(main_cdb):
        cdb_paths.append(main_cdb)
    if os.path.isdir(EXPANSIONS_DIR):
        cdb_paths.extend(glob.glob(os.path.join(EXPANSIONS_DIR, "*.cdb")))

    ids: set[int] = set()
    names: dict[int, set[str]] = {}
    for path in cdb_paths:
        c_ids, c_names = read_cdb_file(path)
        ids |= c_ids
        merge_name_maps(names, c_names)
    return ids, names


def scan_external_ypks() -> tuple[set[int], set[int], dict[int, set[str]]]:
    cdb_ids: set[int] = set()
    pic_ids: set[int] = set()
    names: dict[int, set[str]] = {}
    if not os.path.isdir(EXPANSIONS_DIR):
        return cdb_ids, pic_ids, names

    archive_paths: list[str] = []
    for pat in (os.path.join(EXPANSIONS_DIR, "*.ypk"), os.path.join(EXPANSIONS_DIR, "*.zip")):
        archive_paths.extend(glob.glob(pat))

    for arch_path in sorted(set(archive_paths)):
        fname = os.path.basename(arch_path).lower()
        if fname in OWN_YPK_NAMES:
            continue
        try:
            with zipfile.ZipFile(arch_path, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    inner_name = info.filename
                    m = _YPK_PIC_RE.search(inner_name)
                    if m:
                        cid = int(m.group(1))
                        if cid > 0:
                            pic_ids.add(cid)
                    elif inner_name.lower().endswith(".cdb"):
                        tmp_path = None
                        try:
                            data = zf.read(info.filename)
                            with tempfile.NamedTemporaryFile(suffix=".cdb", delete=False) as tf:
                                tf.write(data)
                                tmp_path = tf.name
                            c_ids, c_names = read_cdb_file(tmp_path)
                            cdb_ids |= c_ids
                            merge_name_maps(names, c_names)
                        except (OSError, zipfile.BadZipFile):
                            pass
                        finally:
                            if tmp_path and os.path.exists(tmp_path):
                                try:
                                    os.remove(tmp_path)
                                except OSError:
                                    pass
        except (zipfile.BadZipFile, OSError):
            pass

    return cdb_ids, pic_ids, names


def load_json(path: str) -> dict:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_json(path: str, data: dict) -> None:
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp_path, path)


def load_ygocdb_name_map() -> dict[str, list[int]]:
    session = get_session()
    cached = load_json(CARDS_MAP_CACHE_PATH)
    cached_md5 = str(cached.get("md5", "")).strip().lower()
    cached_map = cached.get("map") if isinstance(cached.get("map"), dict) else {}

    remote_md5 = ""
    try:
        resp = session.get(CARDS_MD5_URL, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        if resp.ok:
            remote_md5 = resp.text.strip().strip('"').strip("'").lower()
    except Exception:
        pass

    if cached_map and (not remote_md5 or remote_md5 == cached_md5):
        return cached_map

    print("  - 正在更新百鸽卡名映射库 (cards.zip)，用于桥接超先行 9 位卡密...")
    for attempt in range(RETRY_TIMES):
        try:
            resp = session.get(CARDS_ZIP_URL, timeout=(CONNECT_TIMEOUT, META_TIMEOUT * 2))
            resp.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(resp.content), "r") as zf:
                json_name = next((n for n in zf.namelist() if n.lower().endswith(".json")), None)
                if not json_name:
                    break
                raw_cards = json.loads(zf.read(json_name).decode("utf-8"))

            name_map: dict[str, list[int]] = {}
            name_fields = ("sc_name", "cn_name", "md_name", "nwbbs_n", "cnocg_n", "jp_name")
            if isinstance(raw_cards, dict):
                for item in raw_cards.values():
                    if not isinstance(item, dict):
                        continue
                    raw_id = item.get("id")
                    try:
                        official_id = int(raw_id)
                    except (TypeError, ValueError):
                        continue
                    if official_id <= 0:
                        continue
                    for field in name_fields:
                        val = item.get(field)
                        if not isinstance(val, str) or not val:
                            continue
                        norm = normalize_name(val)
                        if not norm:
                            continue
                        lst = name_map.setdefault(norm, [])
                        if official_id not in lst:
                            lst.append(official_id)

            if name_map:
                save_json(CARDS_MAP_CACHE_PATH, {"md5": remote_md5, "map": name_map})
                print(f"  - 卡名映射库更新完成，共索引 {len(name_map)} 条卡名")
                return name_map
        except Exception:
            if attempt < RETRY_TIMES - 1:
                time.sleep(0.8 * (attempt + 1))

    if cached_map:
        print("  - [提示] cards.zip 拉取失败，继续使用本地缓存映射")
        return cached_map
    print("  - [提示] cards.zip 拉取失败，本次跳过 9 位先行卡名桥接")
    return {}


def fetch_metadata(subdir: str) -> dict[int, str] | None:
    url = f"{CDN_BASE}/{subdir}/metadata"
    session = get_session()
    for attempt in range(RETRY_TIMES):
        try:
            resp = session.get(url, timeout=(CONNECT_TIMEOUT, META_TIMEOUT))
            resp.raise_for_status()
            meta: dict[int, str] = {}
            for raw_line in resp.text.splitlines():
                line = raw_line.strip()
                if not line or ":" not in line:
                    continue
                fname, rest = line.split(":", 1)
                fname = fname.strip().lower()
                if not fname.endswith(".webp"):
                    continue
                stem = fname[:-5]
                if not stem.isdigit():
                    continue
                parts = [p.strip() for p in rest.split(",")]
                sig = parts[2] if len(parts) >= 3 and parts[2] else rest.strip()
                meta[int(stem)] = sig
            if meta:
                return meta
        except Exception:
            if attempt < RETRY_TIMES - 1:
                time.sleep(0.6 * (attempt + 1))
    return None


def switch_active_ypk(lang: str) -> str:
    target_ypk = os.path.join(EXPANSIONS_DIR, LANG_CONFIG[lang]["ypk"])
    target_disabled = target_ypk + ".disabled"

    if not os.path.isfile(target_ypk) and os.path.isfile(target_disabled):
        os.replace(target_disabled, target_ypk)
        print(f"[切换] 已恢复之前下载的 {LANG_CONFIG[lang]['ypk']}")

    for other_lang, cfg in LANG_CONFIG.items():
        if other_lang == lang:
            continue
        other_ypk = os.path.join(EXPANSIONS_DIR, cfg["ypk"])
        if os.path.isfile(other_ypk):
            os.replace(other_ypk, other_ypk + ".disabled")
            print(f"[切换] 已暂时停用 {cfg['ypk']}（改名为 .disabled，保留本地缓存）")

    return target_ypk


def get_existing_ids_in_ypk(ypk_path: str) -> set[int]:
    existing: set[int] = set()
    if not os.path.isfile(ypk_path):
        return existing
    pattern = re.compile(r"^pics/(\d+)\.jpg$", re.IGNORECASE)
    try:
        with zipfile.ZipFile(ypk_path, "r") as zf:
            for name in zf.namelist():
                m = pattern.match(name)
                if m:
                    existing.add(int(m.group(1)))
    except zipfile.BadZipFile:
        backup = ypk_path + ".bak"
        print(f"[警告] 检测到 {ypk_path} 已损坏，已重命名为 {backup} 并重建。")
        os.replace(ypk_path, backup)
    return existing


def get_existing_ids_in_dir(folder: str) -> set[int]:
    existing: set[int] = set()
    if not os.path.isdir(folder):
        return existing
    for fn in os.listdir(folder):
        if fn.lower().endswith(".jpg"):
            stem = fn[:-4]
            if stem.isdigit():
                existing.add(int(stem))
    return existing


def download_and_convert(
    local_cid: int,
    remote_cid: int,
    subdirs: list[str],
    expected_sig: str | None,
    out_dir: str,
    limiter: AdaptiveRateLimiter,
) -> tuple[str, int, str | None, str]:
    out_path = os.path.join(out_dir, f"{local_cid}.jpg")
    session = get_session()
    saw_error = False
    last_err = ""

    for subdir in subdirs:
        url = f"{CDN_BASE}/{subdir}/{remote_cid}.webp"
        for attempt in range(RETRY_TIMES):
            if not limiter.wait():
                return ("aborted", local_cid, None, "已取消")
            try:
                resp = session.get(url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
                code = resp.status_code
                if code == 404:
                    break
                if code in (403, 429) or code >= 500:
                    saw_error = True
                    last_err = f"HTTP {code}"
                    ra = _parse_retry_after(resp.headers.get("Retry-After"))
                    limiter.on_throttle(retry_after=ra, severe=(code in (403, 429)))
                    continue
                resp.raise_for_status()

                ctype = resp.headers.get("Content-Type", "").lower()
                if "text/html" in ctype:
                    saw_error = True
                    last_err = "WAF/HTML拦截页"
                    limiter.on_throttle(severe=True)
                    continue

                with Image.open(io.BytesIO(resp.content)) as img:
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    if MAX_WIDTH > 0 and img.width > MAX_WIDTH:
                        new_h = max(1, int(img.height * (MAX_WIDTH / img.width)))
                        img = img.resize((MAX_WIDTH, new_h), _RESAMPLE_LANCZOS)

                    tmp_path = out_path + ".tmp"
                    img.save(tmp_path, format="JPEG", quality=JPG_QUALITY, optimize=True)
                    os.replace(tmp_path, out_path)

                limiter.on_success()
                return ("ok", local_cid, expected_sig or f"{subdir}:{remote_cid}:direct", "")
            except requests.exceptions.Timeout:
                saw_error = True
                last_err = "请求超时"
                limiter.on_throttle(severe=False)
            except requests.exceptions.RequestException as e:
                saw_error = True
                last_err = type(e).__name__
                limiter.on_throttle(severe=False)
                session = reset_session()
            except Exception as e:
                saw_error = True
                last_err = f"解码异常({type(e).__name__})"
                limiter.on_throttle(severe=False)

    return ("err" if saw_error else "404", local_cid, None, last_err)


def merge_cache_into_ypk(cache_dir: str, ypk_path: str) -> tuple[int, int]:
    if not os.path.isdir(cache_dir):
        return 0, 0
    cached_files = [
        fn for fn in os.listdir(cache_dir)
        if fn.lower().endswith(".jpg") and fn[:-4].isdigit()
    ]
    if not cached_files:
        return 0, 0

    existing_names: set[str] = set()
    if os.path.isfile(ypk_path):
        with zipfile.ZipFile(ypk_path, "r") as zf:
            existing_names = set(zf.namelist())

    overwrite_targets = {f"pics/{fn}" for fn in cached_files if f"pics/{fn}" in existing_names}
    added = len(cached_files) - len(overwrite_targets)
    replaced = len(overwrite_targets)

    if overwrite_targets:
        print(f"\n正在写入 {ypk_path}（新增 {added} 张，升级替换 {replaced} 张，正在无冗余重建压缩包）...")
        tmp_ypk = ypk_path + ".rebuilding"
        with zipfile.ZipFile(ypk_path, "r") as zf_in, zipfile.ZipFile(
            tmp_ypk, "w", compression=zipfile.ZIP_STORED
        ) as zf_out:
            for info in zf_in.infolist():
                if info.filename in overwrite_targets:
                    continue
                zf_out.writestr(info.filename, zf_in.read(info.filename))
            for fn in cached_files:
                zf_out.write(os.path.join(cache_dir, fn), arcname=f"pics/{fn}")
        os.replace(tmp_ypk, ypk_path)
    else:
        print(f"\n正在将 {added} 张新卡图追加写入 {ypk_path} ...")
        with zipfile.ZipFile(ypk_path, "a", compression=zipfile.ZIP_STORED) as zf:
            for fn in cached_files:
                zf.write(os.path.join(cache_dir, fn), arcname=f"pics/{fn}")

    for fn in cached_files:
        try:
            os.remove(os.path.join(cache_dir, fn))
        except OSError:
            pass

    try:
        if not os.listdir(cache_dir):
            os.rmdir(cache_dir)
    except OSError:
        pass
    return added, replaced


def sync_super_pre_overrides(
    ypk_path: str,
    lang: str,
    override_ids: set[int],
) -> tuple[int, int]:
    """
    将外部补丁 / 现有散图 / 9位先行卡的卡图，从当前 ypk 按字节比对强制同步到 expansions/pics/；
    覆写前自动备份原有散图到 _htmod_pics_backup/，清理时优先还原备份。
    """
    manifest = load_json(OVERRIDE_MANIFEST_PATH)
    prev_files = set(manifest.get("files", [])) if isinstance(manifest.get("files"), list) else set()

    ypk_names: set[str] = set()
    if os.path.isfile(ypk_path):
        with zipfile.ZipFile(ypk_path, "r") as zf:
            ypk_names = set(zf.namelist())

    available_override_ids = [cid for cid in sorted(override_ids) if f"pics/{cid}.jpg" in ypk_names]
    desired_names = {f"{cid}.jpg" for cid in available_override_ids}
    to_remove = prev_files - desired_names

    removed = 0
    for fn in to_remove:
        target = os.path.join(LOOSE_PICS_DIR, fn)
        backup = os.path.join(BACKUP_PICS_DIR, fn)
        if os.path.isfile(backup):
            os.makedirs(LOOSE_PICS_DIR, exist_ok=True)
            try:
                os.replace(backup, target)
                removed += 1
            except OSError:
                pass
        elif os.path.isfile(target):
            try:
                os.remove(target)
                removed += 1
            except OSError:
                pass

    written = 0
    active_files: list[str] = []
    if available_override_ids and os.path.isfile(ypk_path):
        os.makedirs(LOOSE_PICS_DIR, exist_ok=True)
        with zipfile.ZipFile(ypk_path, "r") as zf:
            for cid in available_override_ids:
                fn = f"{cid}.jpg"
                arcname = f"pics/{fn}"
                dst = os.path.join(LOOSE_PICS_DIR, fn)
                ypk_bytes = zf.read(arcname)

                need_write = True
                if os.path.isfile(dst) and os.path.getsize(dst) == len(ypk_bytes):
                    try:
                        with open(dst, "rb") as cur_f:
                            if cur_f.read() == ypk_bytes:
                                need_write = False
                    except OSError:
                        need_write = True

                if need_write:
                    # 若原本磁盘已有非本工具写入的散图（如先行服原图），先备份一份以便日后可逆还原
                    if os.path.isfile(dst) and fn not in prev_files:
                        os.makedirs(BACKUP_PICS_DIR, exist_ok=True)
                        bk = os.path.join(BACKUP_PICS_DIR, fn)
                        if not os.path.isfile(bk):
                            try:
                                shutil.copy2(dst, bk)
                            except OSError:
                                pass
                    tmp_dst = dst + ".tmp"
                    with open(tmp_dst, "wb") as out_f:
                        out_f.write(ypk_bytes)
                    os.replace(tmp_dst, dst)
                    written += 1
                active_files.append(fn)

    if active_files:
        save_json(OVERRIDE_MANIFEST_PATH, {"lang": lang, "files": active_files})
    elif os.path.isfile(OVERRIDE_MANIFEST_PATH):
        try:
            os.remove(OVERRIDE_MANIFEST_PATH)
        except OSError:
            pass

    for folder in (LOOSE_PICS_DIR, BACKUP_PICS_DIR):
        if os.path.isdir(folder):
            try:
                if not os.listdir(folder):
                    os.rmdir(folder)
            except OSError:
                pass

    return written, removed


def parse_args():
    parser = argparse.ArgumentParser(description="KoishiPro-HTmod 高清卡图同步工具")
    parser.add_argument("--lang", choices=["jp", "sc"], default=None, help="预设卡图语言：jp(日文) / sc(简中)")
    return parser.parse_args()


def main():
    args = parse_args()

    print("=====================================================")
    print("   KoishiPro-HTmod 高清卡图同步工具 (日文 / 简中 / 先行)")
    print("=====================================================")
    print(f"当前游戏目录: {BASE_DIR}\n")

    if not os.path.isfile(os.path.join(BASE_DIR, "cards.cdb")):
        print("[错误] 当前目录未找到 cards.cdb！")
        print("请将本工具放到萌卡的 ygopro 目录（与 ygopro.exe 同级）后再运行。")
        return

    if args.lang:
        lang = args.lang
        print(f"已选定卡图版本: {LANG_CONFIG[lang]['name']}")
    else:
        print("请选择卡图语言版本：")
        print("  1. 日文卡图 (OCG)")
        print("  2. 简中卡图 (官方简中优先，最新卡包/先行卡自动补齐高清中文图)")
        lang_choice = input("请输入选项 [1/2，默认 1]: ").strip() or "1"
        lang = "sc" if lang_choice == "2" else "jp"

    cfg = LANG_CONFIG[lang]
    sources: list[str] = cfg["sources"]
    cache_dir = os.path.join(EXPANSIONS_DIR, cfg["cache"])
    state_path = os.path.join(EXPANSIONS_DIR, cfg["state"])

    print("\n请选择同步范围：")
    print("  1. 仅同步 deck/ 目录中的全部卡组（极快，推荐先试）")
    print("  2. 同步全卡池（含 cards.cdb 与超先行服补丁，支持断点续传与增量升级）")
    scope = input("请输入选项 [1/2，默认 1]: ").strip() or "1"

    print("\n请选择输出方式：")
    print(f"  1. 打包为 expansions/{cfg['ypk']} + 自动高优先级覆盖先行服卡图（推荐）")
    print("  2. 全部输出到 expansions/pics/ 散图目录")
    out_mode = input("请输入选项 [1/2，默认 1]: ").strip() or "1"

    os.makedirs(EXPANSIONS_DIR, exist_ok=True)
    use_ypk = (out_mode != "2")
    ypk_path = switch_active_ypk(lang) if use_ypk else ""
    work_dir = cache_dir if use_ypk else LOOSE_PICS_DIR
    os.makedirs(work_dir, exist_ok=True)

    print("\n正在扫描本地数据库与扩展补丁...")
    local_cdb_ids, id_to_names = collect_from_local_cdbs()
    ext_cdb_ids, ext_pic_ids, ext_names = scan_external_ypks()
    merge_name_maps(id_to_names, ext_names)

    loose_pic_ids = get_existing_ids_in_dir(LOOSE_PICS_DIR)
    pre_9digit_ids = {cid for cid in (local_cdb_ids | ext_cdb_ids) if cid >= 100000000}

    # 覆盖池涵盖：外部 ypk 卡片、expansions/pics 现有散图、以及所有 9 位先行卡
    ext_override_pool = ext_cdb_ids | ext_pic_ids | loose_pic_ids | pre_9digit_ids
    if ext_override_pool:
        print(
            f"检测到需高优先级覆盖的补丁/散图/先行卡: {len(ext_override_pool)} 张"
            f"（其中 9 位先行卡 {len(pre_9digit_ids)} 张，现有散图 {len(loose_pic_ids)} 张）"
        )

    if scope == "1":
        target_ids = collect_ids_from_decks()
    else:
        target_ids = local_cdb_ids | ext_cdb_ids | pre_9digit_ids

    if not target_ids:
        print("\n[提示] 未读取到任何卡片 ID，已退出。")
        return

    print("正在从百鸽拉取卡图索引 (metadata)...")
    metas: dict[str, dict[int, str] | None] = {}
    all_meta_ok = True
    for src in sources:
        m = fetch_metadata(src)
        metas[src] = m
        if m is None:
            all_meta_ok = False
            print(f"  - [{src}] 索引获取失败，将降级为直接尝试下载模式")
        else:
            print(f"  - [{src}] 已加载 {len(m)} 条卡图索引")

    def find_in_metas(check_id: int) -> tuple[str | None, str | None]:
        for src in sources:
            src_meta = metas.get(src)
            if src_meta and check_id in src_meta:
                return src, src_meta[check_id]
        return None, None

    # 所有 9 位先行卡无条件优先通过卡名桥接 8 位正式卡密；其他外部补丁卡查不到时也桥接
    need_bridge_cids = [
        cid for cid in target_ids
        if cid in id_to_names and (
            cid >= 100000000
            or (cid in ext_override_pool and (not all_meta_ok or find_in_metas(cid)[0] is None))
        )
    ]

    bridged_map: dict[int, int] = {}
    if need_bridge_cids:
        ygocdb_name_map = load_ygocdb_name_map()
        if ygocdb_name_map:
            for local_cid in sorted(need_bridge_cids):
                matched_remote = None
                for raw_name in id_to_names.get(local_cid, ()):
                    norm = normalize_name(raw_name)
                    cand_ids = ygocdb_name_map.get(norm)
                    if not cand_ids:
                        continue
                    # 优先选择正式 8 位卡密（< 100000000）
                    ordered_cands = sorted(cand_ids, key=lambda x: (x >= 100000000, x))
                    if all_meta_ok:
                        for cand in ordered_cands:
                            if find_in_metas(cand)[0] is not None:
                                matched_remote = cand
                                break
                    if matched_remote is None:
                        matched_remote = ordered_cands[0]
                    if matched_remote is not None:
                        break
                if matched_remote is not None and matched_remote != local_cid:
                    bridged_map[local_cid] = matched_remote

            if bridged_map:
                print(f"  - 已通过卡名自动桥接先行卡密 -> 正式卡密: {len(bridged_map)} 张")
                for sample_local in list(bridged_map.keys())[:8]:
                    sample_remote = bridged_map[sample_local]
                    sample_name = next(iter(id_to_names.get(sample_local, ("?",))))
                    src_hit, _ = find_in_metas(sample_remote)
                    print(f"      · {sample_local} ({sample_name}) -> {sample_remote} [{src_hit or 'direct'}]")

    local_state: dict[str, str] = load_json(state_path)
    state_dirty = False

    existing_ids = get_existing_ids_in_dir(work_dir)
    if use_ypk:
        existing_ids |= get_existing_ids_in_ypk(ypk_path)

    tasks: list[tuple[int, int, list[str], str | None, bool]] = []
    skipped_no_art = 0
    skipped_uptodate = 0
    upgrade_cnt = 0

    for local_cid in sorted(target_ids):
        cid_key = str(local_cid)
        remote_cid = bridged_map.get(local_cid, local_cid)

        if all_meta_ok:
            chosen_src, raw_md5 = find_in_metas(remote_cid)
            if chosen_src is None or raw_md5 is None:
                # 若桥接后的 ID 无图，再回退检查本地原 ID
                if remote_cid != local_cid:
                    remote_cid = local_cid
                    chosen_src, raw_md5 = find_in_metas(local_cid)
                if chosen_src is None or raw_md5 is None:
                    skipped_no_art += 1
                    continue

            if remote_cid == local_cid:
                chosen_sig = f"{chosen_src}:{raw_md5}"
            else:
                chosen_sig = f"{chosen_src}:{remote_cid}:{raw_md5}"

            if local_cid in existing_ids:
                saved_sig = local_state.get(cid_key)
                # 仅普通 8 位正式老卡在缺少 state 时回填跳过；9 位先行卡或桥接卡必须核验签名并升级覆写
                if saved_sig is None and remote_cid == local_cid and local_cid < 100000000:
                    local_state[cid_key] = chosen_sig
                    state_dirty = True
                    skipped_uptodate += 1
                    continue
                if saved_sig == chosen_sig:
                    skipped_uptodate += 1
                    continue
                tasks.append((local_cid, remote_cid, [chosen_src], chosen_sig, True))
                upgrade_cnt += 1
            else:
                tasks.append((local_cid, remote_cid, [chosen_src], chosen_sig, False))
        else:
            if local_cid in existing_ids and remote_cid == local_cid and local_cid < 100000000:
                skipped_uptodate += 1
                continue
            tasks.append((local_cid, remote_cid, sources, None, local_cid in existing_ids))

    new_cnt = len(tasks) - upgrade_cnt
    print(
        f"\n[{cfg['name']}] 目标: {len(target_ids)} | 已最新跳过: {skipped_uptodate} | "
        f"图库暂无: {skipped_no_art} | 待新下: {new_cnt} | 待升级替换: {upgrade_cnt}"
    )

    err_cnt = 0
    err_reasons: Counter[str] = Counter()
    if tasks:
        print("开始下载并转码为 JPG（已启用全局 QPS 限速与撞墙冷却，按 Ctrl+C 可安全暂停并保存进度）...\n")
        pending = tasks
        interrupted = False

        # 第 1 轮正常限速拉取；若有失败，冷却后自动降为 2 线程低速补漏一轮
        rounds = [
            ("第 1 轮同步", MAX_WORKERS, MAX_QPS, MIN_QPS),
            ("第 2 轮低速补漏", 2, 3.0, 1.0),
        ]
        for r_idx, (r_label, workers, r_max_qps, r_min_qps) in enumerate(rounds):
            if not pending or interrupted:
                break
            if r_idx > 0:
                print(f"\n[自动补漏] 等待 8 秒冷却后，对失败的 {len(pending)} 张进行低速重试...")
                try:
                    time.sleep(8)
                except KeyboardInterrupt:
                    interrupted = True
                    break

            limiter = AdaptiveRateLimiter(max_qps=r_max_qps, min_qps=r_min_qps)
            ok_cnt = notfound_cnt = round_err = done_cnt = 0
            failed_next: list[tuple[int, int, list[str], str | None, bool]] = []
            task_by_cid = {t[0]: t for t in pending}
            total = len(pending)
            start_ts = time.time()
            round_reasons: Counter[str] = Counter()

            executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
            futures = [
                executor.submit(download_and_convert, local_cid, remote_cid, subdirs, sig, work_dir, limiter)
                for local_cid, remote_cid, subdirs, sig, _ in pending
            ]
            try:
                for fut in concurrent.futures.as_completed(futures):
                    res, local_cid, sig, reason = fut.result()
                    if res == "aborted":
                        continue
                    done_cnt += 1
                    if res == "ok":
                        ok_cnt += 1
                        if sig:
                            local_state[str(local_cid)] = sig
                            state_dirty = True
                    elif res == "404":
                        notfound_cnt += 1
                    else:
                        round_err += 1
                        round_reasons[reason or "未知错误"] += 1
                        failed_next.append(task_by_cid[local_cid])

                    # 每完成 200 张定期落盘，防止直接关窗口丢失状态
                    if state_dirty and done_cnt % 200 == 0:
                        save_json(state_path, local_state)
                        state_dirty = False

                    elapsed = max(0.1, time.time() - start_ts)
                    speed = done_cnt / elapsed
                    top_err = f" | 主因:{round_reasons.most_common(1)[0][0]}" if round_reasons else ""
                    print(
                        f"\r[{r_label}] {done_cnt}/{total} ({done_cnt * 100 / total:.1f}%) | "
                        f"成功: {ok_cnt} | 无图: {notfound_cnt} | 失败: {round_err} | "
                        f"{speed:.1f} 张/秒 (上限:{limiter.current_qps:.1f} 退避:{limiter.throttle_hits}){top_err}   ",
                        end="",
                        flush=True,
                    )
            except KeyboardInterrupt:
                interrupted = True
                limiter.stop_event.set()
                print("\n\n[已中断] 正在等待当前线程收尾并保存已下载的卡图...")
                executor.shutdown(wait=True, cancel_futures=True)
            else:
                executor.shutdown(wait=True)
            print()

            pending = failed_next
            err_cnt = round_err
            err_reasons = round_reasons

        if err_reasons:
            detail = ", ".join(f"{k}×{v}" for k, v in err_reasons.most_common(5))
            print(f"[失败原因统计] {detail}")
    else:
        print("所有可用卡图均已是最新版本，无需下载。")

    if use_ypk:
        added, replaced = merge_cache_into_ypk(cache_dir, ypk_path)
        if added or replaced:
            print(f"写入完成！新增 {added} 张，升级替换 {replaced} 张 -> {ypk_path}")

        written, removed = sync_super_pre_overrides(ypk_path, lang, ext_override_pool)
        if written or removed:
            print(f"[先行服高优先级覆盖] 已强制同步 {written} 张，清理/还原 {removed} 张 -> expansions/pics/")
    else:
        if tasks:
            print(f"同步完成！卡图已保存至: {LOOSE_PICS_DIR}")

    if state_dirty:
        save_json(state_path, local_state)

    if err_cnt > 0:
        print(f"[提示] 有 {err_cnt} 张因网络波动下载失败，重新运行即可自动补齐。")


if __name__ == "__main__":
    try:
        main()
    finally:
        input("\n处理结束，按回车键退出...")
