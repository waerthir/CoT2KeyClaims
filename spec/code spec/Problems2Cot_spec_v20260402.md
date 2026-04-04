# Problems2Cot Spec

## 1. 目标

本 spec 描述当前版本 `Problems2Cot` 的具体设计。

这一版第二层不再把 CoT 组织成“大主包 + 子碎片”的双层结构，而是直接以“单个题目、单个方法、单个文件”为唯一持久化单位。

当前版本的目标是：

- 读取第一层 `Raw2Problems` 输出的 `ProblemPackage`
- 扫描当前仓库中已经存在的 CoT 文件
- 恢复并继续未完成的任务
- 若当前完整解法数量不足，则按需新增新的候选 CoT 文件
- 对每个候选按固定顺序串行检查
- 只保留通过全部检查的完整 CoT 文件
- 让下一层 `CotT2keyClaims` 直接读取完整 CoT 文件，而不是先依赖第二层再合并一个大文件

这一版的关键变化有四个：

1. `cot` 改为单个字符串字段，不再使用列表式 `cot_steps`
2. `layer_cot/aaa/` 目录下直接存放 CoT 文件，不再使用 `CoT_fragments/` 子目录
3. 第二层不再生成 `layer_cot/aaa/aaa.json` 这种汇总主包
4. 被判定失败或重复的候选文件直接删除，不再保留 `discard` 终止文件

这个设计的核心意图是：

- 减少重复状态
- 让恢复逻辑更简单
- 让下游接口更直接
- 保持“中途中断后可继续”的能力

## 2. 输入输出边界

### 2.1 输入

当前版本仍按“工作单元”读取输入。

建议与第一层保持一致：

- 默认遍历 `layer_problem/` 下的所有一级子目录
- 每个工作单元目录都视为一个输入对象
- 若未来配置中加入 `target_work_units`，则只处理指定工作单元
- 工作单元按名称排序后依次纳入任务系统

单个工作单元的输入是：

- `layer_problem/aaa/aaa.json`

这个输入文件就是第一层输出的 `ProblemPackage`。

### 2.2 输出

当前版本只产生一种持久化输出：

- `layer_cot/aaa/<problem_id>_<method_id>.json`

示例：

- `layer_cot/aaa/prob_9b0a7ef70ee83d702776eea6_1.json`

明确约束：

- 不再创建 `layer_cot/aaa/CoT_fragments/` 子目录
- 不再生成 `layer_cot/aaa/aaa.json`
- CoT 文件一旦创建或更新，必须立即写盘
- 若候选被判定失败或重复，则直接删除对应文件

## 3. 标识规则

### 3.1 `file_id`

- `file_id` 是字符串字段
- 当前版本中，`file_id` 直接取自工作单元目录名
- 示例：工作单元目录名为 `aaa`

### 3.2 `problem_id`

- `problem_id` 直接继承自第一层 `ProblemPackage`
- 第二层绝不重新生成 `problem_id`
- 示例：`prob_9b0a7ef70ee83d702776eea6`

### 3.3 `method_id`

- `method_id` 是整数，不是字符串
- 同一 `problem_id` 下，新的候选 CoT 在创建时分配一个新的 `method_id`

当前版本建议的最简分配规则是：

- 扫描当前工作单元目录中该题仍然存在的 CoT 文件
- 取其中同一 `problem_id` 的最大 `method_id`
- 新文件使用 `max + 1`
- 若当前不存在该题的任何 CoT 文件，则从 `1` 开始

补充说明：

- 当前版本不维护独立的“历史尝试计数器”
- 已删除文件的 `method_id` 不需要额外保留
- 这个简化方案足够支撑当前层与下一层的语义

### 3.4 文件命名规则

文件名统一使用：

- `problem_id + "_" + method_id + ".json"`

示例：

- 若 `problem_id = prob_9b0a7ef70ee83d702776eea6`
- 且 `method_id = 1`
- 则文件名为 `prob_9b0a7ef70ee83d702776eea6_1.json`

这样设计的原因是：

- 方便直接按题目和方法读取
- 方便启动时扫描已有文件
- 方便下一层按文件粒度直接消费

## 4. 第二层读取的输入对象

第二层直接读取第一层输出的 `ProblemPackage`。

示例：

```json
{
  "file_id": "aaa",
  "stage": "raw_to_problem",
  "source_file_name": "actual_input_file.json",
  "problems": [
    {
      "problem_id": "prob_9b0a7ef70ee83d702776eea6",
      "question_text": "题目文本",
      "standard_answer": "标准答案",
      "images": ["test/img1.png"],
      "source_meta": {},
      "multi_solution_hint": null,
      "ingest_status": "ready"
    }
  ]
}
```

