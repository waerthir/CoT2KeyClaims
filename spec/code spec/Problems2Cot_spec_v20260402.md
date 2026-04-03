# Problems2Cot Spec

## 1. 目标

本 spec 描述当前版本 `Problems2Cot` 的具体设计。

这一版第二层不再只是“单次生成一个 CoT”，而是一个可恢复、可筛选、可控制解法数量的闭环系统。

当前版本的目标是：

- 读取第一层输出的 `ProblemPackage`
- 扫描当前工作单元已有的 CoT 碎片
- 对未完成步骤的碎片继续处理
- 若当前合格解法数量不足，则只新增一个新的候选 CoT 碎片
- 对新旧碎片按固定顺序做串行检查
- 只有通过全部检查的碎片，才视为完整解法
- 当完整解法数量满足要求时，汇总生成 `CoTPackage`

这个设计的核心意图是：

- 能够抗断网
- 能够抗中途中断
- 每次启动都能从已有碎片继续推进
- 可以控制“只要 1 个解法就停”或“要 3 个解法再停”

## 2. 当前版本的输入输出边界

### 2.1 输入

当前版本按“工作单元”处理输入。

建议与第一层保持一致：

- 默认遍历 `layer_problem/` 下的所有一级子目录
- 把每个工作单元目录都视为应处理对象
- 若未来配置中加入 `target_work_units`，则只处理指定工作单元
- 工作单元按名称排序后依次处理

单个工作单元的输入是：

- `layer_problem/aaa/aaa.json`

这个输入文件就是第一层输出的 `ProblemPackage`。

### 2.2 输出

当前版本会产生两类输出：

1. CoT 碎片

- `layer_cot/aaa/CoT_fragments/<problem_id>_<method_id>.json`

2. 第二层主包

- `layer_cot/aaa/aaa.json`

补充说明：

- 碎片一旦产生或被更新，就应立即写盘
- 主包只在整理器判断“当前完整解法数量已满足要求”时生成或更新

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

- 当前版本中，`method_id` 只保存在字段里作为数字
- 也就是说，`method_id` 是整数，不是字符串
- 示例：`1`、`2`、`3`

分配规则：

- 同一 `problem_id` 内部从 `1` 开始递增
- 一个新的候选碎片只在真正创建时才分配新的 `method_id`
- 已存在碎片的 `method_id` 一旦写入，就不再改动

### 3.4 碎片文件命名规则

虽然 `method_id` 字段本身是数字，但碎片文件名仍使用：

- `problem_id + "_" + method_id + ".json"`

示例：

- 若 `problem_id = prob_9b0a7ef70ee83d702776eea6`
- 且 `method_id = 1`
- 则碎片文件名为 `prob_9b0a7ef70ee83d702776eea6_1.json`

这样设计的原因是：

- 方便直接按题目和方法读取碎片
- 也方便启动时扫描现有碎片

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

## 5. CoT 碎片结构

### 5.1 当前版本的四个核心标志位

每个 CoT 碎片都必须额外带四个标志位：

1. `answer_matches_standard`
   表示该 CoT 给出的最终答案是否和标准答案一致

2. `gemini_checked`
   表示该碎片是否已经经过 Gemini 细节性检查

3. `is_duplicate_with_existing_complete_method`
   表示该碎片是否与现有“完整解法碎片”重复

4. `is_complete_fragment`
   表示该碎片是否已经成为一个最终可下放的完整方法

补充说明：

- 这里第三个标志位，当前在 spec 中严格定义为“是否与现有完整解法重复”
- 不是简单比较最终答案字符串是否相同
- 否则多解任务会永远无法成立

### 5.2 `CoTFragment`

当前版本建议的碎片结构为：

