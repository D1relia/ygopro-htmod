import concurrent.futures
import glob
import io
import os
import re
import sqlite3
import sys
import threading
import time
import zipfile

import requests
from PIL import Image

# ==================== 可按需调整的参数 ====================
CDN_URL = "https://cdn.233.momobako.com/ygoimg/jp/{cid}.webp"
MAX_WORKERS = 6          # 并发线程数（不建议超过 8，避免给图床造成压力）
TIMEOUT = 12             # 单张下载超时（秒）
RETRY_TIMES = 3          # 失败重试次数
MAX_WIDTH = 400          # 输出 JPG 最大宽度（设为 0 则保留原图尺寸）
JPG_QUALITY = 85         # JPG 压缩质量（80-90 兼顾清晰度与体积）
# ========================================================

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

EXPANSIONS_DIR = os.path.join(BASE_DIR, "expansions")
YPK_PATH = os.path.join(EXPANSIONS_DIR, "jp_pics.ypk")
CACHE_DIR = os.path.join(EXPANSIONS_DIR, "_jp_pics_cache")
LOOSE_PICS_DIR = os.path.join(EXPANSIONS_DIR, "pics")

_thread_local = threading.local()
_RESAMPLE_LANCZOS = getattr(Image, "Resampling", Image).LANCZOS


def get_session() -> requests.Session:
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KoishiPro-HTmod/1.0",
            "Accept": "image/webp,image/*,*/*;q=0.8",
        })
        _thread_local.session = s
    return _thread_local.session


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


def collect_ids_from_cdbs() -> set[int]:
    cdb_paths = []
    main_cdb = os.path.join(BASE_DIR, "cards.cdb")
    if os.path.isfile(main_cdb):
        cdb_paths.append(main_cdb)
    if os.path.isdir(EXPANSIONS_DIR):
        cdb_paths.extend(glob.glob(os.path.join(EXPANSIONS_DIR, "*.cdb")))

    ids: set[int] = set()
    for path in cdb_paths:
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT id FROM datas WHERE id > 0")
            for (cid,) in cur.fetchall():
                ids.add(int(cid))
            conn.close()
        except sqlite3.Error:
            pass
    return ids


def get_existing_ids_in_ypk() -> set[int]:
    existing: set[int] = set()
    if not os.path.isfile(YPK_PATH):
        return existing
    pattern = re.compile(r"^pics/(\d+)\.jpg$", re.IGNORECASE)
    try:
        with zipfile.ZipFile(YPK_PATH, "r") as zf:
            for name in zf.namelist():
                m = pattern.match(name)
                if m:
                    existing.add(int(m.group(1)))
    except zipfile.BadZipFile:
        backup = YPK_PATH + ".bak"
        print(f"[警告] 检测到 {YPK_PATH} 已损坏，已重命名为 {backup} 并重建。")
        if os.path.exists(backup):
            os.remove(backup)
        os.rename(YPK_PATH, backup)
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


def download_and_convert(cid: int, out_dir: str) -> str:
    """返回值: 'ok' | '404' | 'err'"""
    out_path = os.path.join(out_dir, f"{cid}.jpg")
    if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
        return "ok"

    session = get_session()
    url = CDN_URL.format(cid=cid)

    for attempt in range(RETRY_TIMES):
        try:
            resp = session.get(url, timeout=TIMEOUT)
            if resp.status_code == 404:
                return "404"
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(0.8 * (attempt + 1))
                continue
            resp.raise_for_status()

            with Image.open(io.BytesIO(resp.content)) as img:
                if img.mode != "RGB":
                    img = img.convert("RGB")
                if MAX_WIDTH > 0 and img.width > MAX_WIDTH:
                    new_h = max(1, int(img.height * (MAX_WIDTH / img.width)))
                    img = img.resize((MAX_WIDTH, new_h), _RESAMPLE_LANCZOS)

                tmp_path = out_path + ".tmp"
                img.save(tmp_path, format="JPEG", quality=JPG_QUALITY, optimize=True)
                os.replace(tmp_path, out_path)
            return "ok"
        except Exception:
            if attempt < RETRY_TIMES - 1:
                time.sleep(0.5 * (attempt + 1))
    return "err"


