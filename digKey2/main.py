"""
Digikey 爬虫主入口
功能：批量读取关键词，爬取现货数量，导出Excel
"""

from spider import DigikeySpider
from datetime import datetime


def main():
    spider = DigikeySpider()

    # 读取关键词配置文件
    keywords = spider.load_keywords('config/keywords.txt')
    print(f"已加载 {len(keywords)} 个关键词\n")

    # 爬取数据
    results = spider.crawl(keywords)

    # 导出Excel（文件名带时间戳）
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f'output/digikey_stock_{timestamp}.xlsx'
    spider.export_to_excel(results, output_file)
    print("\n爬取完成!")


if __name__ == '__main__':
    main()
