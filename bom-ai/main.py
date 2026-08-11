#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bom.ai 数据爬取工具
功能：登录 bom.ai，根据关键字爬取元器件数据，导出为 Excel
"""

import os
import re
import json
import uuid
import base64
import configparser
from datetime import datetime

import requests
from bs4 import BeautifulSoup
import pandas as pd


# ======================== 配置加载 ========================

def load_config():
    """加载 account.properties 配置"""
    config_path = os.path.join(os.path.dirname(__file__), "config", "account.properties")

    # .properties 文件没有 section header，手动补一个再给 configparser 解析
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = "[DEFAULT]\n" + content

    config = configparser.ConfigParser()
    config.read_string(content)
    return {
        "CompanyName": config.get("DEFAULT", "bom-ai.CompanyName"),
        "AccountName": config.get("DEFAULT", "bom-ai.AccountName"),
        "Password": config.get("DEFAULT", "bom-ai.Password"),
    }


def load_keywords():
    """加载关键字列表"""
    keywords_path = os.path.join(os.path.dirname(__file__), "config", "keywords.txt")
    with open(keywords_path, "r", encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip()]
    return keywords


# ======================== ClientUniqueCode 生成 ========================

def generate_client_code():
    """生成 ClientUniqueCode：uuid -> base64"""
    uid = str(uuid.uuid4())
    # 对 uuid 进行 base64 编码
    code = base64.b64encode(uid.encode("utf-8")).decode("utf-8")
    return code


# ======================== 登录 ========================

def login(account, client_code, session=None):
    """
    登录 bom.ai
    使用 requests.Session 保持登录状态
    返回 (token, session) 元组
    """
    if session is None:
        session = requests.Session()

    url = "https://api.bom.ai/api/v1/user/login"
    headers = {
        "Content-Type": "application/json",
        "origin": "https://bom.ai",
        "referer": "https://bom.ai/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36",
    }

    # 先设置 ClientUniqueCode cookie（URL 编码）
    session.cookies.set("ClientUniqueCode", requests.utils.quote(client_code), domain=".bom.ai")

    payload = {
        "CompanyName": account["CompanyName"],
        "AccountName": account["AccountName"],
        "LoginType": 1,
        "logining": False,
        "PhoneNumber": "",
        "Password": account["Password"],
        "IsFreeLogin": False,
        "IsRemanberPwd": False,
        "ClientCode": client_code,
        "CheckedCompanyName": "",
    }

    resp = session.post(url, headers=headers, json=payload, timeout=30)
    data = resp.json()

    if data.get("Code") != 200:
        raise Exception(f"登录失败: {data.get('Message', '未知错误')}")

    result_data = data["Result"]["Data"]
    if result_data.get("Code") != 0:
        raise Exception(f"登录失败: {result_data.get('Message', '未知错误')}")

    token = result_data["Data"]["Token"]
    company_name = result_data["Data"].get("CompanyName", "")
    user_bg_code = result_data["Data"].get("UserBgCode", "")
    print(f"[登录成功] 账号: {company_name}")

    # 构建 logininfo cookie（URL 编码的 JSON）
    login_info = {
        "LoginType": 1,
        "rememberPassword": False,
        "IsFreeLogin": False,
        "CompanyName": account["CompanyName"],
        "AccountName": account["AccountName"],
        "Password": None,
        "PhoneNumber": "",
        "UserBgCode": user_bg_code,
        "CheckedCompanyName": "",
    }
    login_info_encoded = requests.utils.quote(json.dumps(login_info, separators=(",", ":")))
    session.cookies.set("logininfo", login_info_encoded, domain=".bom.ai")

    # token 也设置到 cookie 中
    session.cookies.set("token", token, domain=".bom.ai")

    return token, session


# ======================== 登录状态检查（数据2用） ========================

def check_login_status(html):
    """
    检查 HTML 页面中是否出现 bom_power_login 元素
    用于判断数据2（云价格）的登录状态
    返回 True 表示已登录，False 表示未登录
    """
    soup = BeautifulSoup(html, "html.parser")
    login_prompt = soup.select_one("p.bom_power_login")
    if login_prompt:
        return False
    return True


# ======================== 爬取数据 ========================

def fetch_keyword_page(keyword, session):
    """
    使用已登录的 session 获取关键字对应的 HTML 页面
    """
    url = f"https://www.bom.ai/components-storage/{requests.utils.quote(keyword)}.html"
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36",
        "referer": "https://www.bom.ai/",
    }

    resp = session.get(url, headers=headers, timeout=30)
    resp.encoding = "utf-8"
    return resp.text


# ======================== 数据解析 ========================

def fetch_basic_info(keyword, token, session):
    """
    通过 API 获取数据1：是否在产、搜索次数、参考价
    GET https://api.bom.ai/asyncapi/v1/getsipartinfos?keyword={keyword}
    返回 (basic_info_dict, is_login_valid) 元组
    当 is_login_valid=False 时表示登录失效，需要重新登录
    """
    result = {
        "是否在产": "",
        "搜索次数": "",
        "参考价": "",
    }

    url = f"https://api.bom.ai/asyncapi/v1/getsipartinfos?keyword={requests.utils.quote(keyword)}"
    headers = {
        "origin": "https://www.bom.ai",
        "referer": "https://www.bom.ai/",
        "authorization": f"JWT {token}",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
    }

    try:
        resp = session.get(url, headers=headers, timeout=30)
        data = resp.json()

        # 检查 isSuccess — 如果为 False 说明登录失效
        if not data.get("Result", {}).get("isSuccess"):
            return result, False

        result_data = data.get("Result", {}).get("Data", {})

        # ProductDetail 中的信息
        product_detail = result_data.get("ProductDetail") or {}

        # 是否在产 — API 可能返回 null，JS 渲染时固定设为"在产"
        in_production = product_detail.get("InProduction")
        if in_production is not None:
            result["是否在产"] = in_production
        else:
            # API 返回 null 时，JS 也会在页面上显示"在产"
            result["是否在产"] = "--"

        # quotePart（同时用于搜索次数和参考价）
        quote_part = result_data.get("quotePart") or {}

        # 搜索次数 — 优先取 RecentSearchCount，其次取 quotePart.SearchCount
        search_count = product_detail.get("RecentSearchCount")
        if search_count is not None:
            result["搜索次数"] = str(search_count)
        else:
            sc = quote_part.get("SearchCount")
            if sc is not None:
                result["搜索次数"] = str(sc)

        # 参考价 — 取 quotePart.UnitPrice
        ref_price = quote_part.get("UnitPrice")
        if ref_price is not None:
            result["参考价"] = f"¥{ref_price}"

        return result, True

    except Exception as e:
        print(f"    [错误] 获取数据1失败: {e}")
        return result, True


def parse_cloud_price(soup):
    """
    解析数据2：云价格列表
    返回一个列表，每个元素是一个字典
    """
    records = []

    # 找到云价格区域
    cloud_section = soup.select_one("#yunexg")
    if not cloud_section:
        return records

    # 查找所有云价格行
    rows = cloud_section.select("ul.alt.bom_cloud_h")
    for row in rows:
        record = {
            "供应商": "",
            "型号": "",
            "品牌": "",
            "封装": "",
            "年份": "",
            "参考价": "",
            "时间": "",
            "数量": "",
            "记价人代码": "",
        }

        # 供应商名称
        supplier_elem = row.select_one("a[id^='cloud_supplier_name_']")
        if supplier_elem:
            record["供应商"] = supplier_elem.text.strip()

        # 从 data-suppliername 属性获取备用供应商名
        aside = row.select_one("aside[data-suppliername]")
        if aside and not record["供应商"]:
            record["供应商"] = aside.get("data-suppliername", "")

        # 型号
        model_elem = row.select_one("div.model a.bomID_Merchant_XH")
        if model_elem:
            record["型号"] = model_elem.text.strip()

        # 品牌
        brand_elem = row.select_one("p.cell-brand.bom_yun_05")
        if brand_elem:
            record["品牌"] = brand_elem.get("title", "").strip()

        # 封装
        package_elem = row.select_one("p.cell-package.bom_yun_13")
        if package_elem:
            record["封装"] = package_elem.get("title", "").strip()

        # 年份
        year_elem = row.select_one("p.cell-batch.bom_yun_15")
        if year_elem:
            record["年份"] = year_elem.text.strip()

        # 参考价 (云价格)
        price_elem = row.select_one("p.bomID_yunGFNUM.bom_showunit_price")
        if price_elem:
            record["参考价"] = price_elem.text.strip()

        # 时间
        time_elem = row.select_one("p.bom_yun_11.bomID_yuntime")
        if time_elem:
            record["时间"] = time_elem.get("title", "").strip()

        # 数量
        qty_elem = row.select_one("p.bom_yun_04.bomID_yunNUM")
        if qty_elem:
            record["数量"] = qty_elem.text.strip()

        # 记价人代码
        sign_elem = row.select_one("p.cell-sign span.bom_yun_sign_contant")
        if sign_elem:
            record["记价人代码"] = sign_elem.text.strip()

        # 尝试从 metadata 脚本中提取更多信息作为补充
        metadata_elem = row.select_one("script.metadata")
        if metadata_elem:
            try:
                meta_soup = BeautifulSoup(metadata_elem.string, "xml")
                if not record["参考价"]:
                    price_tag = meta_soup.find("quotePrice")
                    if price_tag:
                        record["参考价"] = f"￥{price_tag.text}"
                if not record["时间"]:
                    date_tag = meta_soup.find("quoteDate")
                    if date_tag:
                        record["时间"] = date_tag.text
            except Exception:
                pass

        # 检查是否至少有一条有效数据（至少有供应商或型号）
        if any(v for v in record.values()):
            records.append(record)

    return records


def scrape_keyword(keyword, token, session):
    """
    爬取单个关键字的所有数据
    返回 records 列表，登录失效返回 None
    """
    print(f"[爬取中] {keyword} ...")
    html = fetch_keyword_page(keyword, session)

    soup = BeautifulSoup(html, "html.parser")

    # 检查数据2登录状态 — bom_power_login 出现说明登录失效
    if not check_login_status(html):
        print(f"  [警告] {keyword}: 登录已失效（云价格需要重新登录）")
        return None  # 返回 None 表示需要重新登录

    # 检查是否有数据（是否有 No 区段显示）
    no_section = soup.select_one("#bom-data-tool_No")
    if no_section and no_section.get("style", "").replace(" ", "") == "display:block;":
        print(f"  [跳过] {keyword}: 暂无数据")
        return []

    # 通过 API 获取数据1，同时检查登录状态（isSuccess）
    basic_info, is_login_valid = fetch_basic_info(keyword, token, session)
    if not is_login_valid:
        print(f"  [警告] {keyword}: 登录已失效（API isSuccess=False），需要重新登录")
        return None  # 返回 None 表示需要重新登录

    # 解析数据2（云价格）
    cloud_records = parse_cloud_price(soup)

    if not cloud_records:
        # 没有云价格数据，也输出基础信息
        row = {"关键字": keyword}
        row.update(basic_info)
        # 添加空的价格字段
        row.update({
            "供应商": "", "型号": "", "品牌": "", "封装": "",
            "年份": "", "云价格参考价": "", "报价时间": "", "数量": "", "记价人代码": "",
        })
        print(f"  [完成] {keyword}: 基础信息已获取，无云价格数据")
        return [row]

    # 合并数据：每个云价格记录都带上基础信息
    results = []
    for cr in cloud_records:
        row = {"关键字": keyword}
        row.update(basic_info)
        row["供应商"] = cr["供应商"]
        row["型号"] = cr["型号"]
        row["品牌"] = cr["品牌"]
        row["封装"] = cr["封装"]
        row["年份"] = cr["年份"]
        row["云价格参考价"] = cr["参考价"]
        row["报价时间"] = cr["时间"]
        row["数量"] = cr["数量"]
        row["记价人代码"] = cr["记价人代码"]
        results.append(row)

    print(f"  [完成] {keyword}: {len(results)} 条云价格记录")
    return results


# ======================== 导出 Excel ========================

def export_to_excel(all_records, output_dir=None):
    """
    将爬取结果导出为 Excel
    """
    if not all_records:
        print("没有数据可导出")
        return None

    df = pd.DataFrame(all_records)

    # 列顺序
    column_order = [
        "关键字", "是否在产", "搜索次数", "参考价",
        "供应商", "型号", "品牌", "封装", "年份",
        "云价格参考价", "报价时间", "数量", "记价人代码",
    ]
    df = df[column_order]

    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "output")

    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"bom_ai_{timestamp}.xlsx"
    filepath = os.path.join(output_dir, filename)

    # 使用 openpyxl 写入，支持自定义列宽
    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="元器件数据")

        # 调整列宽
        worksheet = writer.sheets["元器件数据"]
        col_widths = {
            "A": 16,  # 关键字
            "B": 10,  # 是否在产
            "C": 10,  # 搜索次数
            "D": 10,  # 参考价
            "E": 30,  # 供应商
            "F": 20,  # 型号
            "G": 16,  # 品牌
            "H": 12,  # 封装
            "I": 8,   # 年份
            "J": 14,  # 云价格参考价
            "K": 16,  # 报价时间
            "L": 12,  # 数量
            "M": 14,  # 记价人代码
        }
        for col_letter, width in col_widths.items():
            worksheet.column_dimensions[col_letter].width = width

    print(f"\n导出成功: {filepath} (共 {len(df)} 条记录)")
    return filepath


# ======================== 主流程 ========================

def main():
    print("=" * 50)
    print("bom.ai 数据爬取工具")
    print("=" * 50)

    # 加载配置
    account = load_config()
    keywords = load_keywords()

    if not keywords:
        print("错误: config/keywords.txt 中没有关键字")
        return

    print(f"关键字数量: {len(keywords)}")

    # 生成 ClientUniqueCode
    client_code = generate_client_code()
    print(f"ClientUniqueCode: {client_code}")

    # 登录，使用 Session 保持登录状态
    token, session = login(account, client_code)

    # 爬取每个关键字
    all_records = []
    i = 0
    relogin_count = 0
    while i < len(keywords):
        keyword = keywords[i]
        print(f"\n[{i + 1}/{len(keywords)}] 处理关键字: {keyword}")
        try:
            records = scrape_keyword(keyword, token, session)

            if records is None:
                # 登录失效，重新登录（复用同一个 session）
                if relogin_count >= 3:
                    print("  [错误] 重试登录超过3次，跳过此关键字")
                    i += 1
                    relogin_count = 0
                    continue
                print("  正在重新登录...")
                relogin_count += 1
                token, session = login(account, client_code, session)
                # 不增加 i，重新爬取当前关键字
                continue

            relogin_count = 0  # 成功爬取，重置重试计数
            all_records.extend(records)
            i += 1
        except Exception as e:
            print(f"  [错误] {keyword}: {e}")
            i += 1

    # 导出 Excel
    print("\n" + "=" * 50)
    export_to_excel(all_records)

    print("=" * 50)
    print("爬取完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()
