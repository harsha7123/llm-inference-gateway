import sys
from openai import OpenAI
# usage: python scripts/test_user.py <api_key> "your question"
client = OpenAI(base_url="http://localhost:8000/v1", api_key=sys.argv[1])
resp = client.chat.completions.create(model="any",
        messages=[{"role": "user", "content": sys.argv[2]}], max_tokens=200)
print(resp.choices[0].message.content)