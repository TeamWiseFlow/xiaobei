"""PC security configuration fetched locally and interpreted by OFB Relay."""

from xhs_utils.xhs_core.dsl import DsFetcher

_default = DsFetcher('xhs-pc-web', referer='https://www.xiaohongshu.com/')


def get_dsl(proxies=None, force=False, http_client=None):
    return _default.get(proxies=proxies, force=force, http_client=http_client)


__all__ = ['DsFetcher', 'get_dsl']
