"""roundtable — 多模型圆桌决策工具(个人版)

对没有标准答案的决策问题,并行调用多个异构厂商 LLM 做独立盲审,
结构化呈现共识/分歧/独有考量/未定变量,最后对抗性审查攻击多数意见。
工具不给答案,只产出决策地图;决策者是人。
"""

import argparse
import asyncio
import os
import sys
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

load_dotenv()

console = Console(stderr=True)  # 进度输出到 stderr,不污染 stdout 报告

# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class Panelist:
    name: str          # 展示名,如 "DeepSeek"
    base_url: str      # OpenAI 兼容 endpoint
    api_key_env: str   # 环境变量名(绝不硬编码 key)
    model: str


@dataclass
class Take:
    model: str
    text: str
    error: str | None = None


# ── 面板配置(P1: 必须来自不同厂商,实现误差去相关) ────────────────────────────

PANEL: list[Panelist] = [
    Panelist(name="DeepSeek",  base_url="https://api.deepseek.com/v1",          api_key_env="DEEPSEEK_API_KEY",  model="deepseek-v4-flash"),
    Panelist(name="Qwen",      base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", api_key_env="DASHSCOPE_API_KEY", model="qwen-plus"),
    Panelist(name="GLM",       base_url="https://open.bigmodel.cn/api/paas/v4", api_key_env="ZHIPU_API_KEY",     model="glm-5.2"),
]

# Facilitator / Adversary 独立配置(可指向面板中任意模型,也可指向面板外)
# 默认: Facilitator 用第一个面板模型, Adversary 用第二个;编辑此处可指定
FACILITATOR_MODEL: Panelist = PANEL[0]
ADVERSARY_MODEL: Panelist = PANEL[-1]  # 用最后一个面板模型

# ── 超时(秒) ─────────────────────────────────────────────────────────────────

TIMEOUT = 60


# ── 核心调用封装 ──────────────────────────────────────────────────────────────

async def _complete(
    panelist: Panelist,
    user_msg: str,
    system_msg: str = "",
    temperature: float = 0.7,
    timeout: float = TIMEOUT,
) -> Take:
    """调用单个 OpenAI 兼容模型,返回 Take。失败时 Take.error 非空。"""
    api_key = os.getenv(panelist.api_key_env, "")
    if not api_key:
        return Take(model=panelist.name, text="", error=f"缺少环境变量 {panelist.api_key_env}")

    client = AsyncOpenAI(base_url=panelist.base_url, api_key=api_key)
    messages = []
    if system_msg:
        messages.append({"role": "system", "content": system_msg})
    messages.append({"role": "user", "content": user_msg})

    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=panelist.model,
                messages=messages,
                temperature=temperature,
            ),
            timeout=timeout,
        )
        content = resp.choices[0].message.content
        if not content:
            return Take(model=panelist.name, text="", error=f"{panelist.name}: 模型返回空内容")
        return Take(model=panelist.name, text=content.strip())
    except asyncio.TimeoutError:
        return Take(model=panelist.name, text="", error=f"{panelist.name}: 超时({timeout}s)")
    except Exception as e:
        return Take(model=panelist.name, text="", error=f"{panelist.name}: {type(e).__name__}: {e}")


# ── 阶段一:独立盲审(P3: gather 并行,零共享) ──────────────────────────────────

BLIND_SYSTEM = """你是一位独立评审员。请对下面的决策问题给出你的真实判断。

要求:
1. 明确倾向(倾向 A 方案 / B 方案 / 倾向某个方向),禁止模棱两可
2. 关键理由(2-3 条)
3. 你的判断依赖哪些前提假设
4. 最大风险是什么
5. 最易被忽略的因素是什么

禁止:不得看其他评审意见(你没有这个能力),不得说"综合来看",不得回避立场。
≤300 字。"""


async def _gather(question: str) -> list[Take]:
    """并行盲审。单个模型失败不阻塞其余;存活 < 2 条则终止。"""
    # P1 警告:检测同厂商
    vendors = [p.base_url.split("/")[2] for p in PANEL]
    seen: dict[str, str] = {}
    for p, v in zip(PANEL, vendors):
        if v in seen:
            console.print(f"[yellow]⚠ P1 警告:[/] {p.name} 与 {seen[v]} 同厂商,去相关收益降低")
        else:
            seen[v] = p.name

    takes = await asyncio.gather(
        *[_complete(p, question, BLIND_SYSTEM, temperature=0.7) for p in PANEL]
    )
    ok = [t for t in takes if not t.error]
    if len(ok) < 2:
        console.print(f"[red]✗[/] 存活意见 {len(ok)} 条(< 2),无法形成有效分歧。")
        for t in takes:
            if t.error:
                console.print(f"  [yellow]⚠[/] {t.model}: {t.error}")
            else:
                console.print(f"  [green]✓[/] {t.model}")
        sys.exit(1)
    return takes


# ── 匿名化(P3: 防止模型偏袒特定厂商) ────────────────────────────────────────

