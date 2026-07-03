# roundtable — 多模型圆桌决策工具

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Release](https://img.shields.io/badge/Release-v1.0.0-green.svg)](https://github.com/zhangshujuan1314/roundtable/releases)

对**没有标准答案**的决策问题(架构选型、技术路线、职业/产品决策),并行调用多个**异构厂商**的 LLM 做独立盲审,然后结构化呈现「共识/分歧/独有考量/未定变量」,最后由对抗性审查攻击多数意见。

**工具不给答案,只产出决策地图;决策者是人。**

---

## 快速开始(3 步上手)

### 1. 下载安装包

[下载 Roundtable-v1.0.0-Windows.zip](https://github.com/zhangshujuan1314/roundtable/raw/main/Roundtable-v1.0.0-Windows.zip)

### 2. 解压并配置

解压后编辑 `.env` 文件,填入至少 2 家厂商的 API Key:

```env
DEEPSEEK_API_KEY=sk-xxx
ZHIPU_API_KEY=xxx
```

### 3. 双击启动

双击 `Roundtable.bat`,浏览器自动打开,输入决策问题即可。

---

## 获取 API Key

| 厂商 | 获取地址 | 模型 |
|---|---|---|
| DeepSeek | [platform.deepseek.com](https://platform.deepseek.com/api_keys) | deepseek-v4-flash |
| GLM (智谱) | [open.bigmodel.cn](https://open.bigmodel.cn) | glm-5.2 |

---

## 其他安装方式

### pip 安装

```bash
pip install git+https://github.com/zhangshujuan1314/roundtable.git
roundtable-web  # 启动 Web UI
```

### 源码运行

```bash
git clone https://github.com/zhangshujuan1314/roundtable.git
cd roundtable
pip install -r requirements.txt
python -m web.app
```

### 命令行模式

```bash
roundtable "该不该把感知模块从 A 架构重构成 B"
roundtable --timeout 30 "该不该迁移数据库"
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
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  阶段二:书记员(Facilitator)              │
│  输入匿名化意见,结构化抽取,不裁决         │
│  产出: 共识/分歧/独有考量/未定变量        │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  阶段三:对抗性审查(Adversary)            │
│  攻击多数意见:共同假设/少数派 steelman/   │
│  "错在哪才成立"                          │
└────────────────┬────────────────────────┘
                 │
                 ▼
         可视化报告(浏览器)
```

---

## 为什么不是辩论、不是投票

| 方案 | 问题 |
|---|---|
| 多轮辩论到共识 | 违反"无 ground truth ⇒ 不允许裁决者";token 成本几十倍 |
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

## 已知局限

| 编号 | 问题 | 缓解 |
|---|---|---|
| A1 | 书记员 prompt 注入漏洞 | 用户审查报告是否出现隐含推荐 |
| A2 | 盲审 prompt 受问题措辞锚定 | 使用中性措辞提问 |
| A3 | 对抗者在高度一致时硬凑反对 | 设计意图,产出质量由读者判断 |
| A4 | 匿名化被内容自曝绕过 | 实践中罕见,v1 不处理 |

---

## 项目结构

```
roundtable/
├── roundtable.py          # 核心逻辑
├── web/
│   ├── app.py             # Web 服务
│   └── static/
│       └── index.html     # 暗色主题 UI
├── Roundtable.bat         # Windows 双击启动
├── Roundtable-v1.0.0-Windows.zip  # 安装包
├── pyproject.toml         # pip install 配置
├── launcher.py            # PyInstaller 启动器
└── tests/                 # 16 项测试
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
