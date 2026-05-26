import os
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
import re

def convert_date(raw_date):
    """将'2023年12月20日'转换为'2023-12-20'"""
    try:
        return datetime.strptime(raw_date.strip(), "%Y年%m月%d日").strftime("%Y-%m-%d")
    except Exception as e:
        print(f"日期转换失败: {raw_date} - {str(e)}")
        return None

def fetch_all_article_links(pages=2):
    """获取多页文章的所有链接"""
    all_links = []
    base_url = "https://news.sjtu.edu.cn/jdyw/index.html"
    
    for page in range(1, pages+1):
        print(f"正在抓取第 {page} 页...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        try:
            # 处理分页URL（需要根据实际分页规则调整）
            if page == 1:
                url = base_url
            else:
                url = f"https://news.sjtu.edu.cn/jdyw/{page}.html"
                
            response = requests.get(url, headers=headers)
            response.encoding = 'utf-8'
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 根据实际结构调整选择器
                for item in soup.select('li > a'):  # 根据网页结构提取所有文章的链接
                    link = item.get('href')
                    if link and link.startswith('/jdyw/'):
                        full_link = f"https://news.sjtu.edu.cn{link}"
                        all_links.append(full_link)
                
                time.sleep(3)  # 页间延迟
        except Exception as e:
            print(f'第 {page} 页抓取失败：{str(e)}')
            
    return all_links
 

def download_article(article_url):
    
    def sanitize_filename(filename):
        """去除文件名中的非法字符"""
        
        return re.sub(r'[\\/*?:"<>|]', "_", filename)
    
    """根据文章链接下载内容"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://news.sjtu.edu.cn/'  # 添加 Referer 头绕过一些限制
    }
    
    try:
        response = requests.get(article_url, headers=headers)
        response.encoding = 'utf-8'
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 提取文章标题、日期和正文内容
            title_tag = soup.select_one('#ivs_title')  # 标题选择器
            content_div = soup.select_one('.Article_content')  # 正文选择器
            date_tag = soup.select_one('#ivs_date.time')  # 日期选择器
            
            title = title_tag.text.strip() if title_tag else "未知标题"
            pub_date = convert_date(date_tag.text) if date_tag else "未知日期"
            
            # 创建日期目录
            save_dir = f'/Users/aston/Downloads/爬虫文/校内新闻网/{pub_date}'
            os.makedirs(save_dir, exist_ok=True)
            
            # 处理文件名中的非法字符
            sanitized_title = sanitize_filename(title)
            filename = f'{save_dir}/{sanitized_title}.txt'
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"标题：{title}\n")
                f.write(f"日期：{pub_date}\n")
                f.write(f"链接：{article_url}\n\n")
                f.write(content_div.get_text() if content_div else "未找到正文内容")
            
            # 获取图片 URL 基于文章 URL 中的日期部分
            date_str = article_url.split('/')[-2]  # 提取文章 URL 中的日期（如 20250126）
            month = date_str[:6]  # 获取月份部分（如 202501）
            day = date_str[6:]  # 获取日期部分（如 26）
            
            img_tags = content_div.select('img') if content_div else []
            for idx, img in enumerate(img_tags):
                img_url = img.get('src')
                if img_url:
                    # 拼接完整的图片URL
                    if img_url.startswith('/'):
                        img_url = f'https://news.sjtu.edu.cn{img_url}'
                    elif not img_url.startswith('http'):
                        img_url = f'https://news.sjtu.edu.cn{img_url}'
                    
                    # 如果 URL 是相对路径，拼接为绝对路径
                    if img_url.startswith('/resource/upload/'):
                        img_url = f'https://news.sjtu.edu.cn{img_url}'
                    
                    # 这里进行图片 URL 拼接
                    if 'resource/upload' in img_url:
                        img_url = f'https://news.sjtu.edu.cn/resource/upload/{month}/{img_url.split("/")[-1]}'
                    
                    # 检查是否为有效的完整 URL
                    if not img_url.startswith('https://news.sjtu.edu.cn') and not img_url.startswith('https://tzb.sjtu.edu.cn'):
                        print(f"无效图片 URL: {img_url}")
                        continue
                    
                    try:
                        # 下载图片
                        img_response = requests.get(img_url, headers=headers, stream=True)
                        if img_response.status_code == 200:
                            # 保存图片
                            img_data = img_response.content
                            if img_data:  # 确保图片数据不为空
                                img_name = f'{save_dir}/{sanitized_title}_image_{idx+1}.jpg'
                                with open(img_name, 'wb') as img_file:
                                    img_file.write(img_data)
                                print(f"图片保存成功：{img_name}")
                            else:
                                print(f"图片为空：{img_url}")
                        else:
                            print(f"图片下载失败：{img_url}")
                    except Exception as e:
                        print(f'图片下载异常：{str(e)}')
            return True
        else:
            print(f"请求失败，状态码：{response.status_code}")
            return False
    except Exception as e:
        print(f'下载异常：{str(e)}')
        return False

def batch_crawl():
    """批量爬取模式"""
    article_links = fetch_all_article_links(pages=2)  # 修改pages参数控制抓取页数
    
    total = len(article_links)
    print(f"共发现 {total} 篇文章")
    
    success_count = 0
    for idx, article_url in enumerate(article_links, 1):
        print(f"正在处理第 {idx}/{total} 篇：{article_url}")
        if download_article(article_url):
            success_count += 1
        time.sleep(2)  # 增加请求间隔
        
    print(f"任务完成，成功下载 {success_count}/{total} 篇文章")

if __name__ == "__main__":
    batch_crawl()