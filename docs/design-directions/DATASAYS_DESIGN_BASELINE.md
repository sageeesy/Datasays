# DataSays Design Baseline — Current References

本记录用于保存 DataSays 当前阶段最重要的设计参考，防止后续探索丢失已经验证有效的产品关系。它不是最终设计规范，也不代表已经批准实施。

当前参考页面：

- Original 04 Evidence Workbench: [`04-workbench.html`](./04-workbench.html)
- 04C AI-native Workbench: [`04C-ai-native.html`](./workbench-refinement/04C-ai-native.html)
- Controlled comparison: [`workbench-refinement/index.html`](./workbench-refinement/index.html)

## 1. Status

- 当前 DataSays UI 尚未定稿。
- Original 04 和 04C 是当前最重要的两个参考版本，但用途不同。
- Original 04 主要证明 Workbench 产品形态和三栏信息关系是有效的。
- 04C 主要探索 AI input、多轮追问和分析内容增长方式。
- 后续仍需继续评估布局比例、视觉语言、交互细节和响应式行为。
- 不应将任何一个版本直接视为最终实现规范，也不应默认把两者合并。

## 2. Original 04 Evidence Workbench

### Why I Like It

- 三栏结构直观：左侧是 Dataset 与分析上下文，中间是 Analysis Result，右侧是 Evidence。
- Dataset、Analysis Result 和 Evidence 的关系清楚，第一次进入产品也容易理解。
- 用户不需要学习 Canvas、Thread、Artifact 或多文档标签等新的产品心智模型。
- 中间结果是主要工作区，符合“先理解分析，再检查依据”的阅读顺序。
- Evidence 保持可见和可检查，但没有完全取代分析结果。
- Chat / Ask DataSays 仍然存在，因此产品支持持续提问，而不是一次性生成报告。
- 整体更接近 AI Data Analysis Workspace，而不是传统 BI Dashboard 或开发者控制台。

### Elements Worth Preserving

**Layout**

- 左侧导航、中间分析、右侧 Inspector 的稳定三栏骨架。
- 中间区域承担主要阅读和决策任务，两侧栏提供上下文与可信度支持。
- Dataset 和 Evidence 均在工作区内持续可访问，不需要跳转到独立页面。

**Panel hierarchy**

- 中间 Analysis Result 是第一视觉层级。
- 左侧是工作上下文，不应与结果竞争。
- 右侧是 contextual inspector，不应成为第二个主内容区。
- Developer Trace 处于更低层级，并通过折叠逐步披露。

**Navigation**

- 左侧同时容纳当前问题、Dataset 和分析导航的基本方向。
- 顶部产品导航保持简洁，没有把模型、设置或调试状态变成主角。
- 用户能够从结果继续进入 Dashboard、明细或后续分析，但不需要操作 Dashboard Builder。

**Result area**

- 标题、口径说明、KPI、主图和关键发现形成容易扫描的基本顺序。
- KPI 与月度趋势能在首屏建立整体经营判断。
- 结果首先用业务语言表达，技术细节留在 Evidence 与 Trace。

**Evidence location**

- Evidence 常驻右侧，用户可以在不离开结果的情况下核对指标。
- Plan、metric definition、population、join 和 validation 有明确入口。
- Evidence 与当前分析并排出现，强化“结论可以被检查”的产品差异。

**Interaction pattern**

- Ask DataSays 保留在工作区中，支持围绕当前结果继续提问。
- 用户视图优先，Evidence 与 Trace 采用 progressive disclosure。
- 产品不是一条不断增长的聊天记录，而是一个可以持续工作的分析空间。

**Visual balance and density**

- 三栏比例虽然仍需调整，但已能稳定表达“上下文 / 结果 / 依据”的关系。
- 信息密度适合桌面工作台，不会像营销页面一样过度留白。
- 冷静的中性色与绿色验证状态符合数据分析产品的可信、克制气质。
- KPI、图表和发现之间的节奏清楚，用户能快速找到经营概览的主要信息。

### Current Problems

- 整体视觉完成度仍不足，部分细节带有第一版静态概念稿的感觉。
- 某些区域仍有明显的 AI-generated UI 感，例如重复边框、同质化卡片和过小标签。
- 左右栏在桌面宽度中占比偏高，可能压缩中间 Analysis Result。
- Panel、card 和 border 的层级仍可能过重，内容关系有时依赖容器而不是排版建立。
- Typography hierarchy 尚未成熟；正文、标签、KPI 与标题的字号和字重仍需统一。
- Spacing rhythm 偏机械，局部区域缺少紧密组与宽松章节之间的节奏差异。
- Color system 尚未定稿，目前的冷灰和绿色可靠，但品牌辨识度有限。
- 中间分析结果仍可进一步从“组件组合”精炼为更连续的 analytical document。
- 主图的尺寸和视觉权重仍有提升空间。
- Evidence Inspector 的独立 Evidence 卡片偏重，可能与主结果争夺注意力。
- AI input 与当前分析上下文的联系不够明确，其最终位置和交互方式尚未确定。
- Agent Workflow 默认可见时略偏 developer-console-first，不应成为普通用户的主界面内容。

## 3. 04C AI-native Workbench

### Why It Is Interesting

- Ask DataSays input 比 Original 04 更自然地融入当前分析，而不是一个孤立的聊天入口。
- 输入区域明确显示当前 analysis context 和使用的数据集，用户知道下一次提问会作用于什么。
- 用户追问不会退化成传统聊天气泡或左右对话流。
- Follow-up 会在中间结果中成长为新的分析 section，原有分析仍然保留。
- “Added analysis · November diagnosis” 用轻量状态表达 AI 已经完成的动作，而不制造新的产品对象。
- 右侧 Evidence Inspector 会随当前分析 section 切换上下文。
- AI 的存在感更明确，但 KPI、图表、发现和分析结论仍然是视觉主体。

