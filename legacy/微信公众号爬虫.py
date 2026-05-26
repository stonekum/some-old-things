import requests
from bs4 import BeautifulSoup
import os
import re
from datetime import datetime

# 设置保存路径
save_dir = "/Users/aston/文件夹/爬虫文/微信平台"
os.makedirs(save_dir, exist_ok=True)

# 读取链接列表
with open(os.path.join(save_dir, "/Users/aston/文件夹/微信链接.txt"), "r") as file:
    article_links = [line.strip() for line in file if line.strip()]

# 请求头，模拟浏览器访问
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://mp.weixin.qq.com/"
}

# 遍历每个链接进行爬取
for url in article_links:
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')

            # 提取文章标题
            title_tag = soup.find('h1', class_='rich_media_title')
            title = title_tag.get_text(strip=True) if title_tag else "未命名文章"

            # 清理非法字符
            title = re.sub(r'[\\/:"*?<>|]+', "_", title)

            # 添加时间戳
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            file_name = f"{title}_{timestamp}.txt"

            # 提取文章正文
            content_div = soup.find('div', id='js_content')
            content = content_div.get_text(strip=True) if content_div else "暂无正文内容"

            # 保存文章
            with open(os.path.join(save_dir, file_name), "w", encoding='utf-8') as f:
                f.write(content)

            print(f"✅ 文章《{title}》已保存为 {file_name}！")

            # 下载文章内的图片
            images = content_div.find_all('img') if content_div else []
            img_dir = os.path.join(save_dir, f"{title}_{timestamp}_images")
            os.makedirs(img_dir, exist_ok=True)

            for index, img in enumerate(images):
                img_url = img.get('data-src') or img.get('src')
                if img_url:
                    img_data = requests.get(img_url).content
                    img_path = os.path.join(img_dir, f"image_{index + 1}.jpg")
                    with open(img_path, "wb") as img_file:
                        img_file.write(img_data)

            print(f"✅ 图片已成功下载至 {img_dir} 目录！\n")

        else:
            print(f"❌ 请求失败，状态码：{response.status_code}，链接：{url}")

    except Exception as e:
        print(f"⚠️ 爬取失败：{url}，错误信息：{e}")