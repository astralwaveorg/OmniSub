<div align="center">

<img src="design/favicon-light-proposal.svg#gh-light-mode-only" alt="OmniSub" width="80">
<img src="design/favicon-dark-proposal.svg#gh-dark-mode-only" alt="OmniSub" width="80">

# OmniSub

将订阅链接、节点链接和规则模板转换为 Mihomo、Stash、Surge 等客户端可用的配置。

[![正式版本](https://img.shields.io/github/v/release/astralwaveorg/OmniSub?label=release&logo=github)](https://github.com/astralwaveorg/OmniSub/releases/latest)
[![发布构建](https://img.shields.io/github/actions/workflow/status/astralwaveorg/OmniSub/release.yml?branch=release&label=build&logo=githubactions)](https://github.com/astralwaveorg/OmniSub/actions/workflows/release.yml)
[![GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-orange)](LICENSE)

[快速开始](#快速开始) · [客户端与格式](#客户端与格式) · [下载与更新](#下载与更新) · [排查问题](#排查问题)

</div>

> [!WARNING]
> 本软件仅供在中华人民共和国境外学习和研究使用。
>
> **禁止任何组织或个人在中国大陆访问、下载、部署或使用本项目的任何内容。身处中国大陆的访客请立即关闭本页面。**
>
> 任何组织或个人均不得利用本项目内容从事违反适用法律法规的活动。使用者须自行承担其使用行为产生的法律责任。

OmniSub 基于 [SubConverter-Extended](https://github.com/Aethersailor/SubConverter-Extended)。它保留上游的 Mihomo / OpenClash 转换路径，并改进 Stash 和 Surge 的配置输出。你可以提供自己的节点或订阅，再按客户端选用模板。OmniSub 不提供代理服务器、节点或上游订阅。

## 快速开始

### 在本机用 Docker 运行

示例把 `25500` 端口绑定到本机回环地址。部署后可用 `/version` 核对实际运行的版本。

```bash
docker run -d \
  --name omnisub \
  --restart unless-stopped \
  -p 127.0.0.1:25500:25500 \
  ghcr.io/astralwaveorg/omnisub:v1.12.1

curl -fsS http://127.0.0.1:25500/healthz
curl -fsS http://127.0.0.1:25500/version
```

### 生成第一份订阅

将下面的示例地址换成你自己的 HTTPS 订阅。命令生成一份 Mihomo 节点列表。去掉 `list=true` 可请求完整配置。其他客户端的参数见下表。

```bash
curl -fsSG 'http://127.0.0.1:25500/sub' \
  --data-urlencode 'target=clash' \
  --data-urlencode 'list=true' \
  --data-urlencode 'url=https://example.com/subscription' \
  -o mihomo.yaml
```

用 `--data-urlencode` 传入完整的订阅地址。它会保留原地址中的 `?`、`&` 等字符。一次提交多个来源时，用 `|` 分隔各来源，再对整个 `url` 参数编码。

### 在 NAS 或 Compose 中使用

- 同一 Compose 网络内，应用通过服务名访问转换器，例如 `http://subconverter-extended:25500`。只需内网调用时，可以移除转换器的 `ports`，无需向宿主机发布端口。
- 替换旧转换器时，保留原服务名、环境变量与已有挂载，只修改镜像引用。生产环境建议固定 Release 中的镜像摘要，便于核对和回退。
- 要保留配置或统计数据，可参考仓库中的 [Compose 示例](docker-compose.yml)。启动前先准备 `base/pref.toml`，不要把整个宿主机目录挂到容器的 `/base`，以免遮盖镜像自带的模板和规则。示例默认发布到宿主机所有接口，使用前请按实际访问范围调整。

本项目未公布 OmniSub 公共实例。上游 Wiki 中的公共地址由上游维护，功能和版本可能不同。订阅 URL 可能包含凭据，建议通过自己的实例转换。

## 客户端与格式

| 客户端 | 请求参数 | 输出 |
| --- | --- | --- |
| Mihomo / OpenClash | `target=clash` | Mihomo YAML。完整配置可生成 Proxy Provider；`list=true` 输出节点列表。历史用法 `target=clashr` 保留。 |
| Stash | `target=stash` | Stash YAML。可保留受支持的 Reality ML-KEM、UDP 封装和 XHTTP 参数。 |
| Surge 6 | `target=surge&ver=6` | Surge 配置，支持转换部分 VLESS 节点。客户端无法表示的传输或字段不会当作兼容配置输出。 |
| 旧版 Surge | `target=surge`，按需指定 `ver` | 沿用旧版配置格式。新增的 VLESS 导出需要 `ver=6`。 |
| Shadowrocket | `target=shadowrocket` | 节点订阅。不要按完整分流配置导入。 |

Hysteria2 在 Mihomo YAML 中使用 `password`，在 Stash YAML 中使用 `auth`。两端需要分别生成对应的配置。配置能生成也不代表所有节点都被保留；转换后请核对节点数量，再在目标客户端导入并测试连接。

本版通过服务端转换回归。OpenClash 和 Shadowrocket 的回归样本与上游一致；Stash、Surge 和 Shadowrocket 的客户端实机导入未在本次发布中验证。其他兼容目标包括 `singbox`、`quanx`、`loon`、`surfboard` 和 `mixed`，详见[上游目标格式参考](https://github.com/Aethersailor/SubConverter-Extended/wiki/Compatibility)。

### 订阅、模板与规则

Mihomo 完整配置可保留远程 Proxy Provider，由客户端定期拉取节点。是否保留远程资源取决于输出目标、输入和请求参数。Provider 方式下，订阅地址仍可能出现在请求或生成的配置中。

用 `config` 选择外部模板。模板可以定义策略组和规则集，同一份模板是否适合多个客户端，取决于目标客户端支持的规则和配置字段。如果客户端使用的最简配置不含 DNS 设置，请在客户端配置 DNS，或换用包含 DNS 设置的基础模板。

更多用法见上游的[远程订阅](https://github.com/Aethersailor/SubConverter-Extended/wiki/Remote-Subscriptions)、[模板](https://github.com/Aethersailor/SubConverter-Extended/wiki/External-Configuration)、[规则集](https://github.com/Aethersailor/SubConverter-Extended/wiki/Rules-and-Rulesets)和 [API 参数](https://github.com/Aethersailor/SubConverter-Extended/wiki/API-Reference)。OpenClash 的模板与规则另见 [Custom_OpenClash_Rules](https://github.com/Aethersailor/Custom_OpenClash_Rules)。

## 下载与更新

从 [OmniSub Releases](https://github.com/astralwaveorg/OmniSub/releases/latest) 获取正式版本。[GitHub Container Registry](https://github.com/astralwaveorg/OmniSub/pkgs/container/omnisub) 的公开镜像可匿名拉取。

| 交付形式 | 平台与格式 |
| --- | --- |
| Docker | `ghcr.io/astralwaveorg/omnisub`：`linux/amd64`、`linux/arm64`、`linux/arm/v7` |
| 便携包 | Linux：`amd64`、`arm64`、`armv7`；Windows：`amd64` |
| OpenWrt | 按设备架构和包管理器选择 `.apk` 或 `.ipk`。继续使用原服务名和配置路径。 |

用 `SHA256SUMS` 校验安装包。用 `RELEASE-MANIFEST.json` 核对构建提交、文件校验值和镜像摘要。镜像的版本标签与 GitHub Release 一致；`latest` 随正式发布更新。

## 排查问题

1. 请求 `/healthz` 检查服务是否就绪，再请求 `/version` 核对版本。
2. 核对 `target`，然后用少量节点缩小问题范围。如果只想查看转换过程，可加 `explain=true` 获取脱敏诊断；该选项不返回配置文件。
3. 仍有问题时，到 [OmniSub Issues](https://github.com/astralwaveorg/OmniSub/issues) 提交版本、客户端版本、目标格式和脱敏样例。若响应带有 `X-Request-ID`，请一并提供。

不要在 Issue 或日志中粘贴完整订阅地址、节点凭据或未经检查的配置。自行部署时，按访问范围选择 `lan`、`public` 或 `strict` 档位；`lan` 不适合直接暴露到公网。公开入口需要额外配置 TLS、访问控制和限流。安全问题请私下报告；[安全策略](SECURITY.md) 目前列的是上游报告入口。详细配置参见[上游安全与隐私文档](https://github.com/Aethersailor/SubConverter-Extended/wiki/Security-and-Privacy)。

## 开发与发布

日常开发在 `dev` 进行。发版时更新 `VERSION` 和 [发布说明](RELEASE-NOTES.md)，再向 `release` 提交 PR。通过必需检查后，用普通合并提交合入。发布流水线从合并提交构建产物，完成转换回归后上传 Release 和镜像。单独推送 `dev` 不发布。

参见[贡献指南](CONTRIBUTING.md)。协议或输出行为有变动时，可用 [HTTP 回归测试](tests/converter_smoke.py) 比较候选镜像与固定的上游基线。测试使用合成节点，不需要登录公共实例。

## 上游与许可证

- [SubConverter-Extended](https://github.com/Aethersailor/SubConverter-Extended)：直接上游。其 [Wiki](https://github.com/Aethersailor/SubConverter-Extended/wiki) 可作通用参数参考；下载和镜像请使用 OmniSub 的发布入口。
- [asdlokj1qpi233/subconverter](https://github.com/asdlokj1qpi233/subconverter)：上游的转换器基础。
- [MetaCubeX/mihomo](https://github.com/MetaCubeX/mihomo)：提供 Mihomo 节点解析能力。

OmniSub 按 [GPL-3.0](LICENSE) 发布。Mihomo 解析桥使用的依赖版本见 [bridge/go.mod](bridge/go.mod)。
