# Problems2Cot Spec

## 1. 目标

本 spec 描述当前版本 `Problems2Cot` 的具体设计。

当前版本的目标是：

- 读取第一层输出的 `ProblemPackage`
- 检查已有 CoT 碎片
- 只对尚未完成的题目发起生成任务
- 使用 OpenAI 接口逐题生成 CoT 与答案
- 每生成一个结果就立即保存为碎片
- 在任务开始时或任务结束后尝试整理全部碎片
- 当碎片齐全时，汇总生成 `CoTPackage`

当前版本不包含独立的 Gemini 校验模块。

也就是说，这一版的重点是：

- 先把第二层“生成 + 碎片保存 + 最终打包”的基础流水线搭起来
- 验证和更复杂的状态机以后再补

## 2. 当前版本的输入输出边界

### 2.1 输入

当前版本按“工作单元”处理输入。

工作单元发现规则建议与第一层保持一致：

- 默认遍历 `layer_problem/` 下的所有一级子目录
- 把每个工作单元目录都视为应处理对象
- 若未来配置中加入 `target_work_units`，则只处理指定工作单元
- 工作单元按名称排序后依次处理

单个工作单元的输入是：

- `layer_problem/aaa/aaa.json`

这个输入文件就是第一层已经整理好的 `ProblemPackage`。

当前第二层只读取第一层标准化后的主包，不再直接读取原始脏数据。

### 2.2 输出

当前版本会产生两类输出：

1. CoT 碎片

- `layer_cot/aaa/CoT_fragments/<method_id>.json`

2. 第二层主包

- `layer_cot/aaa/aaa.json`

补充说明：

- 第二层的输出目录不存在时，后续代码应自动创建
- 每个碎片应在生成成功后立即写盘
- 主包不要求每次都重写，只有在整理器判断碎片齐全时才生成或更新

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

- `method_id` 是字符串字段
- `method_id = problem_id + "_" + 序数id`
- 序数 id 使用整数
- 一旦写入碎片文件，不再改动

当前版本的最小实现假定：

- 每道题默认只生成一个方法
- 因此当前默认方法编号可直接使用 `1`
- 也就是默认 `method_id = problem_id + "_1"`

示例：

- 若 `problem_id = prob_9b0a7ef70ee83d702776eea6`
- 则当前默认 `method_id = prob_9b0a7ef70ee83d702776eea6_1`

补充说明：

- 这只是当前版本的最小实现
- 未来如果扩展为多解法生成，则继续沿用 `_2`、`_3` ... 递增

### 3.4 碎片命名规则

第二层不为碎片额外生成独立 id。

碎片文件名固定为：

- `method_id + ".json"`

示例：

- 若 `method_id = prob_9b0a7ef70ee83d702776eea6_1`
- 则碎片文件名为 `prob_9b0a7ef70ee83d702776eea6_1.json`

## 4. 输入对象格式

### 4.1 第二层读取的 `ProblemPackage`

当前第二层直接读取第一层输出的主包。

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

## 5. 输出对象格式

### 5.1 `CoTFragment`

当前版本建议的碎片结构为：

```json
{
  "file_id": "aaa",
  "problem_id": "prob_9b0a7ef70ee83d702776eea6",
  "method_id": "prob_9b0a7ef70ee83d702776eea6_1",
  "cot_steps": [
    "步骤1",
    "步骤2",
    "步骤3"
  ],
  "generated_answer": "模型答案",
  "standard_answer": "标准答案",
  "answer_match_status": "matched",
  "validation_status": "not_checked",
  "ready_for_packaging": true
}
```

字段说明：

- `cot_steps`：回答器生成的步骤化推理
- `generated_answer`：回答器生成的最终答案
- `standard_answer`：从第一层继承的标准答案
- `answer_match_status`：当前版本可先做简单字符串归一化比较，写成 `matched` 或 `unmatched`
- `validation_status`：当前版本没有独立校验器，因此先固定写为 `not_checked`
- `ready_for_packaging`：只要该碎片结构完整并成功写盘，就可写为 `true`

