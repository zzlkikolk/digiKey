#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
north-ic 数据爬取工具（Playwright 版）
功能：登录 IC交易网(ic.net.cn)，根据关键字爬取元器件数据，导出为 Excel
使用 Playwright 有头浏览器，让页面的 JS 反爬（jbnxtdm/sEnc）在真实浏览器中自然执行

列表解析说明：
    每个 li.stair_tr 内包含多家供应商（div.result_supply 内多个 a.result_goCompany），
    以及对应的多个库存数量（div.result_totalNumber）。页面通过随机 class + CSS
    控制显示/隐藏（display:none !important），只有部分供应商和库存是可见的。
    本工具在浏览器上下文中计算每个节点的实际 display，只保留非隐藏（可见）的
    供应商名称与库存数量，保证与页面上看到的内容一致。
"""

import os
import re
import time
import random
import string
import hashlib
import base64
import json
import configparser
from datetime import datetime

from bs4 import BeautifulSoup
import pandas as pd
from playwright.sync_api import sync_playwright

# ======================== 常量（对应前端 JS） ========================

# base64 字母表
_ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


# ======================== 配置加载 ========================

def load_config():
    """加载 config/account.properties 配置"""
    config_path = os.path.join(os.path.dirname(__file__), "config", "account.properties")

    # .properties 文件没有 section header，手动补一个再给 configparser 解析
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = "[DEFAULT]\n" + content

    config = configparser.ConfigParser()
    config.read_string(content)

    # 搜索间隔（毫秒），默认 3000ms
    try:
        interval_ms = int(config.get("DEFAULT", "north-ic.SearchInterval", fallback="3000"))
    except ValueError:
        interval_ms = 3000
    if interval_ms < 0:
        interval_ms = 3000

    # 是否开启无头模式（默认 true）
    headless = config.get("DEFAULT", "north-ic.Headless", fallback="true").strip().lower() in (
        "true", "1", "yes", "on",
    )

    return {
        "UserName": config.get("DEFAULT", "north-ic.UserName"),
        "Password": config.get("DEFAULT", "north-ic.Password"),
        "SearchInterval": interval_ms,
        "Headless": headless,
    }


def load_keywords():
    """加载关键字列表"""
    keywords_path = os.path.join(os.path.dirname(__file__), "config", "keywords.txt")
    with open(keywords_path, "r", encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip()]
    return keywords


# ======================== 登录密码加密（保留，用于 Playwright 页面填充表单前的参考） ========================

def _js_number_to_string(num):
    """
    模拟 JS 数字默认转字符串行为
    (仅处理非负整数/浮点场景，保留小数位，去除多余的 .0)
    """
    if float(num) == int(num):
        return str(int(num))
    return repr(float(num))


def _bs(password, random_str, timestamp):
    """
    还原前端 _bs 加密（见 decode.js），返回加密后的密码字符串。

    算法：
        inner  = MD5_hex(password) + timestamp + password + SHA1_hex(random)
        s      = MD5_hex(inner)
        result = base64(s 的 UTF-8 字节)
    """
    s = str(password)
    if len(s) == 0:
        return s

    inner = (
        hashlib.md5(s.encode("utf-8")).hexdigest()
        + _js_number_to_string(timestamp)
        + s
        + hashlib.sha1(random_str.encode("utf-8")).hexdigest()
    )
    s = hashlib.md5(inner.encode("utf-8")).hexdigest()
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def lp_random_string(length=32):
    """生成 32 位随机字符串（对应前端 lp_randomString）"""
    return "".join(random.choice(_ALPHA) for _ in range(length))


def build_login_password(password):
    """生成登录所需的 random/timestamp/pwd"""
    random_str = lp_random_string(32)
    timestamp = int(time.time())  # 秒
    pwd = _bs(password, random_str, timestamp)
    return {
        "random": random_str,
        "timestamp": timestamp,
        "pwd": pwd,
    }


# ======================== Playwright 登录 ========================

def login(page, account):
    """
    通过登录异步接口登录 IC交易网（使用手工加密）。

    说明：
        - 保持原接口登录方式，调用 /async/login.asy.php 并携带手工加密的密码。
        - 使用 page.request 发起请求，让响应 cookie 自动写入浏览器上下文，
          后续 Playwright 打开页面时即可携带登录态。
    返回已登录（cookie 已就绪）的 page。
    """
    login_data = build_login_password(account["Password"])

    ts_ms = int(time.time() * 1000)
    callback = f"jQuery{ts_ms}_{ts_ms + random.randint(1, 100)}"

    params = {
        "callback": callback,
        "IC_Method": "userloginnew",
        "UserName": account["UserName"],
        "Pwd": login_data["pwd"],
        "random": login_data["random"],
        "timestamp": login_data["timestamp"],
        "_": ts_ms,
    }

    print(f"  调用登录接口: {account['UserName']}")

    resp = page.request.get(
        "https://member.ic.net.cn/async/login.asy.php",
        params=params,
        headers={"referer": "https://member.ic.net.cn/"},
        timeout=30000,
    )
    text = resp.text().strip()

    match = re.search(r"\((.*)\)\s*$", text, re.S)
    if not match:
        raise Exception(f"登录响应格式异常: {text[:200]}")
    result = json.loads(match.group(1))
    if result.get("status") != 1:
        raise Exception(f"登录失败: {result.get('error', '未知错误')}")

    # 访问首页确认登录态
    page.goto("https://www.ic.net.cn/", wait_until="domcontentloaded", timeout=60000)
    time.sleep(2)

    if "member.ic.net.cn/login.php" in page.url:
        raise Exception("登录后首页被重定向到登录页，登录状态无效")

    print(f"[登录成功] 账号: {account['UserName']}")
    return page


# ======================== 抓取搜索页 ========================

# 在浏览器中提取每个 li 的可见（非隐藏）数据。
# 页面通过随机 class + CSS 控制 display，只有 display 不为 none 的供应商和库存才可见。
_VISIBLE_ROWS_JS = r"""
() => {
    const isVisible = (el) => {
        if (!el) return false;
        const cs = getComputedStyle(el);
        return cs.display !== 'none' && cs.visibility !== 'hidden';
    };

    const rows = document.querySelectorAll('ul#resultList li.stair_tr:not([id])');
    const out = [];

    rows.forEach((row) => {
        // 供应商：只保留可见的 a.result_goCompany
        const suppliers = [...row.querySelectorAll('div.result_supply a.result_goCompany')]
            .filter(isVisible)
            .map(a => a.textContent.trim())
            .filter(Boolean);

        // 库存数量：只保留可见的 result_totalNumber
        const qtys = [...row.querySelectorAll('div.result_totalNumber')]
            .filter(isVisible)
            .map(d => d.textContent.trim())
            .filter(Boolean);

        // 型号（取第一个可见的，若都不可见则取第一个）
        let model = '';
        const modelLinks = [...row.querySelectorAll('div.result_id span.product_number a')].filter(isVisible);
        if (modelLinks.length > 0) {
            model = modelLinks[0].textContent.trim();
        } else {
            const modelSpan = row.querySelector('div.result_id span.product_number');
            if (modelSpan) model = modelSpan.textContent.trim();
        }

        // 厂商 / 批号 / 封装
        const factoryEl = row.querySelector('div.result_factory');
        const factory = factoryEl ? (factoryEl.getAttribute('title') || factoryEl.textContent.trim()) : '';

        const batchEl = row.querySelector('div.result_batchNumber');
        const batch = batchEl ? (batchEl.getAttribute('title') || batchEl.textContent.trim()) : '';

        const packageEl = row.querySelector('div.result_pakaging');
        const package_ = packageEl ? (packageEl.getAttribute('title') || packageEl.textContent.trim()) : '';

        // 仓库
        const placeElems = [...row.querySelectorAll('div.result_kwplace div.kw_list')]
            .map(p => p.textContent.trim()).filter(Boolean);
        const place = placeElems.join('|');

        // 说明
        const promptElems = [...row.querySelectorAll('div.result_prompt div.result_explain')]
            .map(p => p.textContent.trim()).filter(Boolean);
        const prompt = promptElems.join('|');

        // 日期
        let date = '';
        const dateHidden = row.querySelector('div.result_date input[type="hidden"]');
        if (dateHidden && dateHidden.value) {
            date = dateHidden.value.trim();
        } else {
            const dateEl = row.querySelector('div.result_date');
            if (dateEl) date = (dateEl.getAttribute('title') || '').trim();
        }

        out.push({ suppliers, qtys, model, factory, batch, package_, place, prompt, date });
    });

    return JSON.stringify(out);
}
"""


def fetch_search_page(page, keyword):
    """
    抓取关键字的搜索页数据。
    - 使用 Playwright 加载页面，等待页面 JS（含反爬验证/刷新）执行完成。
    - 若登录过期返回 None。
    返回 (basic_html, visible_rows)：
        basic_html   用于解析数据1（参考价/月搜索量）的 HTML
        visible_rows 列表，每项为 {suppliers, qtys, model, ...}（已按可见性过滤）
    """
    url = f"https://www.ic.net.cn/search/{requests_quote(keyword)}.html"

    # 反爬验证页的 goto 可能超时（一直未触发 domcontentloaded），捕获后继续轮询
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
    except Exception as e:
        print(f"  [提示] goto 超时({str(e)[:40]})，继续等待反爬刷新...")

    # 等待搜索结果容器 #resultList 出现；反爬页会自动刷新/渲染真实内容
    deadline = time.time() + 30
    while time.time() < deadline:
        if "member.ic.net.cn/login.php" in page.url:
            print(f"  [警告] {keyword}: 登录已过期（重定向到登录页）")
            return None
        try:
            if page.locator("#resultList").count() > 0:
                break
        except Exception:
            pass
        time.sleep(1)

    # 再给一点时间确保数据渲染完成
    time.sleep(2)

    html = page.content()
    visible_rows = []
    try:
        raw = page.evaluate(_VISIBLE_ROWS_JS)
        visible_rows = json.loads(raw)
    except Exception as e:
        print(f"  [警告] 提取可见数据失败: {e}")

    return html, visible_rows


def requests_quote(text):
    """简单的 URL 编码（兼容 Python3 requests.utils.quote）"""
    from urllib.parse import quote
    return quote(text, safe="")


# ======================== 数据1 解析 ========================

def parse_basic_info(soup):
    """
    解析数据1：参考价、月搜索量
    返回 dict
    """
    result = {
        "参考价": "",
        "月搜索量": "",
    }

    # 参考价: <div class="cankaoPrice">...<span class="orangeT">￥32.156</span>
    cankao = soup.select_one("div.cankaoPrice span.orangeT")
    if cankao:
        result["参考价"] = cankao.text.strip()

    # 月搜索量: <div class="monthSearchNum">...<span class="orangeT">84929</span>
    month = soup.select_one("div.monthSearchNum span.orangeT")
    if month:
        result["月搜索量"] = month.text.strip()

    return result


# ======================== 数据2 解析（基于可见数据） ========================

def parse_visible_rows(visible_rows):
    """
    将浏览器提取的可见数据整理成 Excel 行。

    每行 li 内只保留可见（display 非 none）的供应商和库存数量，按顺序一一对应；
    若可见供应商与可见数量数量不一致，则取两者较小值配对，避免错位。
    返回 records 列表
    """
    records = []

    for row in visible_rows:
        suppliers = row.get("suppliers") or []
        qtys = row.get("qtys") or []

        # 以供应商数为基准拆行，数量按索引对齐（不足则补空）
        num = max(len(suppliers), 1)
        for idx in range(num):
            supplier = suppliers[idx] if idx < len(suppliers) else ""
            quantity = qtys[idx] if idx < len(qtys) else ""
            record = {
                "供应商": supplier,
                "型号": row.get("model", ""),
                "厂商": row.get("factory", ""),
                "批号": row.get("batch", ""),
                "数量": quantity,
                "封装": row.get("package_", ""),
                "仓库": row.get("place", ""),
                "说明": row.get("prompt", ""),
                "日期": row.get("date", ""),
            }
            # 至少有一条有效数据才保留
            if any(v for v in record.values()):
                records.append(record)

    return records


def scrape_keyword(page, keyword):
    """
    爬取单个关键字的所有数据
    登录失效返回 None
    """
    print(f"[爬取中] {keyword} ...")
    fetched = fetch_search_page(page, keyword)
    if fetched is None:
        return None
    html, visible_rows = fetched

    soup = BeautifulSoup(html, "html.parser")

    # 数据1：参考价、月搜索量
    basic_info = parse_basic_info(soup)

    # 数据2：库存结果列表（只保留可见数据）
    result_records = parse_visible_rows(visible_rows)

    # 合并：每个库存记录带上数据1
    results = []
    if not result_records:
        # 无库存数据，也输出基础信息
        row = {"关键字": keyword}
        row.update(basic_info)
        row.update({
            "供应商": "", "型号": "", "厂商": "", "批号": "",
            "数量": "", "封装": "", "仓库": "", "说明": "", "日期": "",
        })
        print(f"  [完成] {keyword}: 基础信息已获取，无库存数据")
        return [row]

    for rr in result_records:
        row = {"关键字": keyword}
        row.update(basic_info)
        row.update(rr)
        results.append(row)

    print(f"  [完成] {keyword}: {len(results)} 条库存记录")
    return results


# ======================== 导出 Excel ========================

def export_to_excel(all_records, output_dir=None):
    """将爬取结果导出为 Excel"""
    if not all_records:
        print("没有数据可导出")
        return None

    df = pd.DataFrame(all_records)

    column_order = [
        "关键字", "参考价", "月搜索量",
        "供应商", "型号", "厂商", "批号", "数量",
        "封装", "仓库", "说明", "日期",
    ]
    df = df[column_order]

    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"north_ic_{timestamp}.xlsx"
    filepath = os.path.join(output_dir, filename)

    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="元器件数据")

        worksheet = writer.sheets["元器件数据"]
        col_widths = {
            "A": 18,  # 关键字
            "B": 12,  # 参考价
            "C": 12,  # 月搜索量
            "D": 40,  # 供应商
            "E": 20,  # 型号
            "F": 20,  # 厂商
            "G": 12,  # 批号
            "H": 16,  # 数量
            "I": 12,  # 封装
            "J": 16,  # 仓库
            "K": 30,  # 说明
            "L": 22,  # 日期
        }
        for col_letter, width in col_widths.items():
            worksheet.column_dimensions[col_letter].width = width

    print(f"\n导出成功: {filepath} (共 {len(df)} 条记录)")
    return filepath


# ======================== 反自动化检测（绕过 q.js 反爬） ========================

# 在页面任何脚本执行前注入，隐藏自动化特征，避免被 q.js 用 document.write("Stop") 清空页面
_ANTI_DETECT_JS = r"""
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// 语言列表非空
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US', 'en'] });
Object.defineProperty(navigator, 'language', { get: () => 'zh-CN' });

// 提供插件列表，避免 Chrome 检测 plugins.length === 0
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const p = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            { name: 'Native Client', filename: 'internal-nacl-plugin' },
        ];
        p.item = (i) => p[i];
        p.namedItem = (n) => p.find(x => x.name === n) || null;
        p.refresh = () => {};
        return p;
    }
});

// 隐藏自动化相关标记
try {
    const cdp = () => {};
    window.cdc_adoQpoasnfa76pfcZLmcfl_Array = undefined;
} catch (e) {}
"""


def apply_anti_detection(context):
    """在 context 上注册反检测脚本（每个新页面加载前都会执行）"""
    context.add_init_script(_ANTI_DETECT_JS)


# ======================== 主流程 ========================

def main():
    print("=" * 50)
    print("north-ic 数据爬取工具 (Playwright)")
    print("=" * 50)

    # 加载配置
    account = load_config()
    keywords = load_keywords()

    if not account["UserName"] or not account["Password"]:
        print("错误: config/account.properties 中未配置账号或密码")
        return
    if not keywords:
        print("错误: config/keywords.txt 中没有关键字")
        return

    print(f"账号: {account['UserName']}")
    print(f"关键字数量: {len(keywords)}")
    print(f"搜索间隔: {account['SearchInterval']} ms")
    print(f"无头模式: {account['Headless']}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=account["Headless"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            permissions=["notifications"],
        )
        apply_anti_detection(context)
        page = context.new_page()

        # 登录
        try:
            login(page, account)
        except Exception as e:
            print(f"[登录失败] {e}")
            browser.close()
            return

        # 爬取每个关键字
        all_records = []
        i = 0
        relogin_count = 0
        while i < len(keywords):
            keyword = keywords[i]
            print(f"\n[{i + 1}/{len(keywords)}] 处理关键字: {keyword}")
            try:
                records = scrape_keyword(page, keyword)

                if records is None:
                    # 登录失效，重新登录（复用同一个 page）
                    if relogin_count >= 3:
                        print("  [错误] 重试登录超过3次，跳过此关键字")
                        i += 1
                        relogin_count = 0
                        continue
                    print("  正在重新登录...")
                    relogin_count += 1
                    login(page, account)
                    continue  # 不增加 i，重新爬取当前关键字

                relogin_count = 0
                all_records.extend(records)
                i += 1
            except Exception as e:
                print(f"  [错误] {keyword}: {e}")
                i += 1

            # 请求间隔，避免被封（配置文件中的毫秒数，叠加 ±20% 随机抖动）
            interval_ms = account["SearchInterval"]
            jitter_ms = interval_ms * random.uniform(0.8, 1.2)
            time.sleep(jitter_ms / 1000.0)

        browser.close()

    # 导出 Excel
    print("\n" + "=" * 50)
    export_to_excel(all_records)

    print("=" * 50)
    print("爬取完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()
