import os
import csv
import time
import json
import requests
from docx import Document

# ---------- DeepSeek API 配置 ----------
API_KEY = "sk-REDACTED-rotate-me"  # 请替换为你的真实 API_KEY
API_URL = "https://api.deepseek.com/v1/chat/completions"


# ---------- 文件路径配置 ----------
# 请根据你的实际情况替换以下路径
INPUT_CSV_PATH = "/Users/aston/文件夹/爬虫文/CSV输出/英文版总结.csv"  
OUTPUT_DOCX_PATH = "/Users/aston/文件夹/爬虫文/CSV输出/result.docx"
HISTORY_DIR_PATH = "/Users/aston/文件夹/爬虫文/历史案例"

def load_history_from_folder(folder_path, max_files=5, max_samples_per_file=3):
    total_samples = 0 
    """
    遍历文件夹加载历史样本（支持嵌套子目录）
    参数说明（参考）：
    - max_files: 最大读取文件数（避免内存过载）
    - max_samples_per_file: 单个文件最大样本数
    """
    history_samples = []
    processed_files = 0
    
    # 遍历文件夹及子目录（参考）
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if processed_files >= max_files:
                return history_samples
                
            file_path = os.path.join(root, file)
            try:
                # 调用原有单文件加载逻辑
                samples = load_history_samples(file_path, max_samples_per_file)
                history_samples.extend(samples)
                processed_files += 1
            except Exception as e:
                print(f"⚠️ 文件 {file_path} 加载失败: {e}")
                
    samples = load_history_samples(file_path, max_samples_per_file)
    total_samples += len(samples)  # 统计总数
            
    print(f"✅ 总计加载历史推文样本: {total_samples}条")
    return history_samples

def load_history_samples(file_path, max_samples=3):
    """
    读取历史文案文件（支持JSON/CSV/TXT）
    返回格式: ["标题1: 摘要文本...", "标题2: 摘要文本..."]
    """
    try:
        if file_path.endswith('.json'):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return [f"{item['title']}: {item['content'][:100]}..." for item in data[:max_samples]]
        
        elif file_path.endswith('.csv'):
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                return [f"{row['Title']}: {row['Content'][:100]}..." for row in reader][:max_samples]
        
        else:  # 纯文本处理
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
                return lines[:max_samples]
    
    except Exception as e:
        print(f"⚠️ 历史文案加载失败: {e}")
        return []


# ---------- 生成 Prompt 的函数 ----------
def generate_prompt(Key_Sentences, Title, Platform, Emoji_suggestions, 
                    Date, Emoji_Flag, Audience, history_samples=[]):
    """
    整合历史文案参考（参考）
    """
    style_reference = "\n".join(history_samples) if history_samples else "无历史参考"
    
    return f'''
    [历史风格参考]（禁止复制内容，仅继承以下要素）:
    {style_reference}
    
    Generate an English social media post **strictly** based on the provided details.  
    - **DO NOT add fictional names, events, or programs.**  
    - **DO NOT include explanations, prefaces, or additional notes.**  
    - **Only output: [Post Title] + [Post Content]**  
    - **Output must be plain text with no special characters like **, #, or >**

    **[Post Title]**  
    {Title}  

    **[Post Content]**  
    Write a concise {Platform} post (220-280 words) integrating these elements:  
    - **Main Theme**: [{Key_Sentences}]  
    - **Target Audience**: {Audience}  
    - **Platform-Specific Style**: {{
        Instagram: "Visual storytelling + emojis {Emoji_suggestions}",
        Twitter: "Concise statements + relevant hashtags",
        Facebook: "Detailed narratives"
    }}  
    - **Emoji Usage**: {Emoji_Flag} ({", ".join(Emoji_suggestions) if Emoji_Flag else "none"})  
    - **Date Context**: {"Include " + Date if Date else "Omit date references"}  

    **Structure:**    
    1）Call-to-action (platform-specific engagement)  
    2）最多分成3段
    3）尽量用简单易懂的词汇，避免使用生涩难懂的词汇，符合英文表达习惯
    '''  


