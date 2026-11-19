# 设计与内容参考

本站点组统一使用共享 session/profile `default`；每条 Camoufox 操作带 `--persistent`。入口常量见 [site-catalog.json](../site-catalog.json)。需要 Pexels/Pixabay 的检索与下载时，当前 crew 已配置 `pexels-footage` / `pixabay-footage` 则先读取对应技能。

| 站点 | session / profile | 搜索入口 |
|---|---|---|
| Pinterest | `default` | `https://www.pinterest.com/search/pins/?q={keyword}` |
| Pixiv | `default` | `https://www.pixiv.net/`，使用页面搜索 |
| ArtStation | `default` | `https://www.artstation.com/search`，使用页面搜索 |
| Flickr | `default` | `https://www.flickr.com/search/?text={keyword}` |
| Unsplash | `default` | `https://unsplash.com/`，使用页面搜索 |
| Openverse | `default` | `https://openverse.org/`，使用页面搜索 |

## Pinterest

- 默认搜 pins；画板可用 `https://www.pinterest.com/search/boards/?q={keyword}`，用户可用 `https://www.pinterest.com/search/users/?q={keyword}`。类别与排序以实际页面为准。
- 提取 Pin/board/profile 的真实链接、标题、作者/账号、可见说明和原始外链；保存 Pin 详情而非把 CDN 缩略图当作品来源。
- 根据懒加载有界滚动；进入原始作品页核对图片内容和作者。

## Pixiv

- 在当前界面的搜索框输入关键词/标签，按页面选插画、漫画、小说等类别和实际标签匹配方式；不把 `/ajax/search/illustrations` 当成网页地址。
- 提取作品标题、作者、作品详情链接/ID、标签、发布时间和可见页数；多页作品到详情核对每页与说明。
- 登录/年龄/付费可见范围按 browser-guide 处理；只读取实际展示的作品与字段，不切换限制设置或自动关注/收藏。

## ArtStation

- 打开搜索页等待真实控件，按页面选择作品、艺术家等类别以及媒介/主题/排序，输入用户的主题或风格关键词。
- 保存作品标题、作者、项目详情链接、可见描述与媒介/软件标签；进入 project 页面核对图集、视频和作者来源。
- 缩略图、作者项目与商店商品分开，收费素材只记录实际可见信息；不复制上游 search.json 请求。

## Flickr

- 在网页搜索中按实际筛选限定照片/用户/群组、日期与颜色。
- 提取照片标题、作者、照片详情链接、实际显示的拍摄/上传日期及说明；拍摄日期与上传日期分别保存。
- 到照片详情页核对内容；不调用需要 API key 的 Flickr 接口。

## Unsplash

- 从页面搜索框提交主题，按当前界面选择照片、合集或用户及方向/颜色等筛选。区分普通照片与 Unsplash+ 付费内容。
- 保存照片/合集/用户真实链接、标题/描述、摄影师及可见日期；查作者时进入真实 profile。
- 只完成检索与来源确认，批量下载不在本规则执行；未展示字段保留缺项。

## Openverse

- 在首页使用实际可用的搜索入口，按页面选择图片/音频与来源。界面不可用或本轮无法完成验证时报告入口缺口，不自动切到 Openverse API。
- 提取作品标题、作者、详情链接与原始来源链接。
- 到原始来源核对作品，搜索引擎的聚合标签作为线索；图片和音频分别记录。

源码参考：[OpenCLI Pinterest](https://github.com/jackwener/OpenCLI/tree/b06ab7780e73d3021e12e0f170086c2d55675776/clis/pinterest)、[Pixiv](https://github.com/jackwener/OpenCLI/blob/b06ab7780e73d3021e12e0f170086c2d55675776/clis/pixiv/search.js)、[SearXNG 图像引擎](https://github.com/searxng/searxng/tree/ad46ebd7d87666edb5f116c5b274b47f689ac6cd/searx/engines)。API-only 引擎只用于核对来源与字段，不复刻成浏览器接口调用。
