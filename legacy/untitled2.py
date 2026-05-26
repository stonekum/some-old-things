

from openai import OpenAI

client = OpenAI(api_key="sk-REDACTED-rotate-me", base_url="https://api.deepseek.com/v1")

messages = [{"role": "user", "content": "9.11 and 9.8, which is greater?"}]
response = client.chat.completions.create(
    model="deepseek-reasoner",
    messages=messages
)

print(response)  # 检查返回结果