```json
{
  "file_id": "aaa",
  "problem_id": "prob_9b0a7ef70ee83d702776eea6",
  "method_id": 1,
  "cot_steps": [
    "步骤1",
    "步骤2",
    "步骤3"
  ],
  "generated_answer": "模型答案",
  "standard_answer": "标准答案",
  "answer_matches_standard": null,
  "gemini_checked": false,
  "is_duplicate_with_existing_complete_method": null,
  "is_complete_fragment": false
}
```

字段说明：

- `cot_steps`
  当前碎片里的 CoT 内容
- `generated_answer`
  当前碎片里的最终答案
- `standard_answer`
  从第一层继承的标准答案
- `answer_matches_standard`
  初始为 `null`
  答案检查完成后写为 `true` 或 `false`
- `gemini_checked`
  初始为 `false`
  Gemini 完成细节检查并输出新 CoT 后写为 `true`
- `is_duplicate_with_existing_complete_method`
  初始为 `null`
  重复解法检查后写为 `true` 或 `false`
- `is_complete_fragment`
  初始为 `false`
  只有当碎片通过全部流程后，才写为 `true`

### 5.3 关于 discard

当前版本不要求真的删除碎片文件。

这里的“discard”在实现上更适合解释为：

- 碎片被判定为终止状态
- 不再继续送往下一个检查器
- 但文件保留在磁盘上，方便断点恢复和问题排查

当前版本的终止条件有两种：

- `answer_matches_standard = false`
- `is_duplicate_with_existing_complete_method = true`

满足任一条件后，该碎片就视为已被 discard。

## 6. 第二层主包结构

### 6.1 `CoTPackage`

当前版本建议的主包结构为：

```json
{
  "file_id": "aaa",
  "stage": "problem_to_cot",
  "source_problem_file_id": "aaa",
  "problems": [
    {
      "problem_id": "prob_9b0a7ef70ee83d702776eea6",
      "question_text": "题目文本",
      "standard_answer": "标准答案",
      "images": ["test/img1.png"],
      "multi_solution_hint": null,
      "cot_methods": [
        {
          "method_id": 1,
          "cot_steps": ["步骤1", "步骤2"],
          "generated_answer": "答案A"
        }
      ]
    }
  ]
}
```

这里的 `cot_methods` 只收录：

- `is_complete_fragment = true` 的碎片

也就是说：

- 未完成碎片不进入主包
- 被 discard 的碎片也不进入主包

## 7. 模块设计

你的这套设计是合理的。

尤其是下面三点是非常对的：

- 每个检查步骤都要写回碎片，方便断网恢复
- 多线程只开在“多问题并行”，单题内部保持串行
- 每次启动只新增一个新候选碎片，更容易控制和回收

当前版本把它整理成九个模块。

### 7.1 `ProblemPackageReader`

职责：

- 读取 `layer_problem/aaa/aaa.json`
- 解析第一层输出的 `ProblemPackage`
- 提取当前工作单元的题目列表

边界：

- 只负责读取和解析
- 不负责检查碎片
- 不负责调用模型

### 7.2 `CoTFragmentScanner`

职责：

- 扫描 `layer_cot/aaa/CoT_fragments/`
- 读取当前工作单元已经存在的全部碎片
- 区分：
  - 完整碎片
  - 未完成碎片
  - 已被 discard 的终止碎片

当前建议分类规则：

- `is_complete_fragment = true`
  视为完整碎片
- `answer_matches_standard = false`
  视为已 discard
- `is_duplicate_with_existing_complete_method = true`
  视为已 discard
- 其余都视为未完成碎片

### 7.3 `MethodQuotaInspector`

职责：

- 判断当前每道题理论上需要几个完整解法

设计意图：

- 这就是你提到的“检查完整碎片个数是否和是否多解指示对上”的机器

当前版本建议最小规则：

- 若 `multi_solution_hint` 为空或不要求多解，则目标完整碎片数为 `1`
- 若 `multi_solution_hint` 明确要求多解，则目标完整碎片数由配置决定
- 当前常见的目标值可以是 `3`

补充说明：

- 当前版本只把这件事写进 spec
- 具体到底用 `1`、`2` 还是 `3`，以后可以继续细化

### 7.4 `TaskDispatcher`

职责：

- 读取题目列表
- 读取碎片扫描结果
- 读取目标解法数量
- 决定每个问题下一步该做什么

当前版本的关键策略：

- 多线程只用于“多个问题同时处理”
- 单个问题内部始终是串行处理
- 每次程序启动时，对每个题目最多只新增一个新的候选碎片

也就是说：

- 如果某题已经有未完成碎片，就优先继续推进它
- 如果某题没有未完成碎片，但完整碎片数还没达到要求，就新增一个新碎片
- 如果某题完整碎片数已经达到要求，就不再继续生成

### 7.5 `CoTGenerator`

职责：

- 接收单个题目任务
- 调用 OpenAI 接口
- 生成一个新的原始 CoT 候选

这里用 `CoTGenerator` 取代旧的 `OpenAIResponder` 命名。

当前版本建议输入：

- `file_id`
- `problem_id`
- `method_id`
- `question_text`
- `standard_answer`
- `images`
- `multi_solution_hint`

当前版本建议输出：

- `cot_steps`
- `generated_answer`

生成完成后，立即保存为一个新的原始碎片。

也就是说，生成器只负责产生“第一个版本”的 CoT。

### 7.6 `AnswerMatcher`

职责：

- 读取原始碎片
- 检查 `generated_answer` 是否和 `standard_answer` 一致
- 把检查结果写回 `answer_matches_standard`
- 然后立即保存碎片

规则：

- 若匹配失败，则该碎片直接进入 discard 终止状态
- 若匹配成功，则允许继续送到下一个检查器

### 7.7 `DuplicateMethodChecker`

职责：

- 读取已经通过答案检查的碎片
- 只与现有“完整碎片”比较
- 判断该碎片是否与现有完整解法重复
- 把结果写回 `is_duplicate_with_existing_complete_method`
- 然后立即保存碎片

规则：

- 若判定为重复，则该碎片直接进入 discard 终止状态
- 若不重复，则允许继续送到下一个检查器

补充说明：

- 这里检查的是“解法是否重复”
- 不是只看最终答案字符串
- 因为所有正确解法的最终答案本来就应该一致

### 7.8 `GeminiDetailChecker`

职责：

- 读取已经通过前两关的碎片
- 调用 Gemini 3 Flash 做细节性检查
- Gemini 必须输出一个新的 CoT
- 用新的 CoT 覆盖或更新碎片中的 `cot_steps`
- 必要时也可更新 `generated_answer`
- 把 `gemini_checked = true` 写回碎片
- 再把 `is_complete_fragment = true` 写回碎片
- 然后立即保存碎片

当前版本假定：

- Gemini 细节性检查不会只返回一个通过/不通过标记
- 它应直接输出一版新的 CoT

### 7.9 `CoTPackageOrganizer`

职责：

- 在程序启动时或程序结束时尝试执行
- 读取当前工作单元的全部碎片
- 检查每道题的完整碎片数是否满足要求
- 若满足，则整理生成最终 `CoTPackage`

当前版本的触发时机建议：

- 程序启动时先执行一次
  用于处理“上一次其实已经完成，只是还没整理”的情况
- 程序结束后再执行一次
  用于处理“本次运行刚刚完成收集”的情况

## 8. 单题内部的串行回路

这部分是当前版本最关键的闭环设计。

对单个问题来说，处理顺序固定为：

1. 若没有碎片，生成一个新的原始碎片
2. 若该碎片还没做答案检查，则运行 `AnswerMatcher`
3. 若答案检查通过，且还没做重复解法检查，则运行 `DuplicateMethodChecker`
4. 若重复检查通过，且还没做 Gemini 细节检查，则运行 `GeminiDetailChecker`
5. 若 Gemini 已完成，则把该碎片视为完整碎片

