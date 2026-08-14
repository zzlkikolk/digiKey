#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analog 数据爬取工具
功能：遍历 config/keywords.txt 关键字，爬取 analog.com 网站上的元器件数据，导出为 Excel

说明：
    网站搜索页与 sample-buy 页均为前端 JS 渲染（Algolia Instant Search / MUI 表格），
    直接 requests 抓 HTML 拿不到数据，因此本工具使用 Playwright 驱动真实浏览器渲染后提取。

流程：
    1. 搜索：
       用 Playwright 加载 GET https://www.analog.com/cn/search.html?query={keyword}
       等待页面渲染，取第一个 class="baseball-card" 中
       class="baseball-card-snb" 内的样片及购买（sample-buy）链接。

    2. 解析 sample-buy 页面：
       用 Playwright 加载上一步的 sample-buy 页，等待 MUI 表格渲染，
       根据 {keyword} 筛选对应的行，提取「数量」「单价（人民币）」「库存信息」。
"""

import os
import time
import random
import configparser
from datetime import datetime
from urllib.parse import quote

import pandas as pd
from playwright.sync_api import sync_playwright


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
        interval_ms = int(config.get("DEFAULT", "analog.SearchInterval", fallback="3000"))
    except ValueError:
        interval_ms = 3000
    if interval_ms < 0:
        interval_ms = 3000

    # 是否开启无头模式（默认 true）
    headless = config.get("DEFAULT", "analog.Headless", fallback="true").strip().lower() in (
        "true", "1", "yes", "on",
    )

    return {
        "SearchInterval": interval_ms,
        "Headless": headless,
    }


def load_keywords():
    """加载关键字列表"""
    keywords_path = os.path.join(os.path.dirname(__file__), "config", "keywords.txt")
    with open(keywords_path, "r", encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip()]
    return keywords


def normalize_keyword(keyword):
    """
    归一化关键字用于型号匹配。
    型号如 'LTC6957HMS-2#TRPBF'，表格中可能展示完整型号或基型号。
    取 '#' 前的核心型号（去除大小写差异）做匹配，更稳健。
    """
    core = keyword.split("#")[0].strip().upper()
    return core


# ======================== 步骤1：搜索，取第一个 baseball-card 的 sample-buy 链接 ========================

def fetch_sample_buy_url(page, keyword):
    """
    用 Playwright 加载搜索页，获取第一个 baseball-card 的样片及购买链接。

    返回 sample-buy 页完整 URL；未找到返回 None。
    """
    url = f"https://www.analog.com/cn/search.html?query={quote(keyword)}"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    # 等待第一个 baseball-card 渲染
    try:
        page.wait_for_selector("div.baseball-card", timeout=30000)
    except Exception:
        print("    [提示] 搜索页未渲染出 baseball-card")
        return None

    # 取第一个 baseball-card 中的 sample-buy 链接
    link = page.query_selector("div.baseball-card div.baseball-card-snb a[href]")
    if not link:
        print("    [提示] baseball-card 中未找到 sample-buy 链接")
        return None

    href = link.get_attribute("href") or ""
    href = href.strip()
    if not href:
        return None
    if href.startswith("http"):
        return href
    return "https://www.analog.com" + href


# ======================== 步骤2：解析 sample-buy 页面的表格 ========================

def parse_sample_buy_table(page, sample_buy_url, keyword):
    """
    用 Playwright 加载 sample-buy 页面并解析 MUI 表格。

    表头（示例）：
        产品型号 | 数量/单价（人民币） | 库存信息 | 引脚 | 温度范围 | 封装类型 | 封装 | RoHS | 汽车

    每个数据行：
        <tr class="MuiTableRow-root css-...">
            <td>...</td>   # 1 产品型号
            <td>...</td>   # 2 数量 / 单价（人民币）
            <td>...</td>   # 3 库存信息
            ...

    根据 keyword 筛选对应的行（产品型号与关键字匹配），
    提取「数量」「单价（人民币）」「库存信息」。
    返回 records 列表。
    """
    page.goto(sample_buy_url, wait_until="domcontentloaded", timeout=60000)

    # 等待数据行渲染（JS 渲染，需真实浏览器）
    try:
        page.wait_for_selector("tbody tr.MuiTableRow-root", timeout=30000)
    except Exception:
        print("    [提示] sample-buy 页面表格未渲染")
        return []

    # 表格中数量/单价/库存等字段是异步加载的（初始为 MUI Skeleton 骨架屏）。
    # 等待表格主体内的 Skeleton 全部替换为真实数据，避免抓到空值。
    try:
        page.wait_for_function(
            """() => {
                const skels = document.querySelectorAll(
                    'tbody tr.MuiTableRow-root .MuiSkeleton-root'
                );
                return skels.length === 0;
            }""",
            timeout=30000,
        )
    except Exception:
        # 个别字段可能始终为骨架屏/空，超时不阻塞，按当前状态抓取
        pass

    # 提取全部数据行
    rows = page.query_selector_all("tbody tr.MuiTableRow-root")

    core = normalize_keyword(keyword)
    records = []
    for tr in rows:
        tds = tr.query_selector_all(":scope > td")
        if len(tds) < 3:
            continue

        model_td = tds[0]
        price_td = tds[1]
        stock_td = tds[2]

        # 产品型号
        model_el = model_td.query_selector("span.MuiTypography-subtitleSmall")
        model = model_el.inner_text().strip() if model_el else ""

        # 根据 keyword 筛选对应的行
        if not model:
            continue
        if core not in model.upper():
            continue

        # 数量 / 单价（人民币）
        quantity = ""
        price = ""
        dt_el = price_td.query_selector("dl dt")
        if dt_el:
            quantity = dt_el.inner_text().strip()
        dd_el = price_td.query_selector("dl dd div")
        if dd_el:
            price = dd_el.inner_text().strip()

        # 库存信息
        stock = stock_td.inner_text().strip()

        records.append({
            "产品型号": model,
            "数量": quantity,
            "单价(人民币)": price,
            "库存信息": stock,
        })

    return records


def scrape_keyword(page, keyword):
    """
    爬取单个关键字的所有数据
    返回 records 列表
    """
    print(f"[爬取中] {keyword} ...")

    # 步骤1：搜索，获取 sample-buy 链接
    sample_buy_url = fetch_sample_buy_url(page, keyword)
    if not sample_buy_url:
        print(f"  [完成] {keyword}: 未找到对应的样片及购买链接")
        return []

    print(f"  sample-buy: {sample_buy_url}")

    # 步骤2：加载 sample-buy 页面并解析表格
    records = parse_sample_buy_table(page, sample_buy_url, keyword)

    if not records:
        print(f"  [完成] {keyword}: 未匹配到对应行的数据")
        return []

    print(f"  [完成] {keyword}: {len(records)} 条记录")
    return records


# ======================== 导出 Excel ========================

def export_to_excel(all_records, output_dir=None):
    """将爬取结果导出为 Excel"""
    if not all_records:
        print("没有数据可导出")
        return None

    df = pd.DataFrame(all_records)

    # 列顺序
    column_order = [
        "关键字", "产品型号", "数量", "单价(人民币)", "库存信息",
    ]
    df = df[column_order]

    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "output")

    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"analog_{timestamp}.xlsx"
    filepath = os.path.join(output_dir, filename)

    # 使用 openpyxl 写入，支持自定义列宽
    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="元器件数据")

        # 调整列宽
        worksheet = writer.sheets["元器件数据"]
        col_widths = {
            "A": 30,  # 关键字
            "B": 24,  # 产品型号
            "C": 14,  # 数量
            "D": 16,  # 单价(人民币)
            "E": 14,  # 库存信息
        }
        for col_letter, width in col_widths.items():
            worksheet.column_dimensions[col_letter].width = width

    print(f"\n导出成功: {filepath} (共 {len(df)} 条记录)")
    return filepath


# ======================== 主流程 ========================

def main():
    print("=" * 50)
    print("analog 数据爬取工具")
    print("=" * 50)

    # 加载配置
    config = load_config()
    keywords = load_keywords()

    if not keywords:
        print("错误: config/keywords.txt 中没有关键字")
        return

    print(f"关键字数量: {len(keywords)}")
    print(f"搜索间隔: {config['SearchInterval']} ms")
    print(f"无头模式: {config['Headless']}")

    all_records = []

    # 复用同一个浏览器上下文，避免反复启动
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config["Headless"])
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/151.0.0.0 Safari/537.36"),
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()

        try:
            # 爬取每个关键字
            for i, keyword in enumerate(keywords):
                print(f"\n[{i + 1}/{len(keywords)}] 处理关键字: {keyword}")
                try:
                    records = scrape_keyword(page, keyword)
                    for rec in records:
                        all_records.append({"关键字": keyword, **rec})
                except Exception as e:
                    print(f"  [错误] {keyword}: {e}")

                # 请求间隔，避免被封（配置文件中的毫秒数，叠加 ±20% 随机抖动）
                interval_ms = config["SearchInterval"]
                jitter_ms = interval_ms * random.uniform(0.8, 1.2)
                time.sleep(jitter_ms / 1000.0)
        finally:
            browser.close()

    # 导出 Excel
    print("\n" + "=" * 50)
    export_to_excel(all_records)

    print("=" * 50)
    print("爬取完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()
