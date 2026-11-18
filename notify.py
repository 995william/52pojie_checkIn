# -*- coding: utf-8 -*-
"""
推送通知模块（精简版）
仅保留：
1. 企业微信群机器人 (WECOM_WEBHOOK)
2. PushPlus (PUSHPLUS_TOKEN)
3. GitHub Actions Job Summary 渲染
支持 HUB_MANAGED_NOTIFY 集中管控托管静默策略。
"""

import logging
import os
import requests

logger = logging.getLogger("Notify")

DEFAULT_WECOM_WEBHOOK = ""


def send_wecom(webhook: str, title: str, content: str):
    """企业微信群机器人推送 (严格遵循 msgtype: text 纯文本格式)."""
    if content.strip().startswith("🔔") or content.strip().startswith("【"):
        text_content = content.strip()
    else:
        text_content = (
            f"【{title}】\n"
            f"────────────\n"
            f"{content}\n"
            f"────────────"
        )
    payload = {
        "msgtype": "text",
        "text": {
            "content": text_content
        }
    }

    try:
        r = requests.post(webhook, json=payload, timeout=10)
        logger.info(f"企业微信 推送响应: {r.text}")
    except Exception as e:
        logger.error(f"企业微信 推送异常: {e}")


def send_pushplus(token: str, title: str, content: str):
    """PushPlus 微信模板消息推送."""
    url = "https://www.pushplus.plus/send"
    data = {
        "token": token,
        "title": title,
        "content": content.replace("\n", "<br>"),
        "template": "html"
    }
    try:
        r = requests.post(url, json=data, timeout=10)
        logger.info(f"PushPlus 推送响应: {r.text}")
    except Exception as e:
        logger.error(f"PushPlus 推送异常: {e}")


def write_github_summary(title: str, content: str):
    """在 GitHub Actions 环境中生成 Job Summary 报告."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file and os.path.exists(os.path.dirname(summary_file)):
        try:
            markdown = f"## {title}\n\n```text\n{content}\n```\n"
            with open(summary_file, "a", encoding="utf-8") as f:
                f.write(markdown)
        except Exception as e:
            logger.debug(f"写入 GITHUB_STEP_SUMMARY 失败: {e}")


def send(title: str, content: str, public_content: str = None, skip_push: bool = False):
    """
    统一通知分发入口.
    :param title: 通知标题
    :param content: 推送到私密渠道（企微/PushPlus）的完整内容
    :param public_content: 写入 GitHub Actions 公开 Summary 与控制台日志的脱敏内容
    :param skip_push: 为 True 时仅写入 GitHub Job Summary，跳过外部企微/PushPlus 推送
    """
    summary_text = public_content if public_content is not None else content

    # 1. 写入 Actions 公开 Summary（已脱敏）
    write_github_summary(title, summary_text)

    if skip_push:
        logger.info("当前由管控中枢托管通知 (HUB_MANAGED_NOTIFY=true)，全部账号正常，跳过单仓直推（交由中枢汇总早报）。")
        return

    # 2. 控制台日志
    logger.info(f"--- 准备向私有渠道分发推送通知 [{title}] ---")

    pushed = False

    # 3. 企业微信机器人 (私有渠道，推送完整内容)
    wecom_webhook = os.environ.get("WECOM_WEBHOOK") or DEFAULT_WECOM_WEBHOOK
    if wecom_webhook:
        send_wecom(wecom_webhook, title, content)
        pushed = True

    # 4. PushPlus 推送 (私有渠道，推送完整内容)
    pushplus_token = os.environ.get("PUSHPLUS_TOKEN")
    if pushplus_token:
        send_pushplus(pushplus_token, title, content)
        pushed = True

    if not pushed:
        logger.info("未配置任何外部推送 Token，跳过发送。")
