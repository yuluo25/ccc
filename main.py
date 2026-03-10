#!/usr/bin/env python3
"""小宇宙播客 AI 分析工具 - 入口"""

import argparse
import logging
import sys

import yaml

from src.fetcher import fetch_episodes, download_audio
from src.store import load_processed_eids, save_episode
from src.analyzer import analyze_audio
from src.site_builder import build_site

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def load_config(path="config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_full(config):
    """完整流程：获取 → 去重 → 分析 → 建站"""
    episodes = fetch_episodes(config)
    if not episodes:
        log.info("未获取到任何剧集")
        return

    processed = load_processed_eids()
    new_episodes = [ep for ep in episodes if ep["eid"] not in processed]

    if not new_episodes:
        log.info("没有新剧集需要处理")
        build_site(config)
        return

    max_per_run = config["analysis"]["max_episodes_per_run"]
    to_process = new_episodes[:max_per_run]
    log.info("发现 %d 个新剧集，本次处理 %d 个", len(new_episodes), len(to_process))

    for ep in to_process:
        try:
            log.info("处理: %s - %s", ep["eid"], ep["title"])
            audio_path = download_audio(ep["audio_url"], ep["eid"])
            try:
                result = analyze_audio(audio_path, config)
                save_episode(ep, result)
                log.info("完成: %s", ep["title"])
            finally:
                import os
                if audio_path and os.path.exists(audio_path):
                    os.remove(audio_path)
                    log.info("已清理临时音频文件")
        except Exception:
            log.exception("处理失败: %s", ep["title"])

    build_site(config)
    log.info("全部完成")


def run_fetch_only(config):
    """仅获取剧集列表，不分析"""
    episodes = fetch_episodes(config)
    if not episodes:
        log.info("未获取到任何剧集")
        return
    processed = load_processed_eids()
    for ep in episodes:
        status = "已处理" if ep["eid"] in processed else "新"
        log.info("[%s] %s - %s (%ds)", status, ep["eid"], ep["title"], ep["duration"])


def run_single_episode(config, eid):
    """分析指定的一期"""
    episodes = fetch_episodes(config)
    target = None
    for ep in episodes:
        if ep["eid"] == eid:
            target = ep
            break

    if not target:
        log.error("未找到 eid=%s 的剧集", eid)
        sys.exit(1)

    log.info("处理: %s - %s", target["eid"], target["title"])
    audio_path = download_audio(target["audio_url"], target["eid"])
    try:
        result = analyze_audio(audio_path, config)
        save_episode(target, result)
        log.info("完成: %s", target["title"])
    finally:
        import os
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)

    build_site(config)


def main():
    parser = argparse.ArgumentParser(description="小宇宙播客 AI 分析工具")
    parser.add_argument("--fetch-only", action="store_true", help="仅获取剧集列表，不分析")
    parser.add_argument("--build-site-only", action="store_true", help="仅重建静态站点")
    parser.add_argument("--episode", type=str, help="分析指定的一期 (eid)")
    parser.add_argument("--config", type=str, default="config.yaml", help="配置文件路径")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.build_site_only:
        log.info("仅重建站点")
        build_site(config)
    elif args.fetch_only:
        log.info("仅获取剧集列表")
        run_fetch_only(config)
    elif args.episode:
        run_single_episode(config, args.episode)
    else:
        run_full(config)


if __name__ == "__main__":
    main()
