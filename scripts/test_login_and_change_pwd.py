import json
import urllib.request
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
        body = e.read()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body.decode('utf-8', errors='ignore')}


def get_captcha_code():
    r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    status, data = request_json(f'{base}/api/v1/auth/captcha')
    assert status == 200
    code = r.get(f"captcha:{data['captcha_id']}")
    return data['captcha_id'], code


def main():
    # 1. 错误密码登录
    captcha_id, code = get_captcha_code()
    status, result = request_json(
        f'{base}/api/v1/auth/login',
        data=json.dumps({
            'username': 'root',
            'password': 'wrong_password',
            'captcha_id': captcha_id,
            'captcha_code': code,
        }).encode(),
        headers={'Content-Type': 'application/json'},
    )
    print('错误密码登录:', status, result)
    assert status == 401

    # 2. 正确密码登录
    captcha_id, code = get_captcha_code()
    status, result = request_json(
        f'{base}/api/v1/auth/login',
        data=json.dumps({
            'username': 'root',
            'password': '123456',
            'captcha_id': captcha_id,
            'captcha_code': code,
        }).encode(),
        headers={'Content-Type': 'application/json'},
    )
    print('正确密码登录:', status, result.get('message'))
    assert status == 200
    token = result['token']

    # 3. 不带旧密码修改密码（此时 need_change_password=true）
    status, result = request_json(
        f'{base}/api/v1/auth/change-password',
        data=json.dumps({
            'new_password': 'newpass123',
        }).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'},
    )
    print('不带旧密码修改:', status, result)
    assert status == 200

    # 4. 用新密码登录
    captcha_id, code = get_captcha_code()
    status, result = request_json(
        f'{base}/api/v1/auth/login',
        data=json.dumps({
            'username': 'root',
            'password': 'newpass123',
            'captcha_id': captcha_id,
            'captcha_code': code,
        }).encode(),
        headers={'Content-Type': 'application/json'},
    )
    print('新密码登录:', status, result.get('message'), 'need_change_password:', result.get('user', {}).get('need_change_password'))
    assert status == 200

    print('测试通过')


if __name__ == '__main__':
    main()
