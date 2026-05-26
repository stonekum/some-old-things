import os
import re
import csv
import requests
import json

# ----------------------
# 核心函数：调用API提取结构化数据（与之前相同）
# ----------------------

def extract_topic_info(api_key, text):
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    prompt = f'''
        请从文本中提取核心信息，按以下JSON格式返回：
        {{
            "date": ["日期（YYYY-MM-DD）|无"],
            "key_sentences": ["直接影响主题的完整句子", "不少于3条"],
            “title”:"从文案里取一个合适的标题"，
            "style": {{
                "type": "海外校园",
                "audience": "高中生/大学生"
                    }},
            "platforms": ["INSTAGRAM","LINKEDIN","TWITTER","FACEBOOK"],
            "emoji": {{
                "flag": "如文案中提到除了中国以外的国家为True，没提到则False",
                "suggestions": ["相关表情符号"]
      }}
        }}

        处理规则：
        1. 日期提取失败时返回["无"]
        2. 关键句子需保持原文完整性，禁用缩写
        3. 每个句子长度控制在15-25个汉字
        4. 优先选择包含动词的陈述句
        5. 排除疑问句和感叹句
        6. 自动统计处理耗时（精确到秒）和字符总数
        7. 如遇中英混杂句子，保留原始形态
        8. Emoji建议需符合国际学生社交习惯
        9. 如果自带的文案有姓名，请不要带上，有职务的话写出职务，没职务的话，直接隐去，写为我校/对方

        文本内容：
        {text}
            '''

    data = {
        "model": "deepseek-chat",
        "messages": [{
                "role": "system",
                "content": "你是一位文本大纲生成专家，擅长根据用户的需求创建一个有条理且易于扩展成完整文章的大纲，你拥有强大的主题分析能力，能准确提取关键信息和核心要点。具备丰富的文案写作知识储备，熟悉各种文体和题材的文案大纲构建方法。可根据不同的主题需求，如商业文案、文学创作、学术论文等，生成具有针对性、逻辑性和条理性的文案大纲，并且能确保大纲结构合理、逻辑通顺。该大纲应该包含以下部分：\n引言：介绍主题背景，阐述撰写目的，并吸引读者兴趣。\n主体部分：第一段落：详细说明第一个关键点或论据，支持观点并引用相关数据或案例。\n第二段落：深入探讨第二个重点，继续论证或展开叙述，保持内容的连贯性和深度。\n第三段落：如果有必要，进一步讨论其他重要方面，或者提供不同的视角和证据。\n结论：总结所有要点，重申主要观点，并给出有力的结尾陈述，可以是呼吁行动、提出展望或其他形式的收尾。\n创意性标题：为文章构思一个引人注目的标题，确保它既反映了文章的核心内容又能激发读者的好奇心。"
        },
                {"role": "user", 
                 "content": prompt}],
        "temperature": 1.0
    }

    response = requests.post(url, json=data, headers=headers).json()

    try:
        raw_content = response['choices'][0]['message']['content']
        
        # 1. 去掉 Markdown 代码块
        json_content = re.sub(r'```json\s*|\s*```', '', raw_content).strip()

        # 2. 解析 JSON
        parsed_data = json.loads(json_content)

        # 3. **手动检查 DeepSeek 返回的 `date` 字段**
        if not parsed_data.get("date") or any("2023-" in d for d in parsed_data["date"]):
            parsed_data["date"] = ["无"]

        return parsed_data

    except Exception as e:
        print("解析失败，请检查API返回:", response, "错误:", str(e))
        return None

# ----------------------
# 主流程：处理单个TXT文件 → 生成对应CSV
# ----------------------
def process_single_txt(api_key, input_txt_path):
    """
    修改后的函数：
    - 不再写CSV，而是返回本TXT文件对应的所有行数据（列表）。
    """
    with open(input_txt_path, 'r', encoding='utf-8') as f:
        raw_text = f.read()
    
    # 按 "---" 分割文本为多个记录
    records = re.split(r'\-{3,}', raw_text)
    
    row_list = []  # 用来收集本TXT对应的所有记录
    for text in records:
        text = text.strip()
        if not text:
            continue
        
        # 调用你的解析函数
        # 调用解析函数（需适配新JSON结构）
        result = extract_topic_info(api_key, text)
        if result:
            row_data = {
                'Date': ', '.join(result['date']) if result['date'] else "无",  # 规则1
                'Key_Sentences': '；'.join(result['key_sentences'][:3]),        # 规则2
                'Style_Type': result['style']['type'],                       # 固定字段
                'Audience': result['style']['audience'],  
                'Title': result['title'],
                'Platforms': ', '.join(result['platforms']),                # 平台字段标准化
                'Emoji_Flag': str(result['emoji']['flag']).lower(),  # 是否需要Emoji
                'Emoji_Suggestions': ', '.join(result['emoji']['suggestions'])  
                }
            row_list.append(row_data)

        return row_list

def batch_process_txt(api_key, input_dirs, output_dir):
    """
    批量处理多个输入目录下的所有TXT文件，并将所有结果整合到 output_dir 下的同一个 CSV 文件(如combined.csv)里。
    """
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)

    # 在这里定义合并后的 CSV 文件名
    combined_csv_path = os.path.join(output_dir, "整合.csv")
    
    # 定义 CSV 列字段
    fieldnames = ['Date', 'Key_Sentences', 'Style_Type', 
                  'Audience', 'Platforms', 'Emoji_Flag','Title', 
                  'Emoji_Suggestions']
    
    # 先以写模式打开合并CSV，写表头
    with open(combined_csv_path, 'w', newline='', encoding='utf-8') as combined_file:
        writer = csv.DictWriter(combined_file, fieldnames=fieldnames)
        writer.writeheader()

        # 遍历多个输入文件夹
        for input_dir in input_dirs:
            print(f"📂 正在处理目录: {input_dir}")
            
            # 遍历当前目录下的所有TXT文件
            for filename in os.listdir(input_dir):
                file_path = os.path.join(input_dir, filename)

                # 确保是文件而不是子目录
                if os.path.isdir(file_path):
                    print(f"❌ 跳过子目录: {file_path}")
                    continue

                # 仅处理TXT文件
                if filename.endswith(".txt"):
                    print(f"📄 处理文件: {file_path}")
                    try:
                        # 获取当前 TXT 文件的所有解析行
                        rows = process_single_txt(api_key, file_path)
                        # 将这些行写入合并后的 CSV
                        for row in rows:
                            writer.writerow(row)
                        print(f"✅ 处理成功: {filename}，共 {len(rows)} 条记录")
                    except Exception as e:
                        print(f"❌ 处理失败: {filename}，错误信息: {str(e)}")

    print(f"所有TXT文件处理完成，已合并输出到: {combined_csv_path}")

# 运行处理多个目录
API_KEY = "sk-REDACTED-rotate-me"
INPUT_DIRS = [
    "/Users/aston/文件夹/爬虫文/微信平台", 
    "/Users/aston/文件夹/爬虫文/校内新闻网"
]
OUTPUT_DIR = "/Users/aston/文件夹/爬虫文/CSV输出"

batch_process_txt(API_KEY, INPUT_DIRS, OUTPUT_DIR)