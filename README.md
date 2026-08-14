# 📚 OptoMind Full-text Acquisition

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Local API](https://img.shields.io/badge/API-Local%20JSON-2ea44f)](#-本机-json-api)
[![License](https://img.shields.io/badge/Access-Legal%20Only-8a2be2)](#️-使用边界与合规性)

**面向科研智能体的本地论文全文获取工具。**

输入 DOI、PMCID 或论文落地页地址，程序会优先通过合法开放获取（Open Access, OA）渠道取得可追溯全文；对于订阅论文，则在**用户已经手动登录学校机构权限**的前提下，复用可见 Microsoft Edge 浏览器会话逐篇获取全文。

> 🤖 专为科研 Agent、文献资源管道、RAG 知识库准备与可复现实证工作流设计。<br>
> 🔐 无网页表单、不会收集密码、不使用影子图书馆、不绕过付费墙。

---

## ✨ 为什么需要它？

文献元数据 API 能告诉智能体“有这篇论文”，却往往不能可靠地提供可用全文。出版社页面可能只是摘要、付费预览、登录页，也可能需要从学校代理入口访问。

本项目的目标是让系统明确判断：**拿到的是可用全文、仅是元数据页，还是需要人工补充操作。**

```text
论文元数据
    │
    ├── 🟢 合法 OA 路径
    │      JATS XML / TEI XML → 出版社 HTML 正文 → OA PDF
    │
    └── 🔐 机构授权路径
           用户在可见 Edge 中手动登录一次
                    ↓
           复用 Edge-CDP 会话 → 出版社 HTML / PDF
                    ↓
           标准化文本 + provenance.json（来源溯源记录）
```

---

## 🚀 核心能力

- **🤖 Agent 原生接口**：命令行（CLI）与本机 JSON API 均返回结构化状态，适合直接被智能体调用。
- **📄 机器友好优先**：优先尝试 JATS XML、TEI XML、出版社 HTML，最后才使用 PDF 并提取文本。
- **🟢 OA 自动获取**：可利用 Unpaywall 与 OpenAlex 的合法开放获取线索补充下载地址。
- **🏫 机构权限复用**：用户在 Edge 中手动登录一次，程序可逐篇复用该会话；不会读取或保存账号密码。
- **🛑 安全失败而非伪成功**：PubMed 摘要页、订阅预览、验证码页面和无法解析的 PDF 不会被错误标记为全文。
- **🔎 全程可溯源**：每篇成功论文均写入 `provenance.json`，记录来源 URL、访问方式、解析器与原始元数据。
- **🌍 可迁移到任意学校**：用户可配置自己的图书馆/VPN 登录入口；采用 URL 重写代理时，也可配置学校官方代理模板。

---

## 🧩 安装

要求：Python 3.11+。订阅文献路径需要 Windows 上的 Microsoft Edge。

```powershell
git clone https://github.com/Lihonggang-scnu/optomind-fulltext-acquisition.git
cd optomind-fulltext-acquisition
py -3.11 -m pip install -r requirements.txt
py -3.11 -m playwright install chromium
```

如果本机 Playwright 组件已经可用，最后一条命令可以跳过。机构权限流程控制的是**用户可见的 Edge 浏览器**，不会尝试自动填写登录信息。

---

## ⚡ 快速开始：命令行

### 1. 获取开放获取论文

```powershell
py -3.11 cli.py --metadata examples\oa_nature_communications.json
```

### 2. 检查机构会话状态

```powershell
py -3.11 cli.py --check-session
```

### 3. 获取订阅论文

先从自己的图书馆、VPN、CARSI 或学校代理入口启动可见 Edge，并在弹出的浏览器中**手动登录**：

```powershell
py -3.11 cli.py --open-login --login-url "https://library.example.edu/login"
```

保持该 Edge 窗口开启，再提交订阅论文的元数据：

```powershell
py -3.11 cli.py --metadata examples\subscription_nature.json
```

如果学校采用 URL 重写代理，可传入学校官方给出的模板：

```powershell
py -3.11 cli.py --metadata examples\subscription_nature.json `
  --institution-proxy-template "https://{host_dash}-s.proxy.example.edu{path_query}"
```

其中：

- `{host_dash}`：将出版社域名中的 `.` 替换为 `-`；
- `{path_query}`：保留原论文链接中的路径与查询参数。

⚠️ 请仅使用学校官方说明的代理格式，不要猜测或伪造代理地址。

---

## 🔌 本机 JSON API

供工作流编排器、本地智能体或 MCP 包装器调用。默认仅监听 `127.0.0.1`，不会向局域网公开已登录浏览器会话。

```powershell
py -3.11 api_server.py --port 8874
```

| 方法 | 端点 | 作用 |
| --- | --- | --- |
| `GET` | `/health` | 检查服务与 Edge-CDP 会话状态 |
| `POST` | `/open-login` | 在用户指定的图书馆/VPN 地址打开 Edge |
| `POST` | `/acquire` | 根据一份论文元数据获取全文 |

### 请求示例

```json
{
  "title": "Passive radiative cooling below ambient air temperature under direct sunlight",
  "doi": "10.1038/nature13883",
  "is_oa": false,
  "institution_proxy_template": "https://{host_dash}-s.proxy.example.edu{path_query}"
}
```

### 成功响应示例

```json
{
  "status": "acquired",
  "route": "institution_edge_cdp",
  "output": {
    "raw_file": ".../fulltext.html",
    "text_file": ".../fulltext.txt",
    "provenance": ".../provenance.json",
    "source_url": "https://...",
    "access_method": "institution_edge_cdp_html"
  }
}
```

---

## 🗂️ 输出与溯源协议

每篇成功获取的论文都会写入独立目录：

```text
workspace/downloads/<paper-id>/
├── fulltext.xml | fulltext.html | fulltext.pdf
├── fulltext.txt
└── provenance.json
```

`provenance.json` 会记录：输入元数据、最终来源 URL、合法访问方式、解析器、获取时间和候选路径。下游智能体应使用这些本地路径与溯源记录，而非复制或再分发受版权保护的出版商内容。

---

## 🧭 智能体应如何处理状态？

| `status` | 含义 | 推荐下一步 |
| --- | --- | --- |
| `acquired` | 已保存可解析全文。 | 读取 `fulltext.txt` 与 `provenance.json`。 |
| `needs_login` | 尚无可复用的机构 Edge 会话。 | 请求用户手动完成一次机构登录。 |
| `public_fulltext_not_found` | 未找到可解析的合法公开全文。 | 启用机构路径，或请用户提供合法文件。 |
| `manual_follow_up` | 当前访问需要额外点击、登录刷新或独立授权。 | 请用户将合法文件保存至 `workspace/manual_fulltexts/`。 |
| `invalid_input` | 元数据为空或格式不正确。 | 修正请求，不要盲目重试。 |

---


## ⚖️ 使用边界与合规性

本项目只服务于本地科研工作流中的**合法全文获取**：

- ✅ 合法 OA 资源；
- ✅ 用户本人已获授权的学校/机构访问；
- ✅ 用户手动保存的合法文件；
- ❌ 不绕过付费；
- ❌ 不处理 CAPTCHA；
- ❌ 不收集密码；
- ❌ 不进行大规模抓取或再分发版权全文。

请始终遵守出版社条款、学校访问政策与所在地法律法规，不然出了事别怪我。
