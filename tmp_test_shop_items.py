from curl_cffi import requests as stealth_requests

session = stealth_requests.Session(impersonate='chrome124')
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'x-api-source': 'pc',
    'referer': 'https://shopee.com.br/',
}
shopid = 1744033972

url = 'https://shopee.com.br/api/v4/search/search_items'
params = {
    'by': 'sales',
    'limit': 20,
    'match_id': shopid,
    'newest': 0,
    'order': 'desc',
    'keyword': ''
}

r = session.get(url, params=params, headers=headers, timeout=15)
print('status', r.status_code)
try:
    data = r.json()
    print('keys', list(data.keys()))
    print('items count', len(data.get('items', [])))
    if data.get('items'):
        item = data['items'][0]
        print('sample item keys', list(item.keys()))
except Exception as e:
    print('parse error', e)
