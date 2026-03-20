from curl_cffi import requests as stealth_requests

session = stealth_requests.Session(impersonate='chrome124')
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'x-api-source': 'pc',
    'referer': 'https://shopee.com.br/',
}

item_id = 58202207706
shop_id = 1676487555

for filter_val in [1, 0]:
    url = 'https://shopee.com.br/api/v2/item/get_ratings'
    params = {
        'itemid': item_id,
        'shopid': shop_id,
        'limit': 20,
        'filter': filter_val,
    }
    r = session.get(url, params=params, headers=headers, timeout=15)
    print('filter', filter_val, 'status', r.status_code)
    try:
        data = r.json()
        print('  total_ratings', data.get('data', {}).get('rating_total'))
        print('  ratings_length', len(data.get('data', {}).get('ratings', [])))
    except Exception as e:
        print('  parse error', e)
