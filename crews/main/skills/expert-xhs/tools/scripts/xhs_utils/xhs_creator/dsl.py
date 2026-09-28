"""Creator ``_dsl`` anchor (appId=ugc) with browser-matching 5 minute cache."""

from xhs_utils.xhs_core.dsl import DsFetcher


_default = DsFetcher('ugc', referer='https://creator.xiaohongshu.com/')


def get_dsl(
    proxies: dict | None = None,
    force: bool = False,
    http_client=None,
) -> str:
    return get_ds_bundle(
        proxies=proxies,
        force=force,
        http_client=http_client,
    )[0]


def get_ds_bundle(
    proxies: dict | None = None,
    force: bool = False,
    http_client=None,
) -> tuple[str, str]:
    return _default.get_bundle(
        proxies=proxies,
        force=force,
        http_client=http_client,
    )


DSN_READY = 'a1'
DSN_BOOTSTRAP = 'nop'


__all__ = ['get_dsl', 'get_ds_bundle', 'DSN_READY', 'DSN_BOOTSTRAP']