当前第二层最关心的输入字段是：

- `file_id`
- `problem_id`
- `question_text`
- `standard_answer`
- `images`
- `multi_solution_hint`

## 5. CoT 文件结构

### 5.1 文本式 `cot`

当前版本中，一个 CoT 就是一个字符串字段：

- 字段名为 `cot`
- 类型是单个字符串
- 不再使用列表式 `cot_steps`

这个字符串可以包含多行文本，也可以在字符串内部自行写成“步骤 1 / 步骤 2 / 步骤 3”的样式，但在 JSON 结构层面它始终只是一个字符串。

### 5.2 核心标志位

每个 CoT 文件保留四个核心标志位：

1. `answer_matches_standard`
   表示该候选给出的最终答案是否和标准答案一致

2. `gemini_checked`
   表示该候选是否已经经过 Gemini 细节性检查

3. `is_duplicate_with_existing_complete_method`
   表示该候选是否与现有完整解法重复

4. `is_complete_fragment`
   表示该候选是否已经成为一个可直接下放到下一层的完整 CoT

补充说明：

- `answer_matches_standard = false` 的文件不会继续保留
- `is_duplicate_with_existing_complete_method = true` 的文件也不会继续保留
- 因此，磁盘上长期存在的文件只会是“未完成”或“完整”两类

### 5.3 `CoTFragment`

当前版本建议的文件结构为：

```json
{
  "file_id": "aaa",
  "problem_id": "prob_9b0a7ef70ee83d702776eea6",
  "method_id": 1,
  "cot": "步骤1\n步骤2\n步骤3",
  "generated_answer": "模型答案",
  "standard_answer": "标准答案",
  "answer_matches_standard": null,
  "gemini_checked": false,
  "is_duplicate_with_existing_complete_method": null,
  "is_complete_fragment": false
}
```

字段说明：

- `cot`
  当前候选里的完整 CoT 文本
- `generated_answer`
  当前候选里的最终答案
- `standard_answer`
  从第一层继承的标准答案
- `answer_matches_standard`
  初始为 `null`
  答案检查通过后写为 `true`
  若检查失败，当前文件直接删除
- `gemini_checked`
  初始为 `false`
  Gemini 完成细节检查并写回新版本 CoT 后写为 `true`
- `is_duplicate_with_existing_complete_method`
  初始为 `null`
  判重通过后写为 `false`
  若判定重复，当前文件直接删除
- `is_complete_fragment`
  初始为 `false`
  只有通过全部流程后，才写为 `true`

### 5.4 关于 discard

当前版本不再把 `discard` 设计成一类需要长期保留的文件状态。

这里的“discard”在实现上解释为：

- 候选被判定为无效
- 文件立即删除
- 后续恢复与任务分配都不再考虑它

当前版本的删除条件有两种：

- `answer_matches_standard = false`
- `is_duplicate_with_existing_complete_method = true`

这套做法在当前阶段是合理的，因为：

- 第二层真正需要持久化的只有“未完成任务”和“完整结果”
- 被淘汰的候选不会被下一层使用
- 上游 `ProblemPackage` 和当前保留下来的 CoT 文件已经足够恢复任务系统

如果未来需要审计失败候选，再单独设计日志或归档机制，而不是依赖当前目录中的终止文件。

## 6. 与下一层的边界

下一层 `CotT2keyClaims` 应直接读取：

- `layer_cot/aaa/` 下的 CoT 文件

消费规则建议为：

- 只读取 `is_complete_fragment = true` 的文件
- 未完成文件视为当前层内部状态，不下放

也就是说，第二层当前的真实输出接口就是“完整 CoT 文件集合”，而不是一个额外再打包的大 JSON。

## 7. 模块设计

你的这套调整是合理的。

尤其是下面四点是对的：

- `cot` 统一成字符串后，下游结构更稳定
- 去掉第二层主包后，状态不再重复维护
- 让下一层直接读 CoT 文件，会比先合并再拆更简单
- 只保留未完成和完整文件，恢复逻辑会更干净

当前版本建议整理成九个模块。

### 7.1 `ProblemPackageReader`

职责：

- 读取 `layer_problem/aaa/aaa.json`
- 解析第一层输出的 `ProblemPackage`
- 提取当前工作单元的题目列表

边界：

- 只负责读取和解析
- 不负责扫描 CoT 文件
- 不负责调用模型

### 7.2 `CoTFragmentScanner`

职责：

- 扫描 `layer_cot/aaa/`
- 读取当前工作单元已经存在的全部 CoT 文件
- 按 `problem_id` 聚合
- 区分：
  - 完整文件
  - 未完成文件