# ---------- 调用 DeepSeek API 函数 ----------
def call_deepseek_api(prompt, retries=3, delay=15):
    """
    调用 DeepSeek API 生成文案，使用 reasoner 模型。
    若请求失败则重试，最后若全部失败则返回空字符串。
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
        "Connection": "keep-alive" 
    }
    ##system_prompt= "asfadfadf"
    # 使用 reasoner 模型
    data = {
        "model": "deepseek-reasoner",  # 如果实际模型名称不同，请改为与 DeepSeek 提供的对应值
        "messages": [
            ##{"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
            ],
    }
    
    for attempt in range(retries):
        
        try:
            response = requests.post(API_URL, json=data, headers=headers, timeout=180)
            response.raise_for_status()
            response_json = response.json()
        
        # 提取生成的文案和 Token 使用量
            content = response_json["choices"][0]["message"]["content"]
            usage = response_json.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            return content, prompt_tokens, completion_tokens
        
        except requests.exceptions.RequestException as e:
            print(f"⚠️ API 请求失败 (尝试 {attempt+1}/{retries})，错误: {e}")
            time.sleep(delay)  
    print("❌ API 失败，返回空文案")
    return "", 0, 0

# ---------- 处理 CSV 并写到 Word 文档 ----------
def process_csv_and_write_to_word(input_csv, output_docx, history_samples):
    """
    读取 CSV 文件中每一行的主题、子主题、平台、推荐表情符号、日期、表情符号模式、受众，
    调用 API 生成文案，并把结果写到 Word 文档中。
    """
    # 初始化一个空的 Word 文档
    start_time = time.time()
    doc = Document()
    total_prompt_tokens = 0
    total_completion_tokens = 0
    history_samples = load_history_from_folder(HISTORY_DIR_PATH)
    
    with open(input_csv, 'r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        
        for idx, row in enumerate(reader, start=1):

            # 从 CSV 中获取字段
            key_Sentences = row.get("Key_Sentences", "").strip()
            title = row.get("Title", "").strip()
            sub_topics = row.get("Sub_Topics", "").split(", ") if row.get("Sub_Topics") else []
            platform = row.get("Platform", "INSTAGRAM").strip()
            emoji_suggestions = row.get("Emoji_Suggestions", "").split(", ") if row.get("Emoji_Suggestions") else []

            # 新增字段
            date = row.get("Date", "").strip()
            emoji_flag = row.get("Emoji_Flag", "").strip()
            audience = row.get("Audience", "").strip()

            # 如果没有主题，则跳过该行
            if not title:
                print(f"⚠️ 第 {idx} 行无主题，已跳过。")
                continue

            # 打印提示，便于调试
            print(f"📢 正在生成 {platform} 文案 | 主题: {title} | 子主题: {sub_topics} | 日期: {date} | 受众: {audience}")

            # 生成 Prompt 并调用 API
            prompt = generate_prompt(key_Sentences, platform,title, emoji_suggestions, date, emoji_flag, audience,history_samples)
            generated_text = call_deepseek_api(prompt)
            generated_text, prompt_tokens, completion_tokens = call_deepseek_api(prompt)
            total_prompt_tokens += prompt_tokens
            total_completion_tokens += completion_tokens

            # 将结果写入 Word 文档
            doc.add_heading(f"{idx}. {title}", level=2)
            doc.add_paragraph("生成文案：")
            doc.add_paragraph(generated_text)

            # 每行内容结束后可选择插入分页符，便于区分
            doc.add_page_break()

    # 保存 Word 文档
    end_time = time.time()
    print(f"""
          ✅ 任务完成！
          ⏱️ 总运行时长: {end_time - start_time:.2f} 秒
          🪙 Token 使用统计:
              - 输入 Token: {total_prompt_tokens}
              - 输出 Token: {total_completion_tokens}
              - 总消耗: {total_prompt_tokens + total_completion_tokens}
              """)
    doc.save(output_docx)
    print(f"✅ 所有文案已写入 {output_docx}")

# ---------- 主程序入口 ----------
if __name__ == "__main__":
    process_csv_and_write_to_word(INPUT_CSV_PATH, OUTPUT_DOCX_PATH, HISTORY_DIR_PATH)