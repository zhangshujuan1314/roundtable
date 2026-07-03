"""T1-T4: 对抗性审查流程测试(mock API,不真实调用)"""

import asyncio
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, ".")
from roundtable import (
    PANEL,
    Take,
    _anon,
    _complete,
    _facilitator,
    _adversary,
    _gather,
    _report,
    Panelist,
)


# ── T1: 匿名化输出不含任何厂商名 ─────────────────────────────────────────────

def test_anon_no_vendor_names():
    """T1: _anon() 输出的标签不含任何厂商名(文本内容由模型生成,不含自报家门)。"""
    takes = [Take(model=p.name, text=f"独立意见{i}:倾向A方案") for i, p in enumerate(PANEL)]
    result = _anon(takes)
    # 标签只含【观点A/B/C】,不含厂商名
    for p in PANEL:
        assert f"【{p.name}】" not in result, f"匿名化标签出现厂商名: {p.name}"
    # 验证标签格式正确
    assert "【观点A】" in result
    assert "【观点B】" in result


def test_anon_skips_errors():
    """T1 补充: 失败的 Take 不出现在匿名化输出中。"""
    takes = [
        Take(model="A", text="ok"),
        Take(model="B", text="", error="timeout"),
    ]
    result = _anon(takes)
    assert "【观点A】" in result
    assert "观点B" not in result


# ── T2: 单模型失败不影响其余 ──────────────────────────────────────────────────

def test_gather_single_failure(monkeypatch):
    """T2: mock 一个模型抛异常,其余正常,应返回存活意见。"""
    from roundtable import _complete as real_complete

    async def mock_complete(panelist, *args, **kwargs):
        if panelist.name == PANEL[0].name:
            return Take(model=panelist.name, text="", error="模拟异常")
        return Take(model=panelist.name, text=f"{panelist.name}的独立意见,倾向A方案,理由充分")

    monkeypatch.setattr("roundtable._complete", mock_complete)

    async def run():
        return await _gather("测试问题")

    takes = asyncio.run(run())
    ok = [t for t in takes if not t.error]
    assert len(ok) >= 2, "单模型失败后存活意见应 ≥ 2"


# ── T3: 存活 < 2 时退出码 1 且信息明确 ────────────────────────────────────────

def test_gather_insufficient_exits(monkeypatch):
    """T3: 存活意见 < 2 时应 sys.exit(1)。"""
    async def mock_complete(panelist, *args, **kwargs):
        return Take(model=panelist.name, text="", error="全部失败")

    monkeypatch.setattr("roundtable._complete", mock_complete)

    async def run():
        return await _gather("测试问题")

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(run())
    assert exc_info.value.code == 1


# ── T4: 报告包含全部四个 P2 小节标题与脚注 ────────────────────────────────────

def test_report_structure():
    """T4: 报告必须包含 P1/P2/P3 各节标题及固定脚注。"""
    takes = [Take(model="A", text="意见A"), Take(model="B", text="意见B")]
    dm = "## 共识区\n\n## 分歧区\n\n## 独有考量\n\n## 未定变量"
    adv = "对抗审查内容"
    report = _report("测试问题", takes, dm, adv)

    # P2 四个小节
    for section in ["共识区", "分歧区", "独有考量", "未定变量"]:
        assert section in report, f"报告缺少小节: {section}"

    # P4 脚注
    assert "决策权在你" in report

    # P1 各模型原始意见
    assert "P1: 各模型原始意见" in report


# ── 补充:_complete 正常调用(mock) ─────────────────────────────────────────────

def test_complete_success(monkeypatch):
    """mock OpenAI 返回,验证 _complete 正常路径。"""
    mock_response = AsyncMock()
    mock_response.choices = [AsyncMock(message=AsyncMock(content="模型的回答"))]

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("roundtable.AsyncOpenAI", return_value=mock_client):
        monkeypatch.setenv("TEST_KEY", "sk-test")
        p = Panelist(name="TestModel", base_url="http://test", api_key_env="TEST_KEY", model="m")
        take = asyncio.run(_complete(p, "问题"))

    assert take.text == "模型的回答"
    assert take.error is None
