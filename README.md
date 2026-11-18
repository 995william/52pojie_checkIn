<div align="center">

# 吾爱破解（52pojie）自动化签到机器人

**纯 Python 原生算法逆向穿透网宿（WZWS）WAF 防护盾 · 智能任务闭环 · 集中管控中枢联动 · 智能 Cookie 续签**

[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/995william/52pojie_checkIn/checkin.yml?branch=main&label=%E7%AD%BE%E5%88%B0%E6%B5%81%E6%B0%B4%E7%BA%BF&logo=github)](https://github.com/995william/52pojie_checkIn/actions)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

## 📖 项目简介

本项目专为**吾爱破解论坛（52pojie.cn）**量身打造。针对论坛部署的网宿（WZWS）高强度动态 WAF 防护盾，完全采用**纯原生 Python 算法**解算动态挑战参数与加权设备指纹，无需依赖 Node.js、execjs 或无头浏览器，毫秒级自动穿透防护、完成每日任务申领（`id=2`）与奖励领取，并实时抓取最新**吾爱币（CB）**、总积分与用户组资产。

现已全面接入 **William 签到与自动化管控中枢（[https://checkin.wwcoder.top](https://checkin.wwcoder.top)）**，实现高精度云端统一调度、资产趋势归档、在线智能 Cookie 清洗续签以及每日早报汇总推送。

---

## 🌐 集中管控中枢架构与在线续签

本项目由 **[https://checkin.wwcoder.top](https://checkin.wwcoder.top)** 统一纳管（项目标识：`52pojie`）：

1. **高精度受控调度**：移除不可靠的 GitHub 原生 `schedule` 队列与冗余保活提交，仅保留受控入口 `.github/workflows/checkin.yml`（`workflow_dispatch`），由管控中枢每日准点唤醒，彻底杜绝延迟丢包、重复触发及 60 天休眠停用问题。
2. **标准化指标上报（`hub_reporter.py`）**：任务执行完毕后自动通过零依赖 SDK 向中枢同步打卡状态、耗时、吾爱币余额数值与脱敏账号快照。
3. **静默托管与异常秒级告警**：开启 `HUB_MANAGED_NOTIFY="true"` 后，日常全部成功时自动静默单仓推送，统一并入中枢【每日签到早报】；一旦遭遇 Cookie 失效或 WAF 异常，单仓与中枢双通道立即触发即时告警。
4. **在线智能 Cookie 续签指引**：
   - 电脑浏览器登录 [吾爱破解论坛](https://www.52pojie.cn/)，按 `F12` 打开 **Network（网络）** 面板刷新页面；
   - 右键主请求选择 **Copy as cURL** 或复制 **Request Headers**（确保包含 `HttpOnly` 的核心字段 `htVC_2132_auth` 与 `htVC_2132_saltkey`）；
   - 打开 **[https://checkin.wwcoder.top](https://checkin.wwcoder.top)** 续签中心，直接粘贴原始文本，系统将自动提取清洗有效字段、校验必填项并公钥加密直写本仓库 `POJIE52_COOKIE` Secret，随后自动触发一次验证运行。

---

## ✨ 核心特性

- 🛡️ **纯 Python 原生穿透 WAF**：逆向还原 WZWS 动态算法，动态解算挑战码与设备指纹校验和，零重型运行时依赖。
- 🤖 **防重预检与任务闭环**：首页 `wbs.png` 免打扰预检 -> 申请每日签到任务 -> 领取任务奖励 -> 抓取吾爱币与积分。
- 👥 **多账号平滑轮询**：支持单账号或多账号（换行符或 `@@` 分隔）批量打卡，内置拟人化随机缓冲间隔防频控。
- 🔒 **全链路日志脱敏**：GitHub Actions 控制台与 Job Summary 强制输出动态掩码账号（如 `use****45`），严防公开日志泄露隐私。
- 📱 **移动端窄屏友好排版**：严格采用 12 字符短分割线（`────────────`），手机企业微信气泡零折行。

---

## 📱 消息卡片预览

```text
🔔【52Pojie 每日签到】
────────────
👤 账号：your_user【锋芒初露】
🎉 状态：已签到 ✅
💰 吾爱币：388 CB
────────────
⏰ 2026-11-18 09:01:12
```

---

## 🚀 GitHub Actions 环境变量与 Secrets 说明

在仓库 **Settings -> Secrets and variables -> Actions** 中支持以下配置（接入管控中枢后可通过面板一键同步）：

| Secret 名称 | 必填 | 说明 |
| :--- | :---: | :--- |
| `POJIE52_COOKIE` | **是** | 吾爱破解完整登录 Cookie（需含 `*_saltkey` 与 `*_auth`，多账号换行或 `@@` 分隔） |
| `CHECKIN_HUB_TOKEN` | 推荐 | 集中管控中枢（`checkin.wwcoder.top`）上报鉴权令牌 |
| `WECOM_WEBHOOK` | 可选 | 企业微信群机器人 Webhook URL（异常兜底告警或独立部署推送） |
| `PUSHPLUS_TOKEN` | 可选 | PushPlus 微信推送 Token |

---

## 💻 本地调试运行

```bash
git clone https://github.com/995william/52pojie_checkIn.git
cd 52pojie_checkIn
pip install -r requirements.txt

# 复制 .env.example 或注入环境变量后执行
$env:POJIE52_COOKIE="htVC_2132_saltkey=xxx; htVC_2132_auth=xxx"
$env:HUB_MANAGED_NOTIFY="false"
python main.py
```

---

## 📂 项目目录结构

```text
52pojie_checkIn/
├── .github/
│   └── workflows/
│       └── checkin.yml          # 统一受控签到工作流（workflow_dispatch，全中文步骤）
├── main.py                      # 签到主调度、状态判定、资产提取与中枢上报
├── waf_solver.py                # 纯 Python 网宿（WZWS）WAF 动态挑战求解器
├── notify.py                    # 企微群机器人、PushPlus 与 Actions Summary 分发器
├── hub_reporter.py              # 集中管控中枢零依赖标准化上报 SDK
├── .env.example                 # 环境变量脱敏配置模板
├── .gitignore                   # 敏感凭据与临时文件忽略规则
├── requirements.txt             # Python 依赖清单
└── README.md                    # 项目架构与使用文档
```

---

## ⚖️ 免责声明

本项目仅供 Python 网络协议学习与个人自动化效率研究使用，请严格遵守吾爱破解论坛相关规定，严禁用于任何恶意并发请求或商业用途。