def _anon(takes: list[Take]) -> str:
    """将 Take 列表匿名化为【观点A/B/C…】文本。"""
    labels = "ABCDEFGHIJ"
    lines = []
    for i, t in enumerate(takes):
        if t.error:
            continue
        lines.append(f"【观点{labels[i]}】\n{t.text}")
    return "\n\n---\n\n".join(lines)


# ── 阶段二:书记员(P2: 只做结构化抽取,禁止下结论) ─────────────────────────────

FACILITATOR_SYSTEM = """你是一位结构化决策书记员。你的任务是把多位独立评审的意见整理成决策地图。

严格禁止:
- 不得下结论、不得选最优、不得给推荐
- 不得说"建议选择 X"
- 不得对任何观点做优劣评价

输出格式(必须严格遵循):

## 共识区
> ⚠️ 一致≠正确,可能是共同盲区

(列出所有意见都认同的点)

## 分歧区
(每条格式:)
### 分歧 N: [争议标题]
- **各方立场**: 观点A 认为…, 观点B 认为…
- **导致分歧的隐含变量**: (是什么事实/假设的差异导致了分歧)

## 独有考量
(仅一方提出的点——常是补盲价值最高的)

## 未定变量
(把隐含变量提炼成「决策者必须先回答的问题」清单)"""


async def _facilitator(anonymized: str) -> str:
    p = FACILITATOR_MODEL
    return (await _complete(p, anonymized, FACILITATOR_SYSTEM, temperature=0.4)).text


# ── 阶段三:对抗性审查 ────────────────────────────────────────────────────────

ADVERSARY_SYSTEM = """你是一位对抗性审查员。你的任务是攻击多数意见,暴露盲区。

三个固定任务(≤250 字,语气尖锐、具体):

1. **共同假设**:指出所有意见共同默认、未经检验的假设
2. **少数派 steelman**:为被冷落的相反结论做最强辩护
3. **多数意见错在哪**:如果多数意见是错的,什么必须成立?现实中可能性多大?

禁止:不得和稀泥,不得说"各有道理"。"""


async def _adversary(anonymized: str) -> str:
    p = ADVERSARY_MODEL
    return (await _complete(p, anonymized, ADVERSARY_SYSTEM, temperature=0.5)).text


# ── 报告拼装 + 落盘 ─────────────────────────────────────────────────────────

def _report(question: str, takes: list[Take], decision_map: str, adversary_report: str) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# 圆桌决策报告",
        f"",
        f"**问题**: {question}",
        f"**时间**: {ts}",
        f"",
        f"---",
        f"",
        f"## P1: 各模型原始意见",
        f"",
    ]
    for t in takes:
        if t.error:
            lines.append(f"### ⚠️ {t.model} (失败: {t.error})")
        else:
            lines.append(f"### {t.model}")
            lines.append(t.text)
        lines.append("")

    lines += [
        "---",
        "",
        "## P2: 决策地图",
        "",
        decision_map,
        "",
        "---",
        "",
        "## P3: 对抗性审查",
        "",
        adversary_report,
        "",
        "---",
        "",
        "> **决策权在你。** 共识是警报不是背书;优先看未定变量与对抗审查。",
    ]
    return "\n".join(lines)


