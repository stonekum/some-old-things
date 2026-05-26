#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jan 27 11:08:53 2025

@author: aston
"""

import requests

def download_video(url, output_path):
    # 设置请求头，模仿 Safari 浏览器
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Version/15.5 Safari/537.36",
        "Referer": "https://mp.weixin.qq.com/",  # 微信公众号的页面作为来源
        "Accept": "*/*",
        "Connection": "keep-alive",
    }
    
    try:
        # 发送 GET 请求
        response = requests.get(url, headers=headers, stream=True)
        
        # 检查响应状态
        if response.status_code == 200:
            print("开始下载视频...")
            # 写入文件
            with open(output_path, "wb") as video_file:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        video_file.write(chunk)
            print(f"视频下载完成，保存为: {output_path}")
        else:
            print(f"下载失败，状态码: {response.status_code}")
    except Exception as e:
        print(f"发生错误: {e}")

# 视频 URL
video_url = "https://mpvideo.qpic.cn/0bc35yaamaaazqak6ievrntvb3wda3xaabqa.f10002.mp4?dis_k=31ee7a3bbcda2828f6882add3d7e547c&dis_t=1737945479&play_scene=10120&auth_info=OpfmmclqHHljjtOf81EMOG07SDZlZUJsZUx+HAVzd0UFFTokYUIHNBRwByxsOAEYeTE=&auth_key=aaf09589c0f2c6a7bd0ceb08ce6a9da4&vid=wxv_3829720667247017985&format_id=10002&support_redirect=0&mmversion=false"

# 输出文件路径
output_file = "/Users/aston/Downloads/downloaded_video.mp4"

# 调用函数下载视频
download_video(video_url, output_file)