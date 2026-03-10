"""JSON 数据读写 + 去重"""

import json
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(_PROJECT_ROOT, "data", "episodes")
FETCH_CACHE_PATH = os.path.join(_PROJECT_ROOT, "data", ".fetch_cache.json")


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_processed_eids():
    """扫描已处理的剧集 eid 集合"""
    _ensure_dir()
    eids = set()
    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".json"):
            eids.add(filename[:-5])  # 去掉 .json 后缀
    log.info("已有 %d 个已处理剧集", len(eids))
    return eids


def save_episode(episode_meta, analysis_result):
    """保存单集分析结果

    Args:
        episode_meta: 包含 eid, title, audio_url, pub_date, duration, description
        analysis_result: Gemini 返回的分析结果 dict
    """
    _ensure_dir()
    eid = episode_meta["eid"]
    data = {
        "eid": eid,
        "title": episode_meta["title"],
        "audio_url": episode_meta["audio_url"],
        "pub_date": episode_meta["pub_date"],
        "duration": episode_meta["duration"],
        "description": episode_meta.get("description", ""),
        "analysis": analysis_result,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }
    filepath = os.path.join(DATA_DIR, f"{eid}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info("已保存: %s", filepath)


def load_all_episodes():
    """加载所有已分析的剧集，按发布日期倒序排列"""
    _ensure_dir()
    episodes = []
    for filename in os.listdir(DATA_DIR):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(DATA_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            episodes.append(data)
        except (json.JSONDecodeError, OSError) as e:
            log.warning("读取失败: %s - %s", filepath, e)

    episodes.sort(key=lambda x: x.get("pub_date", ""), reverse=True)
    return episodes


def load_episode(eid):
    """加载单集数据"""
    filepath = os.path.join(DATA_DIR, f"{eid}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def load_fetch_cache():
    """读取 HTTP 缓存（ETag / Last-Modified / 剧集列表）"""
    if not os.path.exists(FETCH_CACHE_PATH):
        return None
    try:
        with open(FETCH_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("读取缓存失败: %s", e)
        return None


def save_fetch_cache(cache):
    """写入 HTTP 缓存"""
    os.makedirs(os.path.dirname(FETCH_CACHE_PATH), exist_ok=True)
    with open(FETCH_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
