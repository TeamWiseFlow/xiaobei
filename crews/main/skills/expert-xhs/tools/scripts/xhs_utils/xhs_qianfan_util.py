import random
from xhs_utils.xhs_pc.params import generate_x_b3_traceid

def get_qianfan_headers_template():
    return {
        "authority": "pgy.xiaohongshu.com",
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": "https://pgy.xiaohongshu.com/microapp/distribution/live-broadcast/kol",
        "sec-ch-ua": "\"Chromium\";v=\"122\", \"Not(A:Brand\";v=\"24\", \"Google Chrome\";v=\"122\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "x-b3-traceid": generate_x_b3_traceid()
    }

def get_qianfan_userDetail_headers_template(user_id):
    return {
        "authority": "pgy.xiaohongshu.com",
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://pgy.xiaohongshu.com",
        "pragma": "no-cache",
        "referer": f"https://pgy.xiaohongshu.com/microapp/distribution/live-blogger-info/{user_id}",
        "sec-ch-ua": "\"Chromium\";v=\"122\", \"Not(A:Brand\";v=\"24\", \"Google Chrome\";v=\"122\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "x-b3-traceid": generate_x_b3_traceid()
    }

def generate_qianfan_data(choice, distribution_category, page):
    if choice == "-1":
        data = {
            "buyer_activity": [],
            "live_plan_range": [],
            "seed": random.randint(1000, 9999),
            "page": page,
            "limit": 20
        }
    else:
        choice = choice.split("-")
        live_first_category = []
        live_second_category = []
        for cate_category in choice:
            cate_category_temp = cate_category.split("(")
            live_first_category.append(distribution_category[int(cate_category_temp[0])]["first_category"])
            if len(cate_category_temp) > 1:
                live_second_category_temp = cate_category_temp[1][:-1].split(",")
                for second_category_index in live_second_category_temp:
                    live_second_category.append(
                        distribution_category[int(cate_category_temp[0])]["second_category"][
                            int(second_category_index)])
            else:
                live_second_category.extend(distribution_category[int(cate_category_temp[0])]["second_category"])
        data = {
            "buyer_activity": [],
            "live_plan_range": [],
            "live_first_category": live_first_category,
            "live_second_category": live_second_category,
            "seed": random.randint(1000, 9999),
            "page": page,
            "limit": 20
        }
    return data
