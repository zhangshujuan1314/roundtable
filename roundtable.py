"""roundtable — 多模型圆桌决策工具(个人版)

对没有标准答案的决策问题,并行调用多个异构厂商 LLM 做独立盲审,
结构化呈现共识/分歧/独有考量/未定变量,最后对抗性审查攻击多数意见。
工具不给答案,只产出决策地图;决策者是人。
"""

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

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
    Panelist(name="DeepSeek",  base_url="https://api.deepseek.com/v1",          api_key_env="DEEPSEEK_API_KEY",  model="deepseek-chat"),
    Panelist(name="Qwen",      base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", api_key_env="DASHSCOPE_API_KEY", model="qwen-plus"),
    Panelist(name="GLM",       base_url="https://open.bigmodel.cn/api/paas/v4", api_key_env="ZHIPU_API_KEY",     model="glm-4-flash"),
]

# Facilitator / Adversary 独立配置(可指向面板中任意模型,也可指向面板外)
# 使用面板中第一个模型作为默认值;编辑此处可指定其他模型
FACILITATOR_MODEL: Panelist = PANEL[0]
ADVERSARY_MODEL: Panelist = PANEL[1] if len(PANEL) > 1 else PANEL[0]

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
            print(f"⚠️  P1 警告: {p.name} 与 {seen[v]} 同厂商,去相关收益降低", file=sys.stderr)
        else:
            seen[v] = p.name

    takes = await asyncio.gather(
        *[_complete(p, question, BLIND_SYSTEM, temperature=0.7) for p in PANEL]
    )
    ok = [t for t in takes if not t.error]
    if len(ok) < 2:
        print(f"❌ 存活意见 {len(ok)} 条(< 2),无法形成有效分歧。", file=sys.stderr)
        for t in takes:
            status = "✅" if not t.error else f"⚠️  {t.error}"
            print(f"  {t.model}: {status}", file=sys.stderr)
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


# ── CLI 入口 ──────────────────────────────────────────────────────────────────

async def _run(question: str) -> None:
    # 阶段一
    takes = await _gather(question)

    # 匿名化
    anon = _anon(takes)

    # 阶段二 & 三(可并行,但 Facilitator 结果不依赖 Adversary)
    decision_map, adversary_report = await asyncio.gather(
        _facilitator(anon),
        _adversary(anon),
    )

    # 拼装报告
    report = _report(question, takes, decision_map, adversary_report)

    # stdout
    print(report)

    # 落盘
    fname = f"roundtable_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n📄 报告已保存: {fname}", file=sys.stderr)


def main() -> None:
    global TIMEOUT  # noqa: PLW0603
    parser = argparse.ArgumentParser(
        description="多模型圆桌决策工具 — 独立盲审 / 结构化抽取 / 对抗审查",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               '  python roundtable.py "该不该把感知模块从 A 架构重构成 B"\n'
               "  python roundtable.py   # 无参数则交互输入",
    )
    parser.add_argument("question", nargs="?", default=None, help="决策问题(省略则交互输入)")
    parser.add_argument("--timeout", type=int, default=TIMEOUT, help=f"单模型超时秒数(默认 {TIMEOUT})")
    args = parser.parse_args()

    TIMEOUT = args.timeout

    question = args.question
    if not question:
        question = input("请输入决策问题: ").strip()
        if not question:
            print("❌ 问题不能为空", file=sys.stderr)
            sys.exit(1)
    asyncio.run(_run(question))


if __name__ == "__main__":
    main()
