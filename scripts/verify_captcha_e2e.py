import base64
import json
import re
import urllib.request
from pathlib import Path

import redis
import sys

sys.stdout.reconfigure(encoding='utf-8')

base = 'http://127.0.0.1:8001'
# 验证码图片保存路径（脚本所在目录）
CAPTCHA_IMAGE_PATH = Path(__file__).resolve().parent / 'captcha_sample.png'


def request_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body.decode('utf-8', errors='ignore')}


def main():
    # 1. 获取验证码
    status, data = request_json(f'{base}/api/v1/auth/captcha')
    assert status == 200, f'获取验证码失败: {status}'
    captcha_id = data['captcha_id']
    image_base64 = data['image_base64']
    print(f'验证码 ID: {captcha_id}')

    # 2. 保存验证码图片到本地，便于人工查看
    match = re.match(r'data:image/png;base64,(.+)', image_base64)
    if match:
        img_bytes = base64.b64decode(match.group(1))
        CAPTCHA_IMAGE_PATH.write_bytes(img_bytes)
        print(f'验证码图片已保存: {CAPTCHA_IMAGE_PATH}')

    # 3. 从 Redis 读取正确答案
    r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    code = r.get(f'captcha:{captcha_id}')
    print(f'Redis 中验证码答案: {code}')

    # 4. 用错误验证码登录
    payload = {
        'username': 'root',
        'password': '123456',
        'captcha_id': captcha_id,
        'captcha_code': 'ZZZZ',
    }
    status, result = request_json(
        f'{base}/api/v1/auth/login',
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'},
    )
    print(f'错误验证码登录: {status} {result}')
    assert status == 400, '错误验证码应返回 400'

    # 5. 重新获取验证码
    status, data = request_json(f'{base}/api/v1/auth/captcha')
    captcha_id = data['captcha_id']
    code = r.get(f'captcha:{captcha_id}')
    print(f'新验证码答案: {code}')

    # 6. 用正确验证码登录
    payload = {
        'username': 'root',
        'password': '123456',
        'captcha_id': captcha_id,
        'captcha_code': code,
    }
    status, result = request_json(
        f'{base}/api/v1/auth/login',
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'},
    )
    print(f'正确验证码登录: {status} {result.get("message")}')
    assert status == 200, '正确验证码应登录成功'

    print('E2E 验证码流程验证通过')


if __name__ == '__main__':
    main()
