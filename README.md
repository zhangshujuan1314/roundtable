# roundtable — 多模型圆桌决策工具

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

对**没有标准答案**的决策问题(架构选型、技术路线、职业/产品决策),并行调用多个**异构厂商**的 LLM 做独立盲审,然后结构化呈现「共识/分歧/独有考量/未定变量」,最后由对抗性审查攻击多数意见。

**工具不给答案,只产出决策地图;决策者是人。**

---

## 安装

```bash
pip install git+https://github.com/zhangshujuan1314/roundtable.git
```

或从源码安装:

```bash
git clone https://github.com/zhangshujuan1314/roundtable.git
cd roundtable
pip install .
```

---

## 配置

```bash
cp .env.example .env
```

编辑 `.env`,填入至少 2 家厂商的 API Key:

```env
DEEPSEEK_API_KEY=sk-xxx
ZHIPU_API_KEY=xxx
```

支持的厂商:

| 厂商 | 环境变量 | 模型 |
|---|---|---|
| DeepSeek | `DEEPSEEK_API_KEY` | deepseek-v4-flash |
| Qwen (DashScope) | `DASHSCOPE_API_KEY` | qwen-plus |
| GLM (智谱) | `ZHIPU_API_KEY` | glm-5.2 |

---

## 使用

### Web UI(推荐)

```bash
# 启动 Web 界面(自动打开浏览器)
roundtable-web

# 或从源码
python -m web.app

# Windows 双击
start.bat
```

浏览器打开 `http://127.0.0.1:7800`,输入问题即可。

### 命令行

```bash
# 直接提问
roundtable "该不该把感知模块从 A 架构重构成 B"

# 交互模式
roundtable

# 指定超时
roundtable --timeout 30 "该不该迁移数据库"

# 不打开浏览器
roundtable --no-browser "问题"
```

---

## 工作流程

```
用户问题
   │
   ▼
┌─────────────────────────────────────────┐
│  阶段一:独立盲审                         │
│  N 个异构模型并行,同一中性 prompt,互不可见 │
│  产出: List[Take{model, text}]          │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  阶段二:书记员(Facilitator)              │
│  输入匿名化意见,结构化抽取,不裁决         │
│  产出: 决策地图                          │
│  (共识/分歧+隐含变量/独有考量/未定变量)    │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  阶段三:对抗性审查(Adversary)            │
│  攻击多数意见:共同假设/少数派 steelman/   │
│  "错在哪才成立"                          │
│  产出: 对抗报告                          │
└────────────────┬────────────────────────┘
                 │
                 ▼
         Markdown 报告
    (stdout + 落盘 roundtable_YYYYMMDD_HHMM.md)
```

---

## 为什么不是辩论、不是投票

| 方案 | 问题 |
|---|---|
| 多轮辩论到共识 | 违反"无 ground truth ⇒ 不允许裁决者";token 成本几十倍,收益证据弱 |
| 多数投票选答案 | 相关误差会被投票放大(同源语料高度重叠) |
| 给模型分配人设 | 角色扮演污染真实判断 |

---

## 原理速览

四条第一性原理:

1. **P1 收益来源 = 误差去相关** → 面板必须异构(不同厂商)
2. **P2 无 ground truth ⇒ 不允许裁决者** → 书记员只做抽取,禁止下结论
3. **P3 共享上下文 ⇒ 锚定与附和** → 阶段一严格盲审,阶段二/三匿名化
4. **P4 人是唯一决策者** → 输出无评分/排序,报告末尾固定提示

---

## 测试

```bash
pip install pytest
python -m pytest tests/ -v
```

---

## 已知局限

### A1: 书记员 prompt 注入漏洞
意见文本中的注入指令可能诱导输出推荐性表述。v2 可增加输出校验层。

### A2: 盲审 prompt 受问题措辞锚定
问题带倾向时模型会被框架影响。用户应使用中性措辞。

### A3: 对抗者在高度一致时硬凑反对
设计意图——当所有人同意时最需要挑战共同假设。产出质量由读者判断。

### A4: 匿名化被内容自曝绕过
理论上可行,实践中罕见。v1 选择不处理。

---

## 项目结构

```
roundtable/
├── roundtable.py          # 核心逻辑(单文件)
├── __main__.py            # python -m roundtable
├── pyproject.toml         # 包配置(pip install)
├── start.bat              # Windows 双击启动 Web UI
├── .env.example           # 环境变量模板
├── requirements.txt       # 依赖
├── LICENSE                # MIT
├── README.md              # 本文件
├── web/
│   ├── app.py             # Web 服务(标准库 HTTP)
│   ├── __main__.py        # python -m web.app
│   └── static/
│       └── index.html     # 暗色主题 UI
└── tests/
    └── test_roundtable.py # 16 项测试
```

---

## Contributing

欢迎 Issue 和 PR。请确保:

1. 新增功能需附带测试
2. 遵循现有代码风格
3. 不引入新框架依赖

---

## License

[MIT](LICENSE)
