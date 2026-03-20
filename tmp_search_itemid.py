from curl_cffi import requests as stealth_requests

url = 'https://shopee.com.br/totalmenteseu'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

r = stealth_requests.get(url, headers=headers, impersonate='chrome124', timeout=15)
print('status', r.status_code)
print('contains itemid', 'itemid' in r.text)
print('first occurrence:', r.text.find('itemid'))
print('snippet:', r.text[r.text.find('itemid')-50:r.text.find('itemid')+150])
