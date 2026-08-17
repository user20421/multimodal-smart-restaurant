import urllib.request
import json
import redis
import sys

sys.stdout.reconfigure(encoding='utf-8')

base = 'http://127.0.0.1:8002'


def request_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main():
    # 获取验证码
    status, data = request_json(f'{base}/api/v1/auth/captcha')
    print('获取验证码:', status, data['captcha_id'])
    print('图片长度:', len(data['image_base64']))

    r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    code = r.get(f"captcha:{data['captcha_id']}")
    print('Redis 正确答案:', code)

    # 错误验证码
    payload = {
        'username': 'root',
        'password': '123456',
        'captcha_id': data['captcha_id'],
        'captcha_code': 'XXXX',
    }
    status, result = request_json(
        f'{base}/api/v1/auth/login',
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'},
    )
    print('错误验证码登录:', status, result)

    # 重新获取验证码
    status, data = request_json(f'{base}/api/v1/auth/captcha')
    code = r.get(f"captcha:{data['captcha_id']}")
    print('新验证码答案:', code)

    # 正确验证码登录
    payload = {
        'username': 'root',
        'password': '123456',
        'captcha_id': data['captcha_id'],
        'captcha_code': code,
    }
    status, result = request_json(
        f'{base}/api/v1/auth/login',
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'},
    )
    print('正确验证码登录:', status, result)


if __name__ == '__main__':
    main()
