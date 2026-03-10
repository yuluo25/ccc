"""生成静态 HTML 站点"""

import logging
import os
from datetime import datetime, timezone, timedelta

from jinja2 import Environment, FileSystemLoader

from src.store import load_all_episodes

log = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")


CST = timezone(timedelta(hours=8))


def _format_datetime(value):
    """Jinja2 filter: ISO 8601 → 'MM-DD HH:MM'（北京时间）"""
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is not None:
            dt = dt.astimezone(CST)
        return dt.strftime("%m-%d %H:%M")
    except (ValueError, TypeError):
        return value[:10] if len(value) >= 10 else value


def build_site(config):
    """读取所有已分析的剧集，渲染静态 HTML 到 docs/ 目录"""
    episodes = load_all_episodes()
    log.info("加载 %d 个剧集用于建站", len(episodes))

    site_config = config.get("site", {})
    site_title = site_config.get("title", "播客分析")
    site_description = site_config.get("description", "")
    base_url = site_config.get("base_url", "")

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
    )
    env.filters["format_datetime"] = _format_datetime

    # 确保输出目录存在
    episodes_dir = os.path.join(DOCS_DIR, "episodes")
    os.makedirs(episodes_dir, exist_ok=True)

    # 渲染列表页
    index_tmpl = env.get_template("index.html")
    index_html = index_tmpl.render(
        site_title=site_title,
        site_description=site_description,
        base_url=base_url,
        episodes=episodes,
    )
    index_path = os.path.join(DOCS_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)
    log.info("已生成列表页: %s", index_path)

    # 渲染详情页
    episode_tmpl = env.get_template("episode.html")
    for ep in episodes:
        ep_html = episode_tmpl.render(
            site_title=site_title,
            base_url=base_url,
            ep=ep,
        )
        ep_path = os.path.join(episodes_dir, f"{ep['eid']}.html")
        with open(ep_path, "w", encoding="utf-8") as f:
            f.write(ep_html)

    log.info("已生成 %d 个详情页", len(episodes))
