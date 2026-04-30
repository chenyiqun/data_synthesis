import requests
import json

url = 'https://runway.devops.xiaohongshu.com/openai/zhipu/paas/v4/web_search'
# url = 'https://runway.devops.sit.xiaohongshu.com/openai/zhipu/paas/v4/web_search'
# url = 'https://runway.devops.xiaohongshu.com/openai/zhipu/paas/v4/web_search_vip'

data = {
    "search_engine": "search_prime",
    "search_query": "关节纹太重怎么办",
    # "request_id": "search_pro_ms",
    "query_rewrite": "false"
}

# data = {
#     "search_engine": "web-reader",
#     "url":"https://open.bigmodel.cn/"
# }

headers = {
    'api-key': '4325d9d15bb045da86b7178f66890bbb'
    # 'api-key': '1e6fc76b069c443cb807de0f4373ae16'
}

import time

try:
    start_time = time.time()
    response = requests.post(url, headers=headers, data=json.dumps(data))
    end_time = time.time()
    
    response.raise_for_status()
    print('请求成功，响应内容：')
    print(response.json())
    print(f'请求耗时: {end_time - start_time:.4f} 秒')
except requests.exceptions.HTTPError as http_err:
    print(f'HTTP错误发生: {http_err}')
except Exception as err:
    print(f'其他错误发生: {err}')