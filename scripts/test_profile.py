import json
import urllib.request
import redis
import sys
import uuid

sys.stdout.reconfigure(encoding='utf-8')
base = 'http://127.0.0.1:8002'


def request_json(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
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
    test_username = f'test_user_{uuid.uuid4().hex[:8]}'
    # 1. 注册新用户（带性别生日）
    captcha_id, code = get_captcha_code()
    status, result = request_json(
        f'{base}/api/v1/auth/register',
        data=json.dumps({
            'username': test_username,
            'password': '123456',
            'gender': 'male',
            'birth_date': '1995-08-15',
        }).encode(),
        headers={'Content-Type': 'application/json'},
    )
    print('注册:', status, result)
    assert status == 200

    # 2. 登录
    captcha_id, code = get_captcha_code()
    status, result = request_json(
        f'{base}/api/v1/auth/login',
        data=json.dumps({
            'username': test_username,
            'password': '123456',
            'captcha_id': captcha_id,
            'captcha_code': code,
        }).encode(),
        headers={'Content-Type': 'application/json'},
    )
    print('登录:', status, result.get('user'))
    assert status == 200
    token = result['token']

    # 3. 获取资料
    status, result = request_json(
        f'{base}/api/v1/auth/profile',
        headers={'Authorization': f'Bearer {token}'},
    )
    print('获取资料:', status, result)
    assert status == 200

    # 4. 更新资料
    status, result = request_json(
        f'{base}/api/v1/auth/profile',
        data=json.dumps({
            'phone': '13800138001',
            'gender': 'female',
            'birth_date': '1996-09-20',
        }).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'},
        method='PUT',
    )
    print('更新资料:', status, result)
    assert status == 200

    print('测试通过')


if __name__ == '__main__':
    main()