### Elements Worth Preserving

**Ask DataSays input**

- 输入始终可达，但不占据聊天应用式的大面积空间。
- 输入提示使用 “Ask DataSays about this analysis…” 强调围绕当前分析继续工作。
- 输入区域展示当前 analysis context、Dataset 数量和执行动作。

**Current analysis context**

- 中间顶部明确当前正在查看的 analysis section。
- 左侧 Analysis Sections 与右侧 Inspector 使用同一上下文。
- 用户能够理解 Evidence 属于 Overview 还是 November diagnosis。

**Follow-up interaction**

- 用户提出“为什么 11 月 GMV 最高？”后，系统追加诊断 section，而不是生成聊天回复气泡。
- 新 section 使用同一 population 和 metric definition，延续已有分析合同。
- Follow-up 可以引用既有结果，同时新增拆解、发现和 evidence boundary。

**Lightweight AI state**

- “Added analysis” 表达动作完成，但不使用大面积状态卡、AI 渐变或装饰图标。
- AI action 与 analysis artifact 的关系清楚：AI 负责添加分析，分析内容本身负责承载价值。

**State 2 → State 3 growth**

- State 2 是完整的 2017 Overview。
- State 3 保留 Overview，并在其下增加 November diagnosis。
- 左侧 Analysis Sections 增加导航项。
- 中间内容自然向下增长。
- 右侧 Inspector 切换到新 section 的 evidence。
- Ask DataSays 更新当前上下文，但不会产生独立聊天历史。

**AI and Analysis Result relationship**

- AI 是操作和组织分析的入口，不是页面视觉中心。
- Analysis Result 是长期沉淀的工作内容。
- Evidence 为每个分析 section 提供可检查依据。

### Current Problems

- 04C 的整体视觉不一定优于 Original 04；它主要验证交互表达，而不是最终视觉语言。
- 底部 Ask DataSays dock 的存在感可能偏强，长期使用时可能遮挡或分散对结果的注意力。
- Context bar、Analysis Sections、Added analysis 和 Inspector context 同时存在时，可能出现重复表达。
- 某些 AI-native 状态说明可能过度设计，后续需要判断哪些信息真正帮助用户。
- 中间结果的视觉成熟度仍未完全解决，不能仅依靠 AI interaction 提高整体完成度。
- 还需要判断如何在不破坏 Original 04 稳定框架的前提下使用这些交互元素。
- 当前不应直接把 04C 的所有 AI-native 元素合并进 Original 04。

## 4. Current Design Hypothesis

当前假设是：DataSays 未来可能更接近 Original 04 的整体 Workbench framework，加上 04C 中较自然的 AI input 与 follow-up interaction。

这个假设只描述可能的方向，不是实现决定。以下内容仍未确定：

- layout proportions
- typography
- color system
- panel weight
- chart style
- evidence treatment
- AI input placement
- analysis history behavior
- mobile and narrow-screen behavior

**Do not implement this combination yet.**

在实施前，需要先明确哪些 04C 元素解决真实用户问题，哪些只是概念稿中的视觉表达，并验证它们不会削弱 Original 04 已经建立的清晰产品关系。

## 5. Open Design Questions

- 左侧栏最终主要承担 Dataset、Analysis History，还是当前 Analysis navigation？
- 当前问题和历史问题应该如何并存，避免左侧栏越来越重？
- 右侧 Evidence 应该常驻、可折叠，还是由选中结果 context-triggered 展开？
- Evidence Inspector 默认展示一个指标、一个 section，还是完整 evidence inventory？
- 中间区域更接近连续 analytical document，还是具有固定区块的 structured workspace？
- KPI 应采用 card-based、ruled strip，还是更平面的排版方式？
- Chart、table 和 finding 应建立怎样统一的视觉语言？
- AI input 应固定在底部、放在左侧，还是使用 context-aware floating bar？
- 输入区域需要显示多少当前 context，才能既可信又不重复？
- Follow-up 应全部追加到当前分析，还是允许创建新的 analysis section？
- 多轮分析后如何折叠、导航、归档和控制页面增长？
- Evidence 应如何随 section、chart、KPI 或 table selection 切换？
- 中文与英文 typography 如何统一字号、字重、行高和数字表现？
- 色彩系统应更 neutral，还是建立更强但克制的品牌色？
- 绿色应只表示 validation，还是也承担品牌与交互强调？
- Narrow screen 应将 Dataset 与 Evidence 变为抽屉、折叠区，还是按顺序堆叠？
- Mobile 是否只承担查看与轻量追问，而不完整复制桌面工作台？

## 6. Do Not Lose

后续任何 redesign 都不应轻易破坏：

- [ ] Dataset / Analysis Result / Evidence 三者清晰的工作台关系。
- [ ] 中间 Analysis Result 的视觉优先级。
- [ ] 指标、口径、计算与验证的可追踪性。
- [ ] 用户可以围绕现有分析持续追问。
- [ ] Follow-up 能沉淀为分析内容，而不只是聊天消息。
- [ ] 不退化成传统 BI Dashboard 或 Dashboard Builder。
- [ ] 不退化成 ChatGPT clone。
- [ ] 不重新引入 developer-console-first 的默认体验。
- [ ] Evidence-first 不等于 Evidence-heavy。
