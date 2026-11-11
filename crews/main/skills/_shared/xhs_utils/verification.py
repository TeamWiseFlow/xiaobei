"""Typed, bounded verification challenges from PC responses."""
from __future__ import annotations

import re
from urllib.parse import urlencode


class VerificationRequired(RuntimeError):
    def __init__(self, status: int, uuid: str, kind: str, *, response=None):
        self.challenge = {'status': status, 'uuid': uuid, 'type': kind}
        self.response = response
        super().__init__('小红书要求用户完成安全验证；使用 xhs-hunter verify-start 继续')

    def public(self):
        query = urlencode({'redirectPath': 'https://www.xiaohongshu.com/explore',
                           'verifyUuid': self.challenge['uuid'],
                           'verifyType': self.challenge['type'],
                           'verifyBiz': self.challenge['status']})
        return {'error': 'VERIFICATION_REQUIRED', 'verify_type': self.challenge['type'],
                'supported': self.challenge['type'] in {'120', '124'},
                'verify_url': 'https://www.xiaohongshu.com/website-login/captcha?' + query}


def check_response(response):
    status = getattr(response, 'status_code', None)
    if status not in (461, 471):
        return
    headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
    uuid = headers.get('verifyuuid', '')
    kind = headers.get('verifytype', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', uuid) or not re.fullmatch(r'\d{1,4}', kind):
        raise RuntimeError('小红书安全验证响应缺少有效验证材料；请在同账号网页完成验证')
    raise VerificationRequired(status, uuid, kind, response=response)
