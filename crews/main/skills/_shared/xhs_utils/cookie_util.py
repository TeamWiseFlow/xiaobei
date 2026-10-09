def trans_cookies(cookies_str):
    if '; ' in cookies_str:
        ck = {i.split('=')[0]: '='.join(i.split('=')[1:]) for i in cookies_str.split('; ')}
    else:
        ck = {i.split('=')[0]: '='.join(i.split('=')[1:]) for i in cookies_str.split(';')}
    return ck