### 5.2 `CoTPackage`

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
          "method_id": "prob_9b0a7ef70ee83d702776eea6_1",
          "cot_steps": ["步骤1", "步骤2"],
          "generated_answer": "答案A",
          "answer_match_status": "matched",
          "validation_status": "not_checked"
        }
      ]
    }
  ]
}
```

补充说明：

- 主包里的内容来自碎片整理，而不是模型直接一次性输出
- 第二层主包是第三层的标准输入

## 6. 模块设计

你的这套设计是合理的，尤其适合第二层这种“可中断、可恢复、先碎片后汇总”的任务。

当前版本将其整理为六个模块。

### 6.1 `ProblemPackageReader`

职责：

- 读取 `layer_problem/aaa/aaa.json`
- 解析第一层输出的 `ProblemPackage`
- 提取本层需要处理的题目列表

边界：

- 只负责读取和解析
- 不负责判断碎片缺失
- 不负责调用模型

当前建议输出：

- `file_id`
- 当前工作单元中的全部题目对象列表

### 6.2 `CoTFragmentChecker`

职责：

- 检查 `layer_cot/aaa/CoT_fragments/` 下已经存在多少碎片
- 判断哪些题目已经完成，哪些题目还没有完成

当前版本建议的最小检查逻辑：

- 当前默认每道题只期望一个 `method_id`
- 即默认检查 `<problem_id>_1.json` 是否存在
- 若存在且结构完整，则视为该题已完成
- 若不存在，或结构不完整，则视为该题仍待生成

边界：

- 只负责“盘点现有碎片”
- 不直接调用模型
- 不直接写碎片

### 6.3 `TaskDispatcher`

职责：

- 根据读取器和碎片检查器的结果
- 收集尚未完成的题目
- 把这些任务分发给回答器

当前版本建议使用多线程。

设计意图：

- 一个线程负责一个待回答题目
- 每个线程把单题任务送给 `OpenAIResponder`
- 拿到结果后，立即交给碎片存储器写盘

边界：

- 负责调度，不负责真正生成答案
- 不直接拼主包

### 6.4 `OpenAIResponder`

职责：

- 接收单个题目
- 调用 OpenAI 接口
- 让模型输出该题的一条 CoT 与最终答案

当前版本建议输入字段：

- `file_id`
- `problem_id`
- `question_text`
- `standard_answer`
- `images`
- `multi_solution_hint`
- `method_id`

当前版本建议输出字段：

- `cot_steps`
- `generated_answer`

边界：

- 一次只处理一个题目任务
- 不直接写文件
- 不直接打包主包

### 6.5 `CoTFragmentWriter`

职责：

- 接收回答器输出的单题结果
- 与原始题目信息合并
- 保存为单个 `CoTFragment`

当前版本建议额外负责：

- 补齐 `file_id`
- 补齐 `problem_id`
- 补齐 `method_id`
- 补齐 `standard_answer`
- 计算当前版本的 `answer_match_status`
- 写入 `validation_status = "not_checked"`
- 写入 `ready_for_packaging = true`

边界：

- 每次只写一个碎片
- 一写成功就落盘
- 不负责全局整理

### 6.6 `CoTPackageOrganizer`

职责：

- 在任务开始时或任务结束后尝试执行
- 扫描当前工作单元的全部碎片
- 判断碎片是否齐全
- 若齐全，则整理为最终的 `CoTPackage`

当前版本建议的触发时机：

- 程序启动时先执行一次
  用于处理“碎片本来就已经齐全”的情况
- 程序结束后再执行一次
  用于处理“本次运行刚刚把碎片补齐”的情况

当前版本建议的整理规则：

- 若某道题当前期望的碎片不存在，则主包不生成
- 只有当全部题目的期望碎片都齐全时，才生成 `layer_cot/aaa/aaa.json`

边界：

- 只负责汇总
- 不负责生成新碎片

## 7. 当前版本的简单系统提示词

下面是一个可以直接作为起点的简单 `system prompt` 草稿。

```text
你现在负责为单个题目生成一条结构化的解题结果。

你会收到以下信息：
1. `question_text`：题目文本
2. `standard_answer`：标准答案
3. `images`：题目相关图片的相对路径列表
4. `multi_solution_hint`：是否多解的预留字段，当前通常为 null

你的任务是：
1. 阅读题目文本、标准答案和图片路径信息
2. 生成一条简洁、必要、按顺序展开的步骤化推理
3. 生成一个最终答案字符串

输出要求：
- 只能输出合法 JSON，不要输出任何额外解释
- 顶层只能有两个字段：`cot_steps` 和 `generated_answer`
- `cot_steps` 必须是有序的字符串列表
- `generated_answer` 必须是单个字符串
- 推理步骤要围绕解题所必需的信息展开，不要写空话，不要写与解题无关的说明
- 不要输出 markdown 代码块，不要输出前后缀说明
- 不要把“根据标准答案可知”这类话直接写进推理
- 如果图片路径存在，应将其视为题目可用信息，但不要在输出中重复罗列路径本身
- `generated_answer` 应尽量与 `standard_answer` 保持同样或极接近的表述，以减少后续匹配误差
- `cot_steps` 的语言风格应简洁直接，适合后续保存为结构化碎片
```

当前版本建议回答器要求模型输出：

```json
{
  "cot_steps": ["步骤1", "步骤2", "步骤3"],
  "generated_answer": "最终答案"
}
```

## 8. 当前版本的处理流程

当前版本建议的整体执行顺序是：

1. `ProblemPackageReader` 读取 `layer_problem/aaa/aaa.json`
2. `CoTPackageOrganizer` 在任务开始时先尝试整理一次
3. `CoTFragmentChecker` 统计当前已有碎片
4. `TaskDispatcher` 找出尚未完成的题目任务
5. `TaskDispatcher` 采用多线程把这些任务发送给 `OpenAIResponder`
6. `OpenAIResponder` 逐题生成 `cot_steps` 和 `generated_answer`
7. `CoTFragmentWriter` 把每个结果立即保存为单个 `CoTFragment`
8. 全部任务完成后，`CoTPackageOrganizer` 再次检查碎片是否齐全
9. 若齐全，则生成最终的 `CoTPackage`

## 9. 当前版本暂不展开的内容

以下部分故意留待后续讨论：

- OpenAI API 的具体客户端写法
- 线程池大小
- 是否加入重试机制
- `answer_match_status` 的精确归一化规则
- 未来是否重新引入独立校验器
- 多解法生成时如何分配 `_2`、`_3` 等 `method_id`
- 回答器的 user prompt 具体模板

## 10. 当前版本的说明

这份 spec 现在已经不再是旧版的 “GPT + Gemini” 双模块结构。

它已经切换成你当前想要的施工思路：

- 读取器
- 碎片检查器
- 发送器
- 回答器
- 碎片存储器
- 整理器

同时，它的输入输出格式也已经同步到当前第一层和最外层 spec 的版本：

- `problem_id` 使用当前第一层格式
- `images` 使用相对工作单元根目录的路径，例如 `test/img1.png`
- 第二层主包与碎片都按当前最外层 spec 对齐