如果在中间任何一步程序断掉，下次启动时：

- 先扫描磁盘上的碎片
- 再根据四个标志位判断这个碎片停在了哪一步
- 然后从未完成的那一步继续执行

这就是当前版本抗断网、抗中断的核心设计。

## 9. 多线程策略

当前版本明确规定：

- 多线程只用于“多问题并行”
- 单个问题内部不允许并行跑多个检查步骤
- 单个问题内部始终是串行链路

这样做的原因是：

- 简化恢复逻辑
- 简化 `method_id` 分配
- 避免一个问题内部多个候选同时竞争状态

## 10. 多解控制策略

当前版本支持可控地停止。

设计原则是：

- 若目标只要一个完整解法，那么收集到一个完整碎片就可以停
- 若目标要三个完整解法，那么必须收集到三个完整碎片才停

当前版本建议由 `MethodQuotaInspector` 决定目标解法数量。

并且当前版本有一个重要限制：

- 每次程序启动时，对每个题目最多只新增一个新的候选碎片

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
2. 生成一条简洁、必要、按顺序展开的步骤化推理
3. 生成一个最终答案字符串

输出要求：
- 只能输出合法 JSON，不要输出任何额外解释
- 顶层只能有两个字段：`cot_steps` 和 `generated_answer`
- `cot_steps` 必须是有序的字符串列表
- `generated_answer` 必须是单个字符串
- 推理步骤要围绕解题所必需的信息展开
- 不要输出空话，不要输出与解题无关的说明
- 不要输出 markdown 代码块，不要输出前后缀说明
- 不要把“根据标准答案可知”这类话直接写进推理
- 如果图片路径存在，应将其视为题目可用信息，但不要在输出中重复罗列路径本身
- `generated_answer` 应尽量与 `standard_answer` 保持同样或极接近的表述
```

当前版本建议 `CoTGenerator` 要求模型输出：

```json
{
  "cot_steps": ["步骤1", "步骤2", "步骤3"],
  "generated_answer": "最终答案"
}
```

## 12. 当前版本的整体执行顺序

当前版本建议的整体执行顺序是：

1. `ProblemPackageReader` 读取 `layer_problem/aaa/aaa.json`
2. `CoTPackageOrganizer` 在任务开始时先尝试整理一次
3. `CoTFragmentScanner` 扫描当前已有碎片
4. `MethodQuotaInspector` 计算每道题当前需要几个完整解法
5. `TaskDispatcher` 找出每道题下一步要做什么
6. 若某题需要新增候选，则 `CoTGenerator` 生成一个新的原始碎片并立即保存
7. `AnswerMatcher` 处理尚未做答案检查的碎片
8. `DuplicateMethodChecker` 处理已通过答案检查、但尚未做重复性检查的碎片
9. `GeminiDetailChecker` 处理已通过前两关、但尚未做 Gemini 细查的碎片
10. 每一步检查后都立即写回碎片文件
11. 全部任务结束后，`CoTPackageOrganizer` 再次检查碎片是否齐全
12. 若齐全，则生成最终的 `CoTPackage`

## 13. 当前版本暂不展开的内容

以下部分故意留待后续讨论：

- OpenAI API 的具体客户端写法
- Gemini API 的具体客户端写法
- 线程池大小
- `AnswerMatcher` 的精确匹配规则
- `DuplicateMethodChecker` 的具体判重策略
- `GeminiDetailChecker` 的具体 prompt
- 是否保留原始生成版 CoT 作为审计字段
- 多解目标数量的最终配置规则

## 14. 当前版本说明

这份 spec 已经切换成你当前想要的“生成 -> 检查 -> 再继续”的闭环架构。

它的关键特征是：

- 每个问题内部串行推进
- 每一步都写碎片
- 程序随时中断也能恢复
- 每次启动只新增一个新候选
- 最后只把完整解法下放到下一层
