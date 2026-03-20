from curl_cffi import requests as stealth_requests

session = stealth_requests.Session(impersonate='chrome124')
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'x-api-source': 'pc',
    'referer': 'https://shopee.com.br/',
}

url = 'https://shopee.com.br/api/v4/shop/get_shop_items'
params = {
    'shopid': 1744033972,
    'limit': 10,
    'offset': 0,
}

r = session.get(url, params=params, headers=headers, timeout=15)
print('status', r.status_code)
print(r.text[:800])