def merge_cache_into_ypk() -> int:
    if not os.path.isdir(CACHE_DIR):
        return 0
    cached_files = [
        fn for fn in os.listdir(CACHE_DIR)
        if fn.lower().endswith(".jpg") and fn[:-4].isdigit()
    ]
    if not cached_files:
        return 0

    existing_names: set[str] = set()
    if os.path.isfile(YPK_PATH):
        with zipfile.ZipFile(YPK_PATH, "r") as zf:
            existing_names = set(zf.namelist())

    added = 0
    print(f"\n正在将 {len(cached_files)} 张日文卡图写入 {YPK_PATH} ...")
    with zipfile.ZipFile(YPK_PATH, "a", compression=zipfile.ZIP_STORED) as zf:
        for fn in cached_files:
            arcname = f"pics/{fn}"
            src_path = os.path.join(CACHE_DIR, fn)
            if arcname not in existing_names:
                zf.write(src_path, arcname=arcname)
                existing_names.add(arcname)
                added += 1
            try:
                os.remove(src_path)
            except OSError:
                pass

    try:
        if not os.listdir(CACHE_DIR):
            os.rmdir(CACHE_DIR)
    except OSError:
        pass
    return added


def main():
    print("==============================================")
    print("   KoishiPro-HTmod 日文卡图同步工具 (方案 B)")
    print("==============================================")
    print(f"当前游戏目录: {BASE_DIR}\n")

    if not os.path.isfile(os.path.join(BASE_DIR, "cards.cdb")):
        print("[错误] 当前目录未找到 cards.cdb！")
        print("请将本工具放到萌卡的 ygopro 目录（与 ygopro.exe 同级）后再运行。")
        return

    print("请选择同步范围：")
    print("  1. 仅同步 deck/ 目录中的全部卡组（极快，推荐先试）")
    print("  2. 同步 cards.cdb 全卡池（约 13000+ 张，支持断点续传）")
    scope = input("请输入选项 [1/2，默认 1]: ").strip() or "1"

    print("\n请选择输出方式：")
    print("  1. 打包为单个 expansions/jp_pics.ypk（推荐：方便管理、分享与卸载）")
    print("  2. 直接输出到 expansions/pics/ 散图目录（加载优先级最高）")
    out_mode = input("请输入选项 [1/2，默认 1]: ").strip() or "1"

    os.makedirs(EXPANSIONS_DIR, exist_ok=True)
    use_ypk = (out_mode != "2")
    work_dir = CACHE_DIR if use_ypk else LOOSE_PICS_DIR
    os.makedirs(work_dir, exist_ok=True)

    target_ids = collect_ids_from_decks() if scope == "1" else collect_ids_from_cdbs()
    if not target_ids:
        print("\n[提示] 未读取到任何卡片 ID，已退出。")
        return

    existing_ids = get_existing_ids_in_dir(work_dir)
    if use_ypk:
        existing_ids |= get_existing_ids_in_ypk()

    todo_ids = sorted(target_ids - existing_ids)
    print(f"\n目标卡片总数: {len(target_ids)} | 已存在跳过: {len(target_ids) - len(todo_ids)} | 待下载: {len(todo_ids)}")

    if not todo_ids:
        if use_ypk:
            added = merge_cache_into_ypk()
            if added:
                print(f"已补写 {added} 张缓存卡图到 jp_pics.ypk。")
        print("全部目标日文卡图已是最新，无需下载！")
        return

    ok_cnt = notfound_cnt = err_cnt = done_cnt = 0
    total = len(todo_ids)
    start_ts = time.time()
    print("开始下载并转码为 JPG（可随时按 Ctrl+C 安全暂停并保存进度）...\n")

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)
    futures = [executor.submit(download_and_convert, cid, work_dir) for cid in todo_ids]
    try:
        for fut in concurrent.futures.as_completed(futures):
            res = fut.result()
            done_cnt += 1
            if res == "ok":
                ok_cnt += 1
            elif res == "404":
                notfound_cnt += 1
            else:
                err_cnt += 1
            elapsed = max(0.1, time.time() - start_ts)
            speed = done_cnt / elapsed
            print(
                f"\r进度: {done_cnt}/{total} ({done_cnt * 100 / total:.1f}%) | "
                f"成功: {ok_cnt} | 无日文图: {notfound_cnt} | 失败: {err_cnt} | "
                f"{speed:.1f} 张/秒   ",
                end="",
                flush=True,
            )
    except KeyboardInterrupt:
        print("\n\n[已中断] 正在等待当前下载线程收尾并保存已完成的卡图...")
        executor.shutdown(wait=True, cancel_futures=True)
    else:
        executor.shutdown(wait=True)

    print()
    if use_ypk:
        added = merge_cache_into_ypk()
        print(f"写入完成！本次新增打包 {added} 张，输出路径: {YPK_PATH}")
    else:
        print(f"同步完成！日文卡图已保存至: {LOOSE_PICS_DIR}")

    if err_cnt > 0:
        print(f"[提示] 有 {err_cnt} 张因网络波动下载失败，重新运行一次脚本即可自动补齐。")


if __name__ == "__main__":
    try:
        main()
    finally:
        input("\n处理结束，按回车键退出...")