当前建议分类规则：

- `is_complete_fragment = true`
  视为完整文件
- 其余现存文件
  视为未完成文件

当前版本中不存在“已 discard 文件”这一类持久化对象，因为它们已经被删除。

### 7.3 `MethodQuotaInspector`

职责：

- 判断当前每道题理论上需要几个完整解法

当前版本建议最小规则：

- 若 `multi_solution_hint` 为空或不要求多解，则目标完整文件数为 `1`
- 若 `multi_solution_hint` 明确要求多解，则目标完整文件数由配置决定
- 当前常见目标值可以是 `3`

### 7.4 `GlobalTaskManager`

职责：

- 读取所有选中的工作单元
- 汇总上游题目列表
- 汇总当前层现存的 CoT 文件
- 结合目标解法数量，生成全局待执行任务队列

这里的“全局”指的是：

- 它看到的不是某一个单独题目
- 而是当前一次运行中所有工作单元、所有题目、所有现存 CoT 文件

它只负责判断“还有哪些任务没完成”，不负责亲自执行具体检查步骤。

当前版本建议输出两类任务：

1. `resume_fragment`
   继续处理一个已经存在但尚未完成的 CoT 文件

2. `create_new_fragment`
   为某道题新建一个新的候选 CoT 文件

当前版本建议的分配策略：

- 先把所有现存未完成文件加入任务队列
- 再检查哪些题目的完整文件数仍未达到目标
- 对于“尚未达标且当前没有未完成文件”的题目，加入一个 `create_new_fragment` 任务
- 同一题目在一次启动中，最多只新增一个新的候选文件
- 已经达到目标完整数量的题目，不再分配任务

补充说明：

- `GlobalTaskManager` 不需要知道某个未完成文件具体卡在答案检查、判重还是 Gemini
- 它只需要知道“这个文件还没有完成”
- 真正恢复到哪一步，由后续执行器根据文件中的标志位自动判断

### 7.5 `FragmentTaskExecutor`

职责：

- 接收 `GlobalTaskManager` 下发的单个任务
- 若任务类型是 `create_new_fragment`，先创建一个新的 CoT 文件
- 若任务类型是 `resume_fragment`，直接读取现存文件
- 读取文件标志位，自动判断下一步该执行哪个工序
- 将文件一直推进到“完成”或“删除”为止

它是“导入工序后自动执行未完成部分”的具体承担者。

### 7.6 `CoTGenerator`

职责：

- 接收单个题目任务
- 调用 OpenAI 接口
- 生成一个新的原始 CoT 候选

当前版本建议输入：

- `file_id`
- `problem_id`
- `method_id`
- `question_text`
- `standard_answer`
- `images`
- `multi_solution_hint`

当前版本建议输出：

- `cot`
- `generated_answer`

生成完成后，立即保存为一个新的 CoT 文件。

### 7.7 `AnswerMatcher`

职责：

- 读取候选文件
- 检查 `generated_answer` 是否和 `standard_answer` 一致
- 若一致，则把 `answer_matches_standard = true` 写回文件
- 若不一致，则直接删除该文件

### 7.8 `DuplicateMethodChecker`

职责：

- 读取已经通过答案检查的候选文件
- 只与现有完整文件比较
- 判断该候选是否与现有完整解法重复
- 若不重复，则把 `is_duplicate_with_existing_complete_method = false` 写回文件
- 若重复，则直接删除该文件

补充说明：

- 这里检查的是“解法是否重复”
- 不是只看最终答案字符串

### 7.9 `GeminiDetailChecker`

职责：

- 读取已经通过前两关的候选文件
- 调用 Gemini 3 Flash 做细节性检查
- Gemini 必须输出一个新的 CoT
- 用新的 `cot` 覆盖或更新文件中的原始 `cot`
- 必要时也可更新 `generated_answer`
- 把 `gemini_checked = true` 写回文件
- 再把 `is_complete_fragment = true` 写回文件
- 然后立即保存文件

当前版本假定：

- Gemini 不只是返回一个“通过/不通过”标记
- 它应直接产出一版可落盘的新 CoT 文本

## 8. 单题内部的串行回路

对单个问题来说，处理顺序固定为：

1. 若没有可恢复文件且仍需新解法，则生成一个新的 CoT 文件
2. 若该文件还没做答案检查，则运行 `AnswerMatcher`
3. 若答案检查已通过且还没做判重，则运行 `DuplicateMethodChecker`
4. 若判重已通过且还没做 Gemini 细查，则运行 `GeminiDetailChecker`
5. 若 `is_complete_fragment = true`，则该文件视为完整结果

如果在中间任何一步程序断掉，下次启动时：

- `GlobalTaskManager` 会重新发现这个未完成文件
- `FragmentTaskExecutor` 读取它的标志位
- 自动从尚未完成的那一步继续执行

这就是当前版本抗中断、抗断网的核心设计。

## 9. 多线程策略

当前版本明确规定：

- 多线程只用于“多题并行”或“多工作单元并行”
- 单个问题内部不允许并行跑多个检查步骤
- 单个问题内部始终是串行链路

这样做的原因是：

- 简化恢复逻辑
- 简化 `method_id` 分配
- 避免同一题目内部多个候选同时竞争状态

## 10. 多解控制策略

当前版本支持可控地停止。

设计原则是：

- 若目标只要一个完整解法，那么收集到一个完整文件就可以停
- 若目标要三个完整解法，那么必须收集到三个完整文件才停

当前版本建议由 `MethodQuotaInspector` 决定目标数量，由 `GlobalTaskManager` 负责据此分配任务。

并且当前版本保留一个重要限制：

- 每次程序启动时，对每个题目最多只新增一个新的候选文件

这样虽然推进速度慢一点，但好处是：

- 更容易恢复
- 更容易排查
- 更容易控制多解数量

## 11. 当前版本的简单中文系统提示词

下面是一个可以直接作为起点的简单 `system prompt` 草稿。

```text
你现在负责为单个题目生成一条结构化的解题结果。

你会收到以下信息：
1. `question_text`：题目文本
2. `standard_answer`：标准答案
3. `images`：题目相关图片的相对路径列表
4. `multi_solution_hint`：是否多解的预留字段

你的任务是：
1. 阅读题目文本、标准答案和图片路径信息
2. 生成一条简洁、必要、按顺序展开的推理文本
3. 生成一个最终答案字符串

输出要求：
- 只能输出合法 JSON，不要输出任何额外解释
- 顶层只能有两个字段：`cot` 和 `generated_answer`
- `cot` 必须是单个字符串，不要输出字符串列表
- 如有需要，可以在 `cot` 字符串内部用换行写成“步骤1 / 步骤2 / 步骤3”
- `generated_answer` 必须是单个字符串
- 推理内容要围绕解题所必需的信息展开
- 不要输出空话，不要输出与解题无关的说明
- 不要输出 markdown 代码块，不要输出前后缀说明
- 不要把“根据标准答案可知”这类话直接写进推理
- 如果图片路径存在，应将其视为题目可用信息，但不要在输出中重复罗列路径本身
- `generated_answer` 应尽量与 `standard_answer` 保持同样或极接近的表述
```

当前版本建议 `CoTGenerator` 要求模型输出：

```json
{
  "cot": "步骤1\n步骤2\n步骤3",
  "generated_answer": "最终答案"
}
```

## 12. 当前版本的整体执行顺序

当前版本建议的整体执行顺序是：

1. 枚举 `layer_problem/` 下的目标工作单元
2. `ProblemPackageReader` 读取各工作单元的 `ProblemPackage`
3. `CoTFragmentScanner` 扫描 `layer_cot/<file_id>/` 下现存 CoT 文件
4. `MethodQuotaInspector` 计算每道题需要的完整解法数量
5. `GlobalTaskManager` 汇总上游题目和当前文件状态，生成全局任务队列
6. `FragmentTaskExecutor` 逐个执行任务
7. 若任务需要新建候选，则 `CoTGenerator` 生成并立即落盘
8. `AnswerMatcher` 处理尚未完成答案检查的文件
9. `DuplicateMethodChecker` 处理尚未完成判重的文件
10. `GeminiDetailChecker` 处理尚未完成细查的文件
11. 每一步一旦更新文件，都立即写盘
12. 若某文件在某一步被淘汰，则立即删除
13. 程序结束时，不再执行“合并主包”步骤

## 13. 当前版本暂不展开的内容

以下部分故意留待后续讨论：

- OpenAI API 的具体客户端写法
- Gemini API 的具体客户端写法
- 线程池大小
- `AnswerMatcher` 的精确匹配规则
- `DuplicateMethodChecker` 的具体判重策略
- `GeminiDetailChecker` 的具体 prompt
- 是否保留原始生成版 CoT 作为额外审计字段
- 多解目标数量的最终配置规则

## 14. 当前版本说明

这份 spec 已经切换成你当前想要的结构：

- `cot` 是字符串，不是列表
- 第二层只维护单文件粒度的 CoT 结果
- 不再生成第二层主包
- 失败或重复候选直接删除
- 由全局任务管理器负责发现未完成任务
- 下一层直接读取完整 CoT 文件
