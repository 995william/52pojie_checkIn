# -*- coding: utf-8 -*-
"""
吾爱破解（52pojie）自动化签到主程序
支持纯 Python WAF 自动穿透、多账号批量打卡、状态智能判定、集中管控中枢数据上报与多渠道消息推送。
"""

import http.client
import logging
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

import notify
import waf_solver
from hub_reporter import report_to_hub

# 日志格式化配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("52PojieCheckIn")

BASE_URL = "https://www.52pojie.cn"
URL_HOME = f"{BASE_URL}/"
URL_APPLY = f"{BASE_URL}/home.php?mod=task&do=apply&id=2&referer=%2F"
URL_DRAW = f"{BASE_URL}/home.php?mod=task&do=draw&id=2"
URL_CREDIT = f"{BASE_URL}/home.php?mod=spacecp&ac=credit"

DEFAULT_HEADERS = {
    'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    'Accept-Language': "zh-CN,zh;q=0.9,en;q=0.8",
    'Accept-Encoding': "gzip, deflate, br",
    'sec-ch-ua': '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    'sec-ch-ua-mobile': "?0",
    'sec-ch-ua-platform': '"Windows"',
    'Sec-Fetch-Dest': "document",
    'Sec-Fetch-Mode': "navigate",
    'Sec-Fetch-Site': "none",
    'Sec-Fetch-User': "?1",
    'Upgrade-Insecure-Requests': "1",
    'Connection': "close",  # 显式关闭连接，防止跨境长连接被 CDN/WAF 掐断导致 RemoteDisconnected
}


