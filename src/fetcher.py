"""获取小宇宙播客数据 + 下载音频"""

import json
import logging
import os
import tempfile
import time

import requests
from bs4 import BeautifulSoup

from src.store import load_fetch_cache, save_fetch_cache

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒


def _request_with_retry(url, retries=MAX_RETRIES, delay=RETRY_DELAY, headers=None):
    """带重试的 HTTP GET"""
    req_headers = headers or HEADERS
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=req_headers, timeout=30)
            if resp.status_code == 304:
                return resp
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            log.warning("请求失败 (第%d次): %s - %s", attempt, url, e)
            if attempt < retries:
                time.sleep(delay)
            else:
                raise


def fetch_episodes(config):
    """从小宇宙播客页面获取剧集列表

    使用 ETag / Last-Modified 缓存，304 时直接复用上次结果。

    返回:
        list[dict]: 每个元素包含 eid, title, audio_url, pub_date, duration, description
    """
    podcast_id = config["podcast"]["id"]
    url = f"https://www.xiaoyuzhoufm.com/podcast/{podcast_id}"
    min_duration = config["analysis"]["min_duration_seconds"]

    # ---------- 带缓存头的请求 ----------
    cache = load_fetch_cache() or {}
    req_headers = dict(HEADERS)
    if cache.get("etag"):
        req_headers["If-None-Match"] = cache["etag"]
    if cache.get("last_modified"):
        req_headers["If-Modified-Since"] = cache["last_modified"]

    log.info("获取播客页面: %s", url)
    resp = _request_with_retry(url, headers=req_headers)

    if resp.status_code == 304:
        log.info("页面未更新，使用缓存 (%d 个剧集)", len(cache.get("episodes", [])))
        return cache.get("episodes", [])

    # ---------- 正常解析 ----------
    resp.encoding = "utf-8"
    episodes = _parse_episodes(resp.text, min_duration)

    # 更新缓存
    new_cache = {
        "etag": resp.headers.get("ETag", ""),
        "last_modified": resp.headers.get("Last-Modified", ""),
        "episodes": episodes,
    }
    save_fetch_cache(new_cache)

    return episodes


def _parse_episodes(html, min_duration):
    """从 HTML 中解析剧集列表"""
    soup = BeautifulSoup(html, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag:
        log.error("未找到 __NEXT_DATA__ 脚本标签")
        return []

    try:
        next_data = json.loads(script_tag.string)
    except json.JSONDecodeError:
        log.error("解析 __NEXT_DATA__ JSON 失败")
        return []

    try:
        page_props = next_data["props"]["pageProps"]
    except KeyError:
        log.error("__NEXT_DATA__ 结构异常，找不到 props.pageProps")
        return []

    episodes_raw = (
        page_props.get("episodes")
        or page_props.get("episodeList")
        or page_props.get("podcast", {}).get("episodes")
        or []
    )

    if not episodes_raw:
        log.warning("未在页面数据中找到剧集列表")
        return []

    episodes = []
    for ep in episodes_raw:
        eid = ep.get("eid") or ep.get("id", "")
        title = ep.get("title", "未知标题")
        duration = ep.get("duration", 0)

        audio_url = ""
        enclosure = ep.get("enclosure")
        if isinstance(enclosure, dict):
            audio_url = enclosure.get("url", "")
        elif isinstance(enclosure, str):
            audio_url = enclosure
        if not audio_url:
            audio_url = ep.get("mediaKey", "")
            if audio_url and not audio_url.startswith("http"):
                audio_url = f"https://media.xyzcdn.net/{audio_url}"

        pub_date = ep.get("pubDate") or ep.get("publishedAt", "")
        description = ep.get("description") or ep.get("shownotes", "")

        if not eid or not audio_url:
            log.warning("跳过缺少 eid 或音频URL 的剧集: %s", title)
            continue

        if duration < min_duration:
            log.info("跳过短剧集 (%ds < %ds): %s", duration, min_duration, title)
            continue

        episodes.append({
            "eid": eid,
            "title": title,
            "audio_url": audio_url,
            "pub_date": pub_date,
            "duration": duration,
            "description": description[:500] if description else "",
        })

    log.info("共获取 %d 个有效剧集", len(episodes))
    return episodes


def download_audio(audio_url, eid):
    """下载音频到临时文件

    返回:
        str: 临时文件路径
    """
    log.info("下载音频: %s", audio_url)
    resp = _request_with_retry(audio_url)

    suffix = ".m4a"
    if ".mp3" in audio_url:
        suffix = ".mp3"

    tmp_dir = tempfile.gettempdir()
    audio_path = os.path.join(tmp_dir, f"podcast_{eid}{suffix}")

    with open(audio_path, "wb") as f:
        f.write(resp.content)

    size_mb = len(resp.content) / (1024 * 1024)
    log.info("音频已下载: %.1f MB -> %s", size_mb, audio_path)
    return audio_path