# ── HTML 报告生成 ────────────────────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>圆桌决策报告 — {question_short}</title>
<style>
  :root {{ --bg: #0d1117; --fg: #c9d1d9; --accent: #58a6ff; --warn: #d29922;
           --border: #30363d; --card: #161b22; --green: #3fb950; --red: #f85149; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: var(--bg); color: var(--fg); font-family: -apple-system, BlinkMacSystemFont,
         "Segoe UI", Helvetica, Arial, sans-serif; line-height: 1.6; padding: 2rem; }}
  .container {{ max-width: 900px; margin: 0 auto; }}
  h1 {{ color: var(--accent); font-size: 1.8rem; margin-bottom: 0.5rem; }}
  h2 {{ color: var(--green); font-size: 1.3rem; margin: 2rem 0 1rem; padding-bottom: 0.5rem;
       border-bottom: 1px solid var(--border); }}
  h3 {{ color: var(--accent); font-size: 1.1rem; margin: 1.5rem 0 0.5rem; }}
  .meta {{ color: #8b949e; font-size: 0.9rem; margin-bottom: 2rem; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px;
           padding: 1.2rem; margin: 1rem 0; }}
  .card.warn {{ border-left: 3px solid var(--warn); }}
  .card.ok {{ border-left: 3px solid var(--green); }}
  blockquote {{ border-left: 3px solid var(--warn); padding: 0.5rem 1rem; margin: 1rem 0;
                background: rgba(210,153,34,0.1); border-radius: 4px; }}
  strong {{ color: var(--accent); }}
  code {{ background: #21262d; padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.9em; }}
  pre {{ background: #21262d; padding: 1rem; border-radius: 8px; overflow-x: auto; }}
  .footer {{ margin-top: 3rem; padding: 1rem; border-top: 1px solid var(--border);
             color: #8b949e; font-size: 0.85rem; text-align: center; }}
  .nav {{ position: sticky; top: 0; background: var(--bg); padding: 0.5rem 0;
          border-bottom: 1px solid var(--border); margin-bottom: 2rem; z-index: 10; }}
  .nav a {{ color: var(--accent); text-decoration: none; margin-right: 1.5rem; font-size: 0.9rem; }}
  .nav a:hover {{ text-decoration: underline; }}
  @media (max-width: 600px) {{ body {{ padding: 1rem; }} }}
</style>
</head>
<body>
<div class="container">
  <nav class="nav">
    <a href="#p1">P1 原始意见</a>
    <a href="#p2">P2 决策地图</a>
    <a href="#p3">P3 对抗审查</a>
  </nav>
  <h1>圆桌决策报告</h1>
  <div class="meta">
    <strong>问题</strong>: {question}<br>
    <strong>时间</strong>: {ts}<br>
    <strong>面板</strong>: {panel_info}
  </div>
  {body_html}
  <div class="footer">
    决策权在你。共识是警报不是背书;优先看未定变量与对抗审查。
  </div>
</div>
</body>
</html>
"""


def _md_to_html(md_text: str) -> str:
    """Markdown → HTML。"""
    import markdown
    return markdown.markdown(md_text, extensions=["extra", "nl2br"])


def _generate_html(question: str, takes: list[Take], md_report: str) -> str:
    """从 Markdown 报告生成完整 HTML。"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    panel_info = " / ".join(
        f"{t.model}{'⚠️' if t.error else '✅'}" for t in takes
    )

    # 拆分 P1/P2/P3 段落
    parts = md_report.split("---")
    p1_html = _md_to_html(parts[1]) if len(parts) > 1 else ""
    p2_html = _md_to_html(parts[2]) if len(parts) > 2 else ""
    p3_html = _md_to_html(parts[3]) if len(parts) > 3 else ""

    body_html = f"""
    <h2 id="p1">P1: 各模型原始意见</h2>
    <div class="card ok">{p1_html}</div>
    <h2 id="p2">P2: 决策地图</h2>
    <div class="card">{p2_html}</div>
    <h2 id="p3">P3: 对抗性审查</h2>
    <div class="card">{p3_html}</div>
    """

    return HTML_TEMPLATE.format(
        question=question,
        question_short=question[:30],
        ts=ts,
        panel_info=panel_info,
        body_html=body_html,
    )


# ── CLI 入口 ──────────────────────────────────────────────────────────────────

async def _run(question: str, no_browser: bool = False) -> None:
    ts_label = datetime.now().strftime("%Y%m%d_%H%M")

    # 阶段一
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]阶段一:独立盲审中..."),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("gather", total=None)
        takes = await _gather(question)

    ok = [t for t in takes if not t.error]
    console.print(f"[green]✓[/] 收到 [bold]{len(ok)}/{len(takes)}[/] 条有效意见")
    for t in takes:
        if t.error:
            console.print(f"  [yellow]⚠[/] {t.model}: {t.error}")

    # 匿名化
    anon = _anon(takes)

    # 阶段二 & 三(并行)
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]阶段二/三:书记员 + 对抗审查..."),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("analyze", total=None)
        decision_map, adversary_report = await asyncio.gather(
            _facilitator(anon),
            _adversary(anon),
        )
    console.print("[green]✓[/] 分析完成")

    # 拼装 Markdown 报告
    md_report = _report(question, takes, decision_map, adversary_report)

    # 终端输出(用 rich 渲染 Markdown)
    console.print()
    console.print(Markdown(md_report))

    # 落盘 Markdown
    md_file = f"roundtable_{ts_label}.md"
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(md_report)

    # 生成 HTML 并打开浏览器
    html = _generate_html(question, takes, md_report)
    html_file = f"roundtable_{ts_label}.html"
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html)

    console.print(f"\n[green]✓[/] Markdown: [bold]{md_file}[/]")
    console.print(f"[green]✓[/] HTML:     [bold]{html_file}[/]")

    if not no_browser:
        webbrowser.open(Path(html_file).resolve().as_uri())
        console.print("[green]✓[/] 已在浏览器中打开")


def main() -> None:
    global TIMEOUT  # noqa: PLW0603
    parser = argparse.ArgumentParser(
        description="多模型圆桌决策工具 — 独立盲审 / 结构化抽取 / 对抗审查",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               '  roundtable "该不该把感知模块从 A 架构重构成 B"\n'
               "  roundtable            # 无参数则交互输入\n"
               "  roundtable --no-browser  # 不自动打开浏览器",
    )
    parser.add_argument("question", nargs="?", default=None, help="决策问题(省略则交互输入)")
    parser.add_argument("--timeout", type=int, default=TIMEOUT, help=f"单模型超时秒数(默认 {TIMEOUT})")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    TIMEOUT = args.timeout

    question = args.question
    if not question:
        question = input("请输入决策问题: ").strip()
        if not question:
            console.print("[red]✗[/] 问题不能为空")
            sys.exit(1)
    asyncio.run(_run(question, no_browser=args.no_browser))


if __name__ == "__main__":
    main()