def create_resilient_session(cookies_dict: Optional[Dict[str, str]] = None) -> requests.Session:
    """创建具备连接自愈与重试特性的 requests 会话."""
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    if cookies_dict:
        session.cookies.update(cookies_dict)
    adapter = HTTPAdapter(
        max_retries=Retry(total=2, backoff_factor=1, status_forcelist=[502, 503, 504], raise_on_status=False),
        pool_connections=5,
        pool_maxsize=5
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def safe_request(session: requests.Session, method: str, url: str, max_retries: int = 3, retry_on_403: bool = True, **kwargs) -> requests.Response:
    """
    自愈型安全网络请求：
    自动处理连接断开、SSL EOF 与网络抖动，并对 HTTP 403 频控/临时阻断执行套接字重置与退避重试。
    """
    kwargs.setdefault('timeout', 25)
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.request(method, url, **kwargs)
            # 捕获 HTTP 403 Forbidden 频控/硬阻断特征并执行自愈退避
            if resp.status_code == 403 and retry_on_403 and attempt < max_retries:
                wait_sec = 2.5 * attempt + random.uniform(1.0, 2.5)
                logger.warning(f"请求 {url} 遭遇 HTTP 403 Forbidden（可能触发 CDN/WAF 临时频控），释放连接并等待 {wait_sec:.1f} 秒后重试 ({attempt}/{max_retries})...")
                session.close()
                time.sleep(wait_sec)
                continue
            return resp
        except (requests.exceptions.RequestException, http.client.RemoteDisconnected, ConnectionResetError) as e:
            last_err = e
            logger.warning(f"请求 {url} 遭遇网络抖动 ({type(e).__name__}): {e}，正在执行第 {attempt}/{max_retries} 次自愈重试...")
            session.close()  # 释放已失效的底层套接字
            if attempt < max_retries:
                time.sleep(2 * attempt + random.uniform(0.5, 1.5))
    if last_err:
        raise last_err
    return resp


def fetch_user_assets(session: requests.Session) -> Dict[str, str]:
    """查询用户的资产数据（吾爱币、总积分、用户组）."""
    assets = {"cb": "未知", "credit": "未知", "group": "未知"}
    try:
        credit_headers = session.headers.copy()
        credit_headers.update({
            'Referer': URL_HOME,
            'Sec-Fetch-Site': 'same-origin',
        })
        resp = safe_request(session, "GET", URL_CREDIT, headers=credit_headers)
        if waf_solver.is_waf_page(resp.text):
            if waf_solver.bypass_waf(session, URL_CREDIT, resp.text):
                time.sleep(1.5)
                resp = safe_request(session, "GET", URL_CREDIT, headers=credit_headers)
        elif resp.status_code == 403 or "403 Forbidden" in resp.text:
            logger.warning("获取资产数据遭遇 403 阻断，等待冷却后重试...")
            time.sleep(random.uniform(2.5, 4.0))
            resp = safe_request(session, "GET", URL_CREDIT, headers=credit_headers)

        if BeautifulSoup:
            soup = BeautifulSoup(resp.text, 'html.parser')
            for li in soup.find_all('li'):
                t = li.text.strip()
                if '吾爱币' in t:
                    m = re.search(r'(\d+(?:\.\d+)?)\s*CB', t, re.I)
                    if m:
                        assets["cb"] = f"{m.group(1)} CB"
                elif '积分:' in t and '总积分' in t:
                    m = re.search(r'积分:\s*(\d+)', t)
                    if m:
                        assets["credit"] = m.group(1)
            g_elem = soup.find('a', id='g_upmine')
            if g_elem:
                assets["group"] = g_elem.text.replace('用户组:', '').strip()

        # 正则降级保障
        if assets["cb"] == "未知":
            m_cb = re.search(r'吾爱币:\s*.*?(\d+(?:\.\d+)?)\s*CB', resp.text, re.S | re.I)
            if m_cb:
                assets["cb"] = f"{m_cb.group(1)} CB"
        if assets["credit"] == "未知":
            m_c = re.search(r'积分:\s*</em>(\d+)', resp.text) or re.search(r'积分:\s*(\d+)', resp.text)
            if m_c:
                assets["credit"] = m_c.group(1)
        if assets["group"] == "未知":
            m_g = re.search(r'用户组:\s*.*?target="_blank">([^<]+)</a>', resp.text) or re.search(r'用户组:\s*([^\s<|]+)', resp.text)
            if m_g:
                assets["group"] = m_g.group(1).strip()
    except Exception as e:
        logger.warning(f"获取资产数据异常: {e}")
    return assets


def parse_cookies(cookie_str: str) -> Dict[str, str]:
    """解析 Cookie 字符串为字典."""
    cookies = {}
    for item in cookie_str.split(';'):
        item = item.strip()
        if not item:
            continue
        parts = item.split('=', 1)
        if len(parts) == 2:
            cookies[parts[0].strip()] = parts[1].strip()
    return cookies


def check_cookie_validity(cookies: Dict[str, str]) -> Tuple[bool, str]:
    """检查 Cookie 中是否包含 Discuz 核心认证字段."""
    has_saltkey = any(k.endswith("_saltkey") for k in cookies.keys())
    has_auth = any(k.endswith("_auth") for k in cookies.keys())
    if not (has_saltkey and has_auth):
        return False, "缺少核心凭据 (需包含 *_saltkey 与 *_auth)"
    return True, "Cookie 字段完整"


def parse_account_username(html: str) -> str:
    """尝试从论坛页面提取当前登录的用户名或 UID."""
    if not html or "<title>403 Forbidden</title>" in html:
        return ""
    if BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
        user_elem = soup.find("strong", class_="vwmy") or soup.find("a", title="访问我的空间")
        if user_elem:
            return user_elem.text.strip()
    else:
        m = re.search(r'<strong class="vwmy"[^>]*><a[^>]*>([^<]+)</a></strong>', html) or \
            re.search(r'<a[^>]*title="访问我的空间"[^>]*>([^<]+)</a>', html)
        if m:
            return m.group(1).strip()

    # 查找个人中心链接
    match = re.search(r"home\.php\?mod=space&uid=(\d+)", html)
    if match:
        return f"UID_{match.group(1)}"

    # 校验是否为论坛正常 HTML 页面（包含基础论坛关键词）
    if "吾爱破解" in html or "52pojie" in html or "discuz" in html.lower():
        return "已登录用户"
    return ""


def mask_username(username: str) -> str:
    """对账号名称进行安全脱敏，避免公开日志泄露真实用户名."""
    if not username or username in ("未知", "已登录用户"):
        return username
    if username.startswith("UID_") and len(username) > 6:
        return f"UID_{username[4:6]}****{username[-2:]}"
    if len(username) <= 2:
        return username[0] + "*"
    elif len(username) <= 4:
        return username[0] + "**" + username[-1]
    else:
        # 保留前3位和后2位，中间用固定星号遮盖（如 user12345 -> use****45）
        return f"{username[:3]}****{username[-2:]}"


def extract_cb_number(cb_str: str) -> Optional[float]:
    """从吾爱币字符串（如 '388 CB'）提取浮点数."""
    if not cb_str:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*CB", str(cb_str), re.I)
    if not m:
        m = re.search(r"^(\d+(?:\.\d+)?)$", str(cb_str).strip())
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def extract_reward_cb(msg_str: str) -> Optional[float]:
    """从签到返回消息中尝试提取奖励吾爱币数值."""
    if not msg_str:
        return None
    m = re.search(r"吾爱币[^\d]*(\d+(?:\.\d+)?)", str(msg_str))
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def check_in_account(account_index: int, cookie_str: str) -> Dict[str, str]:
    """执行单个账号的签到流程."""
    cookie_str = cookie_str.strip()
    if not cookie_str:
        return {"index": str(account_index), "user": "未知", "status": "失败", "msg": "Cookie 为空"}

    cookies_dict = parse_cookies(cookie_str)
    valid, msg = check_cookie_validity(cookies_dict)
    if not valid:
        return {"index": str(account_index), "user": "未知", "status": "失败", "msg": msg}

    session = create_resilient_session(cookies_dict)

    logger.info(f"===> 开始处理第 {account_index} 个账号...")

    username = "未知"

    try:
        # 1. 访问首页进行预检
        logger.info(f"[{account_index}] 正在访问论坛首页进行登录与签到预检...")
        home_headers = session.headers.copy()
        home_headers.update({'Sec-Fetch-Site': 'none'})
        home_resp = safe_request(session, "GET", URL_HOME, headers=home_headers)

        # 检查首页是否遇到 WAF 挑战盾
        if waf_solver.is_waf_page(home_resp.text):
            logger.info(f"[{account_index}] 首页触发 WAF 挑战盾，正在求解穿透...")
            if waf_solver.bypass_waf(session, URL_HOME, home_resp.text):
                time.sleep(2.0)
                home_resp = safe_request(session, "GET", URL_HOME, headers=home_headers)
            else:
                return {"index": str(account_index), "user": "未知", "status": "失败", "msg": "首页 WAF 穿透失败"}

        # 检查首页是否遭遇 403 阻断
        if home_resp.status_code == 403 or "403 Forbidden" in home_resp.text:
            logger.warning(f"[{account_index}] 首页遭遇 403 Forbidden 阻断，尝试自愈冷却重连...")
            session.close()
            time.sleep(random.uniform(3.5, 6.0))
            home_resp = safe_request(session, "GET", f"{URL_HOME}?_={int(time.time()*1000)}", headers=home_headers)
            if waf_solver.is_waf_page(home_resp.text):
                waf_solver.bypass_waf(session, URL_HOME, home_resp.text)
                time.sleep(2.0)
                home_resp = safe_request(session, "GET", URL_HOME, headers=home_headers)

        if home_resp.status_code == 403 or "403 Forbidden" in home_resp.text:
            return {"index": str(account_index), "user": "未知", "status": "失败", "msg": "论坛首页遭遇 403 访问限制 (WAF/CDN阻断)"}

        # 检查是否已登录
        if "您需要先登录才能继续本操作" in home_resp.text or ("登录" in home_resp.text and "退出" not in home_resp.text):
            if "member.php?mod=logging&action=login" in home_resp.text:
                return {"index": str(account_index), "user": "未知", "status": "失败", "msg": "Cookie 已失效，请重新获取"}

        username = parse_account_username(home_resp.text) or "已登录用户"
        logger.info(f"[{account_index}] 账号身份确认: {mask_username(username)}")

        status = "成功"
        msg = ""

        if "wbs.png" in home_resp.text:
            logger.info(f"[{account_index}] 首页状态显示：今日已打卡 (wbs.png)")
            status = "成功"
            msg = "今日已签到 (首页状态确认)"
        else:
            # 预留充分缓冲间隔，模拟人工点击节奏，规避高频阻断
            wait_time = random.uniform(2.5, 4.5)
            logger.info(f"[{account_index}] 预检通过，等待 {wait_time:.1f} 秒后发起任务申请...")
            time.sleep(wait_time)

            # 2. 申请任务 (Apply)
            logger.info(f"[{account_index}] 正在申请签到任务 (id=2)...")
            apply_headers = session.headers.copy()
            apply_headers.update({
                'Referer': URL_HOME,
                'Sec-Fetch-Site': 'same-origin',
            })
            apply_resp = safe_request(session, "GET", URL_APPLY, headers=apply_headers)

            # 任务申请页面若遇到 WAF 盾，自动穿透
            if waf_solver.is_waf_page(apply_resp.text):
                logger.info(f"[{account_index}] 任务申请接口触发 WAF 挑战盾，正在求解穿透...")
                if waf_solver.bypass_waf(session, URL_APPLY, apply_resp.text):
                    time.sleep(2.0)
                    logger.info(f"[{account_index}] WAF 穿透成功，重新请求任务申请...")
                    apply_resp = safe_request(session, "GET", URL_APPLY, headers=apply_headers)
                else:
                    return {"index": str(account_index), "user": username, "status": "失败", "msg": "任务申请接口 WAF 穿透失败", "cb": "未知", "credit": "未知", "group": "未知"}
            elif apply_resp.status_code == 403 or "403 Forbidden" in apply_resp.text:
                logger.warning(f"[{account_index}] 任务申请接口遭遇 403 阻断，尝试重新从首页握手刷新 WAF 通行证...")
                session.close()
                time.sleep(random.uniform(3.5, 5.5))
                home_refresh = safe_request(session, "GET", URL_HOME, headers=home_headers)
                if waf_solver.is_waf_page(home_refresh.text):
                    waf_solver.bypass_waf(session, URL_HOME, home_refresh.text)
                    time.sleep(2.0)
                apply_resp = safe_request(session, "GET", URL_APPLY, headers=apply_headers)

            # 申请与领奖之间留出从容缓冲间隔（3.0 ~ 5.5 秒）
            draw_wait = random.uniform(3.0, 5.5)
            logger.info(f"[{account_index}] 任务申请完毕，等待 {draw_wait:.1f} 秒后领取奖励...")
            time.sleep(draw_wait)

            # 3. 领取签到奖励 (Draw)
            logger.info(f"[{account_index}] 正在领取签到任务奖励...")
            draw_headers = session.headers.copy()
            draw_headers.update({
                'Referer': URL_APPLY,
                'Sec-Fetch-Site': 'same-origin',
            })
            draw_resp = safe_request(session, "GET", URL_DRAW, headers=draw_headers)

            if waf_solver.is_waf_page(draw_resp.text):
                logger.info(f"[{account_index}] 领奖接口触发 WAF 挑战盾，正在求解穿透...")
                if waf_solver.bypass_waf(session, URL_DRAW, draw_resp.text):
                    time.sleep(2.0)
                    draw_resp = safe_request(session, "GET", URL_DRAW, headers=draw_headers)
                else:
                    return {"index": str(account_index), "user": username, "status": "失败", "msg": "领奖接口 WAF 穿透失败", "cb": "未知", "credit": "未知", "group": "未知"}
            elif draw_resp.status_code == 403 or "403 Forbidden" in draw_resp.text:
                logger.warning(f"[{account_index}] 领奖接口遭遇 403 阻断，尝试冷却重试...")
                session.close()
                time.sleep(random.uniform(4.0, 6.0))
                draw_resp = safe_request(session, "GET", URL_DRAW, headers=draw_headers)

            # 4. 解析结果反馈
            result_text = ""
            if BeautifulSoup:
                soup = BeautifulSoup(draw_resp.text, "html.parser")
                msg_elem = soup.find("div", id="messagetext")
                if msg_elem and msg_elem.find("p"):
                    result_text = msg_elem.find("p").text.strip()
            else:
                m = re.search(r'<div id="messagetext"[^>]*>.*?<p>([^<]+)</p>', draw_resp.text, re.S)
                if m:
                    result_text = m.group(1).strip()

            if not result_text:
                if draw_resp.status_code == 403 or "403 Forbidden" in draw_resp.text:
                    status, msg = "失败", "接口触发 403 访问限制 (WAF/CDN 频控阻断)"
                elif "您需要先登录才能继续本操作" in draw_resp.text:
                    status, msg = "失败", "Cookie 已失效"
                elif "不是进行中的任务" in draw_resp.text or "今日已签到" in draw_resp.text:
                    status, msg = "成功", "今日已签到"
                elif "恭喜" in draw_resp.text or "奖励" in draw_resp.text:
                    status, msg = "成功", "签到成功并领取奖励"
                else:
                    clean_msg = re.sub(r'<[^>]+>', ' ', draw_resp.text).strip()
                    clean_msg = ' '.join(clean_msg.split())[:60]
                    status, msg = "未知", f"未获取到明确消息: {clean_msg}"
            else:
                logger.info(f"[{account_index}] 领奖反馈: {result_text}")
                if "403 Forbidden" in result_text:
                    status, msg = "失败", "接口触发 403 访问限制 (WAF/CDN 频控阻断)"
                elif "您需要先登录才能继续本操作" in result_text:
                    status, msg = "失败", "Cookie 已失效"
                elif "恭喜" in result_text or "完成" in result_text or "奖励" in result_text:
                    status, msg = "成功", f"签到成功 ({result_text})"
                elif "不是进行中的任务" in result_text or "已经完成" in result_text or "今日已签到" in result_text:
                    status, msg = "成功", "今日已签到"
                else:
                    status, msg = "提示", result_text

        # 5. 抓取用户资产（吾爱币、总积分、用户组）
        assets = fetch_user_assets(session)
        logger.info(f"[{account_index}] 资产总览: 吾爱币={assets['cb']}, 积分={assets['credit']}, 用户组={assets['group']}")

        return {
            "index": str(account_index),
            "user": username,
            "status": status,
            "msg": msg,
            "cb": assets["cb"],
            "credit": assets["credit"],
            "group": assets["group"]
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"[{account_index}] 网络请求异常: {e}")
        return {"index": str(account_index), "user": username, "status": "失败", "msg": f"网络异常: {e}"}
    except Exception as e:
        logger.error(f"[{account_index}] 处理过程发生错误: {e}")
        return {"index": str(account_index), "user": username, "status": "失败", "msg": f"异常: {e}"}


def build_report_text(results_list: List[Dict[str, str]], time_str: str, mask: bool = False) -> str:
    """生成移动端零折行格式化签到汇报卡片文本，支持公开日志脱敏."""
    divider = "────────────"
    report_lines = [
        "🔔【52Pojie 每日签到】",
        divider,
    ]
    for idx, r in enumerate(results_list):
        if idx > 0:
            report_lines.append(divider)
        user_group = r.get('group', '未知')
        if user_group == '未知':
            user_group = '会员'

        if r["status"] == "成功":
            if "已签到" in r["msg"] or "已打卡" in r["msg"]:
                status_text = "已签到 ✅"
            else:
                status_text = "签到成功 ✅"
        else:
            status_text = f"签到失败 ❌ ({r['msg']})"

        display_user = mask_username(r['user']) if mask else r['user']
        report_lines.append(f"👤 账号：{display_user}【{user_group}】")
        report_lines.append(f"🎉 状态：{status_text}")
        report_lines.append(f"💰 吾爱币：{r.get('cb', '未知')}")

    report_lines.append(divider)
    report_lines.append(f"⏰ {time_str}")
    return "\n".join(report_lines)


def sync_results_to_hub(results: List[Dict[str, str]], duration_ms: int, public_card: str) -> None:
    """组装脱敏账号快照并上报至集中管控中枢."""
    accounts_payload: List[Dict[str, Any]] = []
    balances: List[float] = []
    rewards: List[float] = []

    for r in results:
        raw_user = r.get("user", "未知")
        masked_user = mask_username(raw_user) if raw_user else f"账号#{r.get('index', '1')}"
        msg = r.get("msg", "")
        cb_num = extract_cb_number(r.get("cb", ""))
        reward_num = extract_reward_cb(msg)

        if r.get("status") == "成功":
            if "已签到" in msg or "已打卡" in msg:
                acc_status = "already_signed"
            else:
                acc_status = "success"
        else:
            acc_status = "failed"

        if cb_num is not None:
            balances.append(cb_num)
        if reward_num is not None:
            rewards.append(reward_num)

        accounts_payload.append({
            "account_mask": masked_user,
            "status": acc_status,
            "reward_num": reward_num,
            "balance_num": cb_num,
            "unit": "CB",
            "message": msg,
            "extra": {
                "credit": r.get("credit", "未知"),
                "group": r.get("group", "未知"),
            },
        })

    ok_set = {"success", "already_signed"}
    ok_count = sum(1 for a in accounts_payload if a["status"] in ok_set)
    total_count = len(accounts_payload)

    if total_count == 0 or ok_count == 0:
        hub_status = "failed"
    elif ok_count < total_count:
        hub_status = "partial"
    elif all(a["status"] == "already_signed" for a in accounts_payload):
        hub_status = "already_signed"
    else:
        hub_status = "success"

    balance_total = round(sum(balances), 2) if balances else None
    reward_total = round(sum(rewards), 2) if rewards else None

    if balance_total is not None:
        bal_disp = int(balance_total) if balance_total.is_integer() else balance_total
        if reward_total is not None and reward_total > 0:
            rew_disp = int(reward_total) if reward_total.is_integer() else reward_total
            asset_text = f"{bal_disp} CB (+{rew_disp} CB)"
        else:
            asset_text = f"{bal_disp} CB"
    else:
        asset_text = "已签到" if hub_status in ok_set else "签到异常"

    if total_count == 1:
        summary_text = accounts_payload[0]["message"] or ("今日已签到" if hub_status == "already_signed" else "签到完成")
    else:
        summary_text = f"成功 {ok_count}/{total_count} 个账号"

    report_to_hub(
        project_slug="52pojie",
        status=hub_status,
        summary=summary_text,
        duration_ms=duration_ms,
        asset_text=asset_text,
        reward_total=reward_total,
        balance_total=balance_total,
        raw_card=public_card,
        accounts=accounts_payload,
    )


def main():
    start_ts = time.time()
    logger.info("==========================================")
    logger.info("   吾爱破解（52pojie）自动签到任务启动   ")
    logger.info("==========================================")

    # 优先从环境变量获取 Cookie
    raw_cookies = os.environ.get("POJIE52_COOKIE") or os.environ.get("PJ52_COOKIE")

    # 如果环境变量未设置，检查是否存在本地私有测试文件 (不会提交到 git)
    if not raw_cookies and os.path.exists("local_cookie.txt"):
        try:
            with open("local_cookie.txt", "r", encoding="utf-8") as f:
                raw_cookies = f.read().strip()
                logger.info("从本地 local_cookie.txt 文件载入 Cookie。")
        except Exception:
            pass

    if not raw_cookies:
        warning_msg = (
            "未检测到环境变量 POJIE52_COOKIE 或 PJ52_COOKIE！\n"
            "请前往管控中枢 https://checkin.wwcoder.top 或仓库 Actions Secrets 配置 POJIE52_COOKIE。"
        )
        logger.warning(warning_msg)
        duration_ms = int((time.time() - start_ts) * 1000)
        report_to_hub(
            project_slug="52pojie",
            status="failed",
            summary="未配置 POJIE52_COOKIE 凭据",
            duration_ms=duration_ms,
            asset_text="缺少凭据",
            raw_card=warning_msg,
        )
        notify.send("吾爱破解签到提醒", warning_msg, skip_push=False)
        sys.exit(0)

    # 支持多账号（换行符、@@ 或 & 分隔）
    account_list = []
    for line in re.split(r'[\r\n]+|@@|&', raw_cookies):
        line = line.strip()
        if line and not line.startswith("#"):
            account_list.append(line)

    logger.info(f"共检测到 {len(account_list)} 个账号待处理。")

    results = []
    for idx, cookie in enumerate(account_list, 1):
        res = check_in_account(idx, cookie)
        results.append(res)
        if idx < len(account_list):
            sleep_time = random.uniform(2.0, 5.0)
            logger.info(f"等待 {sleep_time:.1f} 秒后处理下一个账号...")
            time.sleep(sleep_time)

    duration_ms = int((time.time() - start_ts) * 1000)

    # 格式化最终汇报 (北京时间 UTC+8)
    tz_beijing = timezone(timedelta(hours=8))
    beijing_time = datetime.now(tz_beijing).strftime("%Y-%m-%d %H:%M:%S")

    # 生成私有推送内容（真实账号）与公开展示内容（脱敏账号）
    private_summary = build_report_text(results, beijing_time, mask=False)
    public_summary = build_report_text(results, beijing_time, mask=True)

    # 控制台日志仅输出脱敏版本，杜绝公开控制台泄露账号
    logger.info("\n" + public_summary)

    # 同步标准化结果至集中管控中枢
    sync_results_to_hub(results, duration_ms, public_summary)

    has_failed = any(r["status"] != "成功" for r in results)
    hub_managed = os.environ.get("HUB_MANAGED_NOTIFY", "").strip().lower() == "true"
    skip_direct_push = hub_managed and not has_failed

    # 发送推送（中枢托管且全部成功时静默单仓推送，失败时照常直推告警）
    notify.send("52Pojie 每日签到", private_summary, public_content=public_summary, skip_push=skip_direct_push)

    logger.info("所有签到流程处理完毕。")

    # 若有任何账号未签到成功，退出码返回 1，以便 GitHub Actions 清晰展示失败状态
    if has_failed:
        logger.error("检测到存在签到失败的账号，退出码设为 1。")
        sys.exit(1)


if __name__ == "__main__":
    main()
