import os
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
import re
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 创建带重试机制的requests.Session
session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
session.mount('http://', adapter)
session.mount('https://', adapter)

def convert_date(raw_date):
    """将'2023年12月20日'转换为'2023-12-20'"""
    try:
        return datetime.strptime(raw_date.strip(), "%Y年%m月%d日").strftime("%Y-%m-%d")
    except Exception as e:
        print(f"日期转换失败: {raw_date} - {str(e)}")
        return None

def read_links(file_path):
    """从文件中读取所有链接"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    except Exception as e:
        print(f"读取链接文件失败: {str(e)}")
        return []

# 图片下载函数
def download_image(img_url, headers, save_dir, sanitized_title, idx):
    try:
        img_response = session.get(img_url, headers=headers, stream=True, timeout=10)
        if img_response.status_code == 200:
            img_data = img_response.content
            if img_data:
                img_name = os.path.join(save_dir, f"{sanitized_title}_image_{idx+1}.jpg")
                with open(img_name, 'wb') as img_file:
                    img_file.write(img_data)
                logging.info(f"图片保存成功：{img_name}")
            else:
                logging.warning(f"图片为空：{img_url}")
        else:
            logging.warning(f"图片下载失败：{img_url} 状态码：{img_response.status_code}")
    except Exception as e:
        logging.error(f'图片下载异常：{img_url} - {str(e)}')

def download_article(article_url):
    def sanitize_filename(filename):
        """去除文件名中的非法字符"""
        return re.sub(r'[\\/*?:"<>|]', "_", filename)
    
    """根据文章链接下载内容"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://news.sjtu.edu.cn/'  # 添加 Referer 头绕过一些限制
    }
    
    # 指定存储路径
    save_dir = "/Users/aston/文件夹/爬虫文/校内新闻网"
    os.makedirs(save_dir, exist_ok=True)  # 确保目录存在
    
    try:
        response = session.get(article_url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 提取文章标题、日期和正文内容
            title_tag = soup.select_one('#ivs_title')  # 标题选择器
            content_div = soup.select_one('.Article_content')  # 正文选择器
            date_tag = soup.select_one('#ivs_date.time')  # 日期选择器
            
            title = title_tag.text.strip() if title_tag else "未知标题"
            pub_date = convert_date(date_tag.text) if date_tag else "未知日期"
            
            # 处理文件名中的非法字符
            sanitized_title = sanitize_filename(title)
            filename = os.path.join(save_dir, f"{sanitized_title}.txt")
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"标题：{title}\n")
                f.write(f"日期：{pub_date}\n")
                f.write(f"链接：{article_url}\n\n")
                f.write(content_div.get_text() if content_div else "未找到正文内容")
            
            # 下载图片
            img_tags = content_div.select('img') if content_div else []
            for idx, img in enumerate(img_tags):
                img_url = img.get('src')
                if img_url:
                    # 统一处理图片URL
                    if img_url.startswith('http'):
                        full_img_url = img_url
                    elif img_url.startswith('/'):
                        full_img_url = f'https://news.sjtu.edu.cn{img_url}'
                    else:
                        full_img_url = f'https://news.sjtu.edu.cn/{img_url}'
                    download_image(full_img_url, headers, save_dir, sanitized_title, idx)
            return True
        else:
            logging.warning(f"请求失败，状态码：{response.status_code}")
            return False
    except Exception as e:
        logging.error(f'下载异常：{str(e)}')
        return False

def batch_crawl(file_path):
    """批量爬取模式"""
    article_links = read_links(file_path)
    
    total = len(article_links)
    logging.info(f"共发现 {total} 个链接")
    
    success_count = 0
    for idx, article_url in enumerate(article_links, 1):
        logging.info(f"正在处理第 {idx}/{total} 篇：{article_url}")
        if download_article(article_url):
            success_count += 1
        time.sleep(2)  # 增加请求间隔
        
    logging.info(f"任务完成，成功下载 {success_count}/{total} 篇文章")

if __name__ == "__main__":
    file_path = '/Users/aston/文件夹/校内新闻网链接.txt'
    batch_crawl(file_path)