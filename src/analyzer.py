"""Gemini API 音频分析"""

import logging
import os
import time

from google import genai
from google.genai import types

log = logging.getLogger(__name__)

# 指数退避重试参数
RETRY_DELAYS = [30, 60, 120]

# 结构化输出 schema
ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "3-5句话的内容摘要",
        },
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "5-10个核心观点或信息点",
        },
        "investment_targets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "标的名称"},
                    "context": {"type": "string", "description": "讨论上下文"},
                },
                "required": ["name", "context"],
            },
            "description": "提到的投资标的",
        },
        "risk_warnings": {
            "type": "array",
            "items": {"type": "string"},
            "description": "风险提示和注意事项",
        },
        "market_outlook": {
            "type": "string",
            "enum": ["bullish", "bearish", "neutral"],
            "description": "市场展望基调",
        },
        "target_audience": {
            "type": "string",
            "description": "适合的目标受众",
        },
    },
    "required": [
        "summary",
        "key_points",
        "investment_targets",
        "risk_warnings",
        "market_outlook",
        "target_audience",
    ],
}


def _get_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("未设置 GEMINI_API_KEY 环境变量")
    return genai.Client(api_key=api_key)


def _upload_and_wait(client, audio_path):
    """上传音频并等待处理完成"""
    log.info("上传音频到 Gemini Files API...")
    uploaded = client.files.upload(file=audio_path)
    log.info("文件已上传: %s, 状态: %s", uploaded.name, uploaded.state)

    # 轮询等待文件处理完成
    while uploaded.state == "PROCESSING":
        log.info("文件处理中，等待 5 秒...")
        time.sleep(5)
        uploaded = client.files.get(name=uploaded.name)

    if uploaded.state != "ACTIVE":
        raise RuntimeError(f"文件处理失败，状态: {uploaded.state}")

    log.info("文件已就绪: %s", uploaded.name)
    return uploaded


def analyze_audio(audio_path, config):
    """分析音频文件

    Args:
        audio_path: 本地音频文件路径
        config: 配置字典

    Returns:
        dict: 分析结果
    """
    client = _get_client()
    model = config["analysis"]["model"]
    prompt = config["prompt"]

    uploaded_file = _upload_and_wait(client, audio_path)

    try:
        return _generate_with_retry(client, model, prompt, uploaded_file)
    finally:
        # 清理上传的文件
        try:
            client.files.delete(name=uploaded_file.name)
            log.info("已删除远程文件: %s", uploaded_file.name)
        except Exception as e:
            log.warning("删除远程文件失败: %s", e)


def _generate_with_retry(client, model, prompt, uploaded_file):
    """带指数退避重试的内容生成"""
    last_error = None
    for attempt, delay in enumerate([0] + RETRY_DELAYS, 1):
        if delay > 0:
            log.warning("等待 %d 秒后重试 (第%d次)...", delay, attempt)
            time.sleep(delay)

        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    types.Content(
                        parts=[
                            types.Part.from_uri(
                                file_uri=uploaded_file.uri,
                                mime_type=uploaded_file.mime_type,
                            ),
                            types.Part.from_text(text=prompt),
                        ],
                    ),
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ANALYSIS_SCHEMA,
                ),
            )

            import json
            result = json.loads(response.text)
            log.info("分析完成，市场展望: %s", result.get("market_outlook"))
            return result

        except Exception as e:
            last_error = e
            log.warning("生成失败 (第%d次): %s", attempt, e)

    raise RuntimeError(f"分析失败，已重试{len(RETRY_DELAYS)}次: {last_error}")
