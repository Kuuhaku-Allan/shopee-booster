import requests
from urllib.parse import quote
import random

prompt = quote('school desk pastel background')
urls = [
    f'https://image.pollinations.ai/prompt/{prompt}?model=flux&width=512&height=512&seed={random.randint(1,9999)}',
    f'https://image.pollinations.ai/prompt/{prompt}?model=turbo&width=512&height=512&seed={random.randint(1,9999)}',
    f'https://gen.pollinations.ai/image/{prompt}?model=flux&width=512&height=512&seed={random.randint(1,9999)}',
    f'https://gen.pollinations.ai/image/{prompt}?model=nanobanana&width=512&height=512&seed={random.randint(1,9999)}',
]

print("--- DIAGNÓSTICO POLLINATIONS ---")
for url in urls:
    try:
        r = requests.get(url, timeout=30)
        print(f"{r.status_code} | {r.headers.get('Content-Type', '?')} | {url[:80]}")
    except Exception as e:
        print(f"ERRO: {e} | {url[:80]}")
print("--- FIM ---")
