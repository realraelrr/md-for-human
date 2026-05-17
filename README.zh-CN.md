# md-for-human

**Agent 写 Markdown，人类读 HTML。md-for-human 连接这两者。**

[English README](README.md)

`md-for-human` 把 Markdown 视为 agent 编写的、可长期维护的源文件，把 HTML 视为给人类阅读的确定性渲染产物。Agent 继续写易于编辑、diff、审查和复用的内容；人类获得带排版、导航、本地链接重写、资产处理、结构校验和 manifest 的 HTML 阅读站点。

这不是 “Markdown vs HTML” 的争论，而是在明确 source/artifact 边界：agent 写出的 Markdown 是 source of truth，renderer 把它确定性地编译成 HTML，默认不重新解释内容。让 agent 直接生成精致 HTML，会把内容表达和视觉表现混在一次生成里，增加语义漂移风险。`md-for-human` 的目标是渲染你已经写好的 Markdown。

## 它做什么

给定一个 Markdown 文件或目录，`md-for-human` 会构建一个静态 HTML 阅读站点：

- 文件夹/站点级渲染
- 默认打开浏览器预览
- 侧边栏导航和页面目录
- 上一页/下一页浏览
- 本地 Markdown 链接重写
- 带安全检查的引用资产复制
- 代码块语法高亮
- `--verify` 结构校验
- `--fail-on-warning` 严格 warning 策略
- `.md-for-human/manifest.json` 用于 agent 审计和交付

它不会改写 Markdown，不会总结内容，不会润色内容，也不会要求 agent 重新设计页面。

## 安装

新环境建议使用项目自带的 conda 环境：

```bash
conda env create -f environment.yml
conda activate md-for-human
```

如果已经在本地开发环境中，从仓库根目录刷新 editable install：

```bash
python -m pip install -e . --no-build-isolation
```

## 使用

从示例 fixture 构建站点：

```bash
md-for-human tests/fixtures/sample_site -o /tmp/md-for-human-sample-site --overwrite --verify --no-open
```

从目录构建并打开结果：

```bash
md-for-human path/to/agent-output
```

从单个 Markdown 文件构建：

```bash
md-for-human path/to/notes.md -o /tmp/notes-site --no-open
```

不激活环境时通过 conda 运行：

```bash
conda run -n md-for-human md-for-human path/to/agent-output --no-open
```

## 面向 Agent 的输出

构建成功后会打印稳定摘要：

```text
Built site at: ...
Output directory: ...
Pages: ...
Assets copied: ...
Warnings: ...
Browser opened: yes/no
Verification: passed
```

每次构建也会在输出目录写入 `.md-for-human/manifest.json`：

```json
{
  "entry_page": "index.html",
  "pages": ["index.html", "guide/setup.html"],
  "copied_assets": ["images/diagram.png"],
  "warnings": []
}
```

使用 `--verify` 做结构校验；当 warning 应该导致自动化失败时，使用 `--fail-on-warning`。

## Skill 集成

仓库内置 agent skill：[SKILL.md](SKILL.md)。`.codex/skills/md-for-human/` 和 `.claude/skills/md-for-human/` 下的入口都指向这份根目录 skill 文档。

当 agent 需要把 Markdown 交付物转成人类可读 HTML 站点时，使用这个 skill。Skill 是 agent-facing 主协议；JSON/manifest 只是辅助验证和交付审计的证据。

## 开发

标准检查：

```bash
ruff check .
mypy --strict src
python -m pytest -q
python -m md_for_human tests/fixtures/sample_site -o /tmp/md-for-human-sample-site --overwrite --verify --no-open
md-for-human --help
```

项目使用 `src/` 布局。顶层 `md_for_human/` 包是本地 bootstrap shim，让 checkout 中的 `python -m md_for_human` 在安装前也能工作。

## 安全说明

默认输出目录会自动替换。已有的自定义输出路径必须显式传入 `--overwrite`，并且只会在校验通过后删除。CLI 会拒绝以下输出路径：输入目录本身、输入目录内部、输入目录的祖先目录、输入 Markdown 文件本身、输入 Markdown 文件的祖先目录。它也会防止最终输出 symlink 删除目标目录，以及 symlink 父路径绕回输入树。

引用资产只有在安全解析到输入树内部时才会被复制。缺失资产、symlink 资产、解析到输入树外的资产、非文件资产都会产生 warning。

## License

MIT. See [LICENSE](LICENSE).
