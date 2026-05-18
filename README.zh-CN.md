# md-for-human

把 agent 编写的 Markdown 渲染成可导航的静态 HTML 阅读站点。

[English README](README.md)

`md-for-human` 保留 Markdown 作为可编辑源文件，把 HTML 作为阅读产物。它支持目录和单文件输入、侧边栏导航、页面目录、上一页/下一页、本地 Markdown 链接重写、引用资产复制、代码高亮、结构校验，以及用于 agent 交付的 manifest。

它不会改写、总结或润色 Markdown。

## 安装

创建并激活项目环境：

```bash
conda env create -f environment.yml
conda activate md-for-human
```

只在已激活的 conda 或 virtualenv 中刷新 editable install：

```bash
python -m pip install -e ".[dev]" --no-build-isolation
```

不要对系统 Python 执行 editable install。

## 使用

从目录构建并打开结果：

```bash
md-for-human path/to/agent-output
```

从单个 Markdown 文件构建并打开结果：

```bash
md-for-human path/to/notes.md -o /tmp/notes-site
```

不激活环境时运行：

```bash
conda run -n md-for-human md-for-human path/to/agent-output
```

从示例 fixture 构建并验证，但不打开浏览器：

```bash
md-for-human tests/fixtures/sample_site -o /tmp/md-for-human-sample-site --overwrite --verify --no-open
```

`--no-open` 用于 headless 场景，`--verify` 用于结构校验，`--fail-on-warning` 用于严格自动化。

## 输出契约

构建成功会输出：

```text
Built site at: ...
Output directory: ...
Pages: ...
Assets copied: ...
Warnings: ...
Browser opened: yes/no
```

使用 `--verify` 时，摘要还会包含 `Verification: passed` 或 `Verification: failed`。

每次构建都会在输出目录写入 `.md-for-human/manifest.json`：

```json
{
  "entry_page": "index.html",
  "pages": ["index.html", "guide/setup.html"],
  "copied_assets": ["images/diagram.png"],
  "warnings": []
}
```

单文件输入的 `entry_page` 使用源文件 basename，而不是 `index.html`。

## Agent Skill

Agent 执行协议在 [`SKILL.md`](SKILL.md)。`.codex/skills/md-for-human/` 和 `.claude/skills/md-for-human/` 下的入口都指向该文件。

## 开发

标准检查：

```bash
ruff check .
mypy --strict src
python -m pytest -q
python -m md_for_human tests/fixtures/sample_site -o /tmp/md-for-human-sample-site --overwrite --verify --no-open
md-for-human --help
```

项目使用 `src/` 布局。顶层 `md_for_human/` 包是 bootstrap shim，让 `python -m md_for_human` 在安装前也能从 checkout 中运行。

## 安全

CLI 会拒绝把输出路径设为输入路径、输入树内部或输入路径祖先。自定义输出路径需要 `--overwrite`。

只复制被引用的本地资产。缺失、symlink、越过输入根目录或非文件资产会产生 warning。

## License

MIT. See [LICENSE](LICENSE).
