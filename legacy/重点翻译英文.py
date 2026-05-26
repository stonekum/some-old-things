import csv
import json
import requests
import time
from tqdm import tqdm

def translate_row(api_key, row):
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Connection": "keep-alive" 
    }
    
    system_prompt = """你是一个中英文翻译专家，将用户输入的中文翻译成英文，或将用户输入的英文翻译成中文。对于非中文内容，它将提供中文翻译结果。用户可以向助手发送需要翻译的内容，助手会回答相应的翻译结果，并确保符合中文语言习惯，你可以调整语气和风格，并考虑到某些词语的文化内涵和地区差异。同时作为翻译家，需将原文翻译成具有信达雅标准的译文。"信" 即忠实于原文的内容与意图；"达" 意味着译文应通顺易懂，表达清晰；"雅" 则追求译文的文化审美和语言的优美。目标是创作出既忠于原作精神，又符合目标语言文化和读者审美的翻译。请将以下JSON中的每个值翻译成英文。保持JSON结构，只返回翻译后的JSON。格式示例：
    {"Date": "翻译结果", "Key_Sentences": "翻译结果"...}"""
    
    user_prompt = json.dumps(
        {k: v for k, v in row.items() if k in ["Date", "Key_Sentences", "Style_Type", "Audience", "Title"]},
        ensure_ascii=False
    )

    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    }

    max_retries = 3
    retry_delay = 15  # 秒

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(url, headers=headers, json=data, timeout=180)
            response.raise_for_status()
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return json.loads(content)
            
        except requests.exceptions.HTTPError as e:
            error_code = response.status_code if response is not None else "N/A"
            print(f"\nHTTP错误 [{error_code}]，第 {attempt}/{max_retries} 次重试（15秒后重试）...")
            time.sleep(retry_delay)
            
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"\n请求失败 [{str(e)}]，第 {attempt}/{max_retries} 次重试（15秒后重试）...")
            time.sleep(retry_delay)
            
        except Exception as e:
            print(f"\n未知错误 [{str(e)}]，第 {attempt}/{max_retries} 次重试（15秒后重试）...")
            time.sleep(retry_delay)

    print("\n重试3次后仍失败，保留原文")
    return {}  # 返回空字典保持原有数据

def translate_csv(input_csv, output_csv, api_key):
    with open(input_csv, "r", encoding="utf-8") as infile:
        reader = csv.DictReader(infile)
        rows = list(reader)
        total_rows = len(rows)

    with open(output_csv, "w", encoding="utf-8", newline="") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
        writer.writeheader()

        progress_bar = tqdm(rows, desc="翻译进度", unit="row")
        for row in progress_bar:
            translated = translate_row(api_key, row)
            # 仅更新成功翻译的字段
            for field in ["Date", "Key_Sentences", "Style_Type", "Audience", "Title"]:
                if field in translated:
                    row[field] = translated[field]
            writer.writerow(row)
            progress_bar.set_postfix_str(f"最新处理: {row.get('Title', '')[:20]}...")

if __name__ == "__main__":
    API_KEY = "sk-REDACTED-rotate-me"  # 请替换为你的 DeepSeek API Key
    input_file = "/Users/aston/文件夹/爬虫文/CSV输出/整合.csv"  # 请替换为实际输入文件路径
    output_file = "/Users/aston/文件夹/爬虫文/CSV输出/英文版总结.csv"
    
    translate_csv(input_file, output_file, API_KEY)
    print("翻译完成，结果已保存。")
