# OmniSubUI 和公网网关

OmniSub 通过 `OmniSubUI` Git 子模块固定前端提交。前端托管版本使用现有网关的 `POST /api/links`、`GET /s/<token>`。网关继续通过内部网络向 `engine:25500` 转换订阅。托管和直连共用原版表单。托管首页通过 `GET /healthz?capabilities=1` 获取目标和参数；诊断使用 `POST /api/links` 的 `action: "diagnose"`，只返回校验状态、目标和节点数。普通静态前端构建和直连后端配置见 [OmniSubUI README](../../OmniSubUI/README.md)。

## 构建

使用 `OmniSubUI/.node-version` 指定的 Node.js 版本。在 OmniSub 根目录执行：

```sh
git submodule update --init OmniSubUI
scripts/package-web-ui.sh /tmp/omnisub-ui-www
```

制品目录是网关的平铺 `www/` 布局：`index.html`、`app.js`、`style.css`、`favicon.svg`。路由保持为 `/`、`/assets/app.js`、`/assets/style.css`、`/favicon.svg`。CSS 和 JavaScript 的 URL 带有前端提交标识，因此可以保留反代原来的精确路径白名单。网关的其他图标可以继续保留。

## 更新现有网关

[gateway-inline.patch](gateway-inline.patch) 适用于固定使用 `base/public.ini` 的现有 Flask 网关。Mihomo 完整输出遇到网关预取并封装的 YAML 时，引擎会返回指向内部 `data:` 源的 Provider。补丁让网关另外请求内联节点，保留原模板其余内容，并继续核对节点数量和 Hysteria2 认证。补丁只转换已认识的站点模板和数据 Provider；模板变更后要重新验证这一行为。已应用补丁的网关无需重复打补丁。

[gateway-client-catalog.patch](gateway-client-catalog.patch) 接在上述补丁之后。它允许 26 个具体目标选项（含 Surge V2 至 V6），按每种格式核对输出节点数。站点继续使用 `base/public.ini`，只开放 YAML 节点列表和严格布尔的 `sort`、`append_type`。前端不向公共网关传递任意规则模板、脚本或 Provider 前缀。旧版加密配方无须更改。

1. 备份当前网关的 `app.py`、要替换的 `www/` 文件，并给运行中的 Web 镜像保留回滚标签。在临时目录用 `patch --dry-run -p1 < gateway-inline.patch` 检查原网关副本，再应用适用的补丁。已有前一版托管网关时，只检查和应用 `gateway-client-catalog.patch`。
2. 在临时构建目录以旧 Web 镜像为基础，复制验证过的 `app.py` 和新的 `www/`，构建候选镜像。用 Compose 的同一 Web 服务配置、内部网络和既有密钥挂载，在另一个仅本机可访问的端口预演。保持引擎、规则模板和反代配置原样。
3. 验收候选环境，确认旧网关生成的合成更新链接仍能下载同样的配置。把验证过的文件保存到部署源目录，将候选镜像标记为 Compose 使用的 Web 镜像，再用 `docker compose up -d --no-deps --no-build --wait web` 更新 Web 服务。失败时恢复备份文件和旧镜像，再以相同命令恢复 Web。现有 `state/link-key` 不要重新生成。
4. 从实际域名再次执行验收：

```sh
python3 deploy/omnisub-ui/smoke.py https://sub.example.com/
python3 deploy/omnisub-ui/client-matrix.py https://sub.example.com/
```

验收脚本只使用合成节点，覆盖首页资源、健康接口、全部具体目标、Surge 5/6 的 VLESS 差异、诊断、可选参数、YAML 和 Hysteria2 认证。它们不打印生成的更新链接。客户端导入和节点连接仍需用客户端独立验证。
