import json
import urllib.request
import redis
import sys

sys.stdout.reconfigure(encoding='utf-8')
base = 'http://127.0.0.1:8001'

r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
req = urllib.request.Request(f'{base}/api/v1/auth/captcha')
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
code = r.get(f"captcha:{data['captcha_id']}")
print('验证码答案:', code)

payload = json.dumps({
    'username': 'root',
    'password': '123456',
    'captcha_id': data['captcha_id'],
    'captcha_code': code,
}).encode()
req = urllib.request.Request(f'{base}/api/v1/auth/login', data=payload, headers={'Content-Type': 'application/json'})
try:
    resp = urllib.request.urlopen(req)
    print('登录成功:', json.loads(resp.read()))
except urllib.error.HTTPError as e:
    print('状态码:', e.code)
    print('响应体:', e.read().decode('utf-8', errors='ignore')[:2000])
