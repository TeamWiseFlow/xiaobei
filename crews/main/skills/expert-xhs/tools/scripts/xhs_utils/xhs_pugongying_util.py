from xhs_utils.xhs_pc.params import (
    generate_x_b3_traceid,
    generate_xs,
)
from xhs_utils.xhs_pc.state import PcDeviceProfile, cookie_header


PC_CURRENT_BROWSER_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36'
)


def get_pugongying_user_info_headers():
    """Headers captured from Chrome for ``GET /api/solar/user/info``.

    This route is an unsigned bootstrap request.  Keep its minimal wire
    contract separate from the signed business routes; in particular, empty
    ``x-s``/``x-t`` and authorization headers are not sent by Chrome.
    """
    return {
        'x-b3-traceid': generate_x_b3_traceid(),
        'referer': 'https://pgy.xiaohongshu.com/role-introduce?needLogout=needLogout',
        'user-agent': PC_CURRENT_BROWSER_UA,
        'accept': 'application/json, text/plain, */*',
    }


def get_pugongying_signed_user_info_headers(
    *, x_s: str, x_t: str, x_s_common: str, x_b3_traceid: str,
    referer: str = 'https://pgy.xiaohongshu.com/role-introduce?needLogout=needLogout',
):
    """Build the later signed ``user/info`` shape from captured values.

    The browser sends a distinct signed variant after bootstrap.  Signature
    bytes are intentionally required from the caller; this helper never
    fabricates or silently drops them.
    """
    required = {
        'x-s': x_s, 'x-t': x_t, 'x-s-common': x_s_common,
        'x-b3-traceid': x_b3_traceid,
    }
    missing = [key for key, value in required.items() if value is None or value == '']
    if missing:
        raise ValueError('signed user/info missing captured fields: ' + ', '.join(missing))
    return {
        'authorization': '',
        'referer': str(referer),
        'x-t': str(x_t),
        'x-b3-traceid': str(x_b3_traceid),
        'x-s-common': str(x_s_common),
        'user-agent': PC_CURRENT_BROWSER_UA,
        'accept': 'application/json, text/plain, */*',
        'x-s': str(x_s),
    }

def get_pugongying_headers_template():
    return {
        "authority": "pgy.xiaohongshu.com",
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "authorization": "",
        "cache-control": "no-cache",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://pgy.xiaohongshu.com",
        "pragma": "no-cache",
        "referer": "https://pgy.xiaohongshu.com/solar/pre-trade/kol",
        "sec-ch-ua": "\"Chromium\";v=\"122\", \"Not(A:Brand\";v=\"24\", \"Microsoft Edge\";v=\"122\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
        "x-b3-traceid": '',
        "x-s": "",
        "x-t": ""
    }

def generate_pugongying_headers(cookies, api, data='', profile=None):
    profile = profile or PcDeviceProfile(cookies=cookies)
    profile.update_cookies(cookies)
    sign_context = profile.next_sign_context(api)
    xs, xt = generate_xs(
        cookies['a1'],
        api,
        data,
        cookie=cookie_header(cookies),
        tier=sign_context['tier'],
        sign_context=sign_context,
    )
    x_b3_traceid = generate_x_b3_traceid()
    headers = get_pugongying_headers_template()
    headers['x-s'] = xs
    headers['x-t'] = str(xt)
    headers['x-b3-traceid'] = x_b3_traceid
    return headers

def get_pugongying_bozhu_data(page, brandUserId, contentTag=None):
    data = {
        "searchType": 1,
        "column": "comprehensiverank",
        "sort": "desc",
        "pageNum": page,
        "pageSize": 20,
        "brandUserId": brandUserId,
        # "trackId": "kolMatch_c9ee1a9a547c4fffae749ed48171752b",
        "personalTags": [],
        "featureTags": [],
        "estimatePicReadPrice": [],
        "estimateVideoReadPrice": [],
        "fansNumberLower": None,
        "fansNumberUpper": None,
        "noteType": 0,
        "gender": None,
        "location": None,
        "tradeType": "不限",
        "fansAge": 0,
        "fansGender": 0,
        "fansNumUp": 0,
        "cpc": False,
        "excludeLowActive": False,
        "newHighQuality": 0,
        "efficiencyValid": 0,
        "clothingIndustry": 0,
        "firstIndustry": "",
        "secondIndustry": "",
        "activityCodes": []
    }
    if contentTag is not None:
        data['contentTag'] = contentTag
    return data

def generate_pugongying_data(choice, distribution_category):
    contentTag = []
    if choice != "-1":
        choice = choice.split("-")
        for cate_category in choice:
            cate_category_temp = cate_category.split("(")
            if len(cate_category_temp) > 1:
                live_second_category_temp = cate_category_temp[1][:-1].split(",")
                for second_category_index in live_second_category_temp:
                    contentTag.append(
                        distribution_category[int(cate_category_temp[0])]["taxonomy2Tags"][int(second_category_index)])
            else:
                contentTag.append(distribution_category[int(cate_category_temp[0])]["taxonomy1Tag"])
    else:
        contentTag = None
    return contentTag
