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

这一版有六个关键约束：

1. `cot` 是单个字符串字段，不再使用列表式 `cot_steps`
2. `layer_cot/aaa/` 目录下直接存放 CoT 文件，不再使用 `CoT_fragments/` 子目录
3. 第二层不再生成 `layer_cot/aaa/aaa.json` 这种汇总主包
4. 三个串行工序的状态标志统一采用 `null / false / true`
5. 初始化扫描器只允许读和分类，不允许把未完成文件直接改判为失败
6. 删除动作只允许发生在某个具体工序完成对该文件的处理之后

这里提前明确一句：

- `cleanup_pending` 不是文件里的正式业务状态，也不是扫描器新判出来的失败
- 它只是启动扫描时对“上次已经写出终止结果、但删除动作没来得及完成的残留文件”的临时分类标签

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
- 若候选被判定失败或重复，则最终应删除对应文件

删除纪律必须单独强调：

- 初始化扫描、分类、配额计算都属于只读流程
- 只读流程不得修改已有 CoT 文件
- 只读流程不得把某个 `null` 状态直接改写成失败结果
- 只读流程不得直接执行删除
- 删除动作只允许由某个具体工序在“该工序已经完成对该文件的处理”之后执行
- 若程序中断导致某个终止文件尚未删掉，启动扫描时只能把它识别为 `cleanup_pending`，后续再交给执行器完成清理

### 2.3 关于 `cleanup_pending`

这一点单独写清楚：

- `cleanup_pending` 不是要写回 JSON 的字段
- `cleanup_pending` 不是第二层长期维护的一类结果
- `cleanup_pending` 只出现在“启动扫描后的内存分类结果”里

它的意图只有一个：

- 防止实现者把扫描器写成“看到异常状态就立即删文件”

正确理解应当是：

- 某个工序已经完成，并且已经把终止结果写进文件
- 但程序在删除动作发生前中断了
- 下次启动时，扫描器读到这个残留文件
- 扫描器只把它标记为 `cleanup_pending`
- 真正删除仍然由后续执行器完成

也就是说，`cleanup_pending` 的存在是为了把“扫描分类”和“执行删除”严格分开。

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

当前 spec 只约束 `cot` 是文本串，还没有确定它内部的具体格式。

因此当前版本不假设：

- 一定是“步骤列表”
- 一定按换行组织
- 一定有固定模板

这一点应留待后续单独确定。

### 5.2 三值状态原则

当前版本中，三个串行工序都使用三值状态：

- `null`
  表示该工序尚未执行完成
- `true` 或 `false`
  表示该工序已经执行完成

这里最重要的不是把 `true` 和 `false` 简单理解成“好”或“坏”，而是：

- `null` = 还没做完
- 非 `null` = 这个工序已经做完并得到了结果

这样做的价值是：

- 扫描器可以明确区分“未完成”和“已完成但结果不同”
- 恢复执行时可以准确知道下一步该接哪一道工序
- 不会把 `false` 和“还没做”混淆

四个核心标志位定义如下：

1. `answer_matches_standard`
   - `null`：尚未做答案检查
   - `true`：答案检查已完成，且答案匹配标准答案
   - `false`：答案检查已完成，但答案不匹配；该文件应进入终止删除路径

2. `is_duplicate_with_existing_complete_method`
   - `null`：尚未完成“是否与已有完整解法重复”的判定
   - `false`：该工序已完成，结果为“可继续”
   - `true`：该工序已完成，结果为“与已有完整解法重复”；该文件应进入终止删除路径

   这里的 `false` 有两种合法来源：

   - 当前题目不要求多解，因此本工序被跳过并直接记为“可继续”
   - 当前题目要求多解，且经 GPT 检查后确认“不重复”

3. `gemini_checked`
   - `null`：尚未完成 Gemini 细节检查
   - `true`：Gemini 细节检查已完成，且该文件通过
   - `false`：Gemini 细节检查已完成，但该文件不通过；该文件应进入终止删除路径

4. `is_complete_fragment`
   - `false`：当前还不是完整 CoT
   - `true`：当前已经是可直接下放到下一层的完整 CoT

补充说明：

- `is_complete_fragment = false` 本身绝不等于失败
- 扫描器不能因为某个文件 `is_complete_fragment = false` 就把它删掉
- 扫描器也不能因为某个工序标志是 `null` 就把它改判为失败

### 5.3 `CoTFragment`

当前版本要明确一个原则：

- 第二层输出文件相对于第一层 `ProblemPackage` 里的单题记录，是“增量式”的
- 也就是说，第二层不会只保留自己新增的字段
- 由于第一层最终字段集合还没有完全定稿，当前版本应尽量保留第一层已经给出的可用字段

因此，当前 CoT 文件里的字段可分成两类：

1. 保留字段
   来自第一层单题记录，当前原则上尽量保留

2. 增量字段
   由第二层新增，用于表达 CoT 内容、工序状态和方法编号

下面的示例只展示当前最关键的一批字段，不代表最终字段全集。

当前版本建议的文件结构为：

```json
{
  "file_id": "aaa",
  "problem_id": "prob_9b0a7ef70ee83d702776eea6",
  "question_text": "题目文本",
  "images": ["test/img1.png"],
  "source_meta": {},
  "multi_solution_hint": null,
  "ingest_status": "ready",
  "method_id": 1,
  "cot": "<model_generated_cot_text>",
  "generated_answer": "模型答案",
  "standard_answer": "标准答案",
  "answer_matches_standard": null,
  "is_duplicate_with_existing_complete_method": null,
  "gemini_checked": null,
  "is_complete_fragment": false
}
```

字段说明：

- 第一层保留字段
  当前版本原则上尽量保留，不在此处穷举冻结
- `cot`
  当前候选里的完整 CoT 文本
- `generated_answer`
  当前候选里的最终答案
- `standard_answer`
  从第一层继承的标准答案
- `answer_matches_standard`
  初始为 `null`
  答案检查通过后写为 `true`
  若检查失败，先写为 `false`，再进入删除流程
- `is_duplicate_with_existing_complete_method`
  初始为 `null`
  若当前题目不要求多解，则本工序直接写为 `false`
  若当前题目要求多解且经 GPT 判定不重复，则写为 `false`
  若判定重复，则先写为 `true`，再进入删除流程
- `gemini_checked`
  初始为 `null`
  Gemini 完成细节检查并通过后写为 `true`
  若 Gemini 完成细节检查但当前候选不通过，则先写为 `false`，再进入删除流程
- `is_complete_fragment`
  初始为 `false`
  只有当前面三个串行工序都已完成且结果允许继续时，才写为 `true`

### 5.4 删除规则与 `cleanup_pending`

当前版本不再把 `discard` 设计成一类需要长期保留的文件状态。

这里的“discard”在实现上解释为：

- 候选被判定为无效
- 文件应被删除
- 后续恢复与任务分配都不再把它当作正常候选继续推进

再次强调：

- `cleanup_pending` 不是一种新结果
- 它只是启动扫描阶段对“残留终止文件”的临时命名
- 它存在的唯一目的，是避免扫描器直接承担删除副作用

当前版本的终止条件有三种：

- `answer_matches_standard = false`
- `is_duplicate_with_existing_complete_method = true`
- `gemini_checked = false`

删除时机必须精确定义：

- 某个文件只有在对应工序已经完成并产出终止结果之后，才允许删除
- 推荐顺序是：先把终止结果写盘，再删除文件
- 如果程序恰好在“写盘之后、删除之前”中断，那么该文件会暂时残留在磁盘上
- 这种残留文件在下一次启动扫描时应被识别为 `cleanup_pending`
- `cleanup_pending` 不是“扫描器判失败”，而是“上一次某个工序已经给出了终止结果，但清理动作还没完成”

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

尤其是下面五点是对的：

- `cot` 统一成字符串后，下游结构更稳定
- 去掉第二层主包后，状态不再重复维护
- 让下一层直接读 CoT 文件，会比先合并再拆更简单
- 三值状态能明确区分“未完成”和“已完成后的结果”
- 扫描阶段保持只读，会显著降低误删风险

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
  - `cleanup_pending` 文件

当前建议分类规则：

- `is_complete_fragment = true`
  视为完整文件
- `answer_matches_standard = false`
  视为 `cleanup_pending`
- `is_duplicate_with_existing_complete_method = true`
  视为 `cleanup_pending`
- `gemini_checked = false`
  视为 `cleanup_pending`
- 其余现存文件
  视为未完成文件

必须强调：

- `CoTFragmentScanner` 是只读模块
- 它只负责分类，不负责修正状态，不负责删除文件
- 它不能把 `null` 推断成失败
- 它也不能把 `is_complete_fragment = false` 推断成失败
- 它对 `cleanup_pending` 的标记只存在于本次扫描结果中，不回写文件

### 7.3 `MethodQuotaInspector`

职责：

- 对当前题目做最小化的“是否进入多解模式”判断

当前版本当前只保留最小设计：

- 若 `multi_solution_hint` 为空或不要求多解，则按单解模式处理
- 若 `multi_solution_hint` 明确要求多解，则按多解模式处理

当前模块先只负责给出这个最小判断。

更细的内容暂不在这一版写死，例如：

- 多解模式下最终目标数量到底是多少
- 多解模式下停止条件如何配置
- 多解模式下是否还要引入别的策略信号

这些细节留待后续补充。

### 7.4 `GlobalTaskManager`

职责：

- 读取所有选中的工作单元
- 汇总上游题目列表
- 汇总当前层现存的 CoT 文件
- 结合单解/多解模式和当前文件状态，生成全局待执行任务队列

这里的“全局”指的是：

- 它看到的不是某一个单独题目
- 而是当前一次运行中所有工作单元、所有题目、所有现存 CoT 文件

它只负责判断“还有哪些任务没完成”，不负责亲自执行具体检查步骤。

当前版本建议输出三类任务：

1. `resume_fragment`
   继续处理一个已经存在但尚未完成的 CoT 文件

2. `create_new_fragment`
   为某道题新建一个新的候选 CoT 文件

3. `cleanup_fragment`
   清理由上一次终止工序遗留下来的 `cleanup_pending` 文件

当前版本建议的分配策略：

- 先把所有现存未完成文件加入任务队列
- 再把所有 `cleanup_pending` 文件加入清理任务队列
- 单解模式下，若当前没有完整文件且也没有未完成文件，则加入一个 `create_new_fragment` 任务
- 单解模式下，已有完整文件的题目不再分配新的候选任务
- 多解模式下，当前 spec 先只要求系统保留“继续分配新候选”和“继续执行判重”的能力
- 多解模式下具体何时停止、目标数量是多少，留待后续补充
- 同一题目在一次启动中，最多只新增一个新的候选文件

补充说明：

- `GlobalTaskManager` 不需要知道某个未完成文件具体卡在答案检查、判重还是 Gemini
- 它只需要知道“这个文件还没有完成”
- 真正恢复到哪一步，由后续执行器根据文件中的标志位自动判断
- `cleanup_fragment` 的来源只能是磁盘上已经存在终止结果的文件，而不是扫描器新推断出来的失败

### 7.5 `FragmentTaskExecutor`

职责：

- 接收 `GlobalTaskManager` 下发的单个任务
- 若任务类型是 `create_new_fragment`，先创建一个新的 CoT 文件
- 若任务类型是 `resume_fragment`，直接读取现存文件
- 若任务类型是 `cleanup_fragment`，只完成清理，不重新判定该文件成败
- 读取文件标志位，自动判断下一步该执行哪个工序
- 将文件一直推进到“完成”或“删除”为止

它是“导入工序后自动执行未完成部分”的具体承担者。

必须强调：

- `FragmentTaskExecutor` 在恢复时只能依据文件里已经存在的标志位继续推进
- 它不能把某个 `null` 状态直接改写成失败
- 删除动作必须建立在某个工序已经产生了终止结果的前提上

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
- 若不一致，则先把 `answer_matches_standard = false` 写回文件，再删除该文件

### 7.8 `DuplicateMethodChecker`

职责：

- 读取已经通过答案检查的候选文件
- 若当前题目不要求多解，则不调用 GPT，直接把 `is_duplicate_with_existing_complete_method = false` 写回文件
- 若当前题目要求多解，则只与现有完整文件比较
- 在要求多解的情况下，调用 GPT 判断该候选是否与现有完整解法重复
- 若不重复，则把 `is_duplicate_with_existing_complete_method = false` 写回文件
- 若重复，则先把 `is_duplicate_with_existing_complete_method = true` 写回文件，再删除该文件

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
- 若通过，则把 `gemini_checked = true` 写回文件
- 若通过，则再把 `is_complete_fragment = true` 写回文件
- 若不通过，则先把 `gemini_checked = false` 写回文件，再删除该文件

当前版本假定：

- Gemini 不只是返回一个“通过/不通过”标记
- 它应直接产出一版可落盘的新 CoT 文本

## 8. 单题内部的串行回路

对单个问题来说，处理顺序固定为：

1. 若没有可恢复文件且仍需新解法，则生成一个新的 CoT 文件
2. 若 `answer_matches_standard = null`，则运行 `AnswerMatcher`
3. 若 `answer_matches_standard = true` 且 `is_duplicate_with_existing_complete_method = null`，则进入“重复检查工序”
4. 若当前题目不要求多解，则该工序直接把 `is_duplicate_with_existing_complete_method = false`
5. 若当前题目要求多解，则调用 `DuplicateMethodChecker`
6. 若前两道工序都已完成且结果允许继续，且 `gemini_checked = null`，则运行 `GeminiDetailChecker`
7. 若 `gemini_checked = true` 且 `is_complete_fragment = true`，则该文件视为完整结果

对三个串行工序来说，统一判定原则是：

- `null` 表示该工序还没完成
- 非 `null` 表示该工序已经完成
- 之后是否继续，由该字段自己的语义决定

也就是说：

- `answer_matches_standard = false` 会终止并删除
- `is_duplicate_with_existing_complete_method = true` 会终止并删除
- `gemini_checked = false` 会终止并删除
- 其余已完成结果则允许流向下一工序

如果在中间任何一步程序断掉，下次启动时：

- `GlobalTaskManager` 会重新发现这个未完成文件
- 若某文件已记录终止结果但尚未删掉，则只把它放入 `cleanup_fragment`
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
- 若题目进入多解模式，则后续应允许继续生成多个完整解法

当前版本建议由 `MethodQuotaInspector` 先只做“是否进入多解模式”的最小判断，由 `GlobalTaskManager` 负责据此分配任务。

当前这一版先不把多解模式下的目标数量、停止规则和配置细节写死，留待后续补充。

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
2. 生成一段完整的 CoT 文本
3. 生成一个最终答案字符串

输出要求：
- 只能输出合法 JSON，不要输出任何额外解释
- 顶层只能有两个字段：`cot` 和 `generated_answer`
- `cot` 必须是单个字符串，不要输出字符串列表
- 当前 spec 只约束 `cot` 是文本串，不约束其内部具体格式
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
  "cot": "<model_generated_cot_text>",
  "generated_answer": "最终答案"
}
```

## 12. 当前版本的整体执行顺序

当前版本建议的整体执行顺序是：

1. 枚举 `layer_problem/` 下的目标工作单元
2. `ProblemPackageReader` 读取各工作单元的 `ProblemPackage`
3. `CoTFragmentScanner` 扫描 `layer_cot/<file_id>/` 下现存 CoT 文件
4. `MethodQuotaInspector` 判断每道题当前是单解模式还是多解模式
5. `GlobalTaskManager` 汇总上游题目和当前文件状态，生成全局任务队列
6. `FragmentTaskExecutor` 先处理 `cleanup_fragment`
7. `FragmentTaskExecutor` 再逐个执行恢复和新建任务
8. 若任务需要新建候选，则 `CoTGenerator` 生成并立即落盘
9. `AnswerMatcher` 处理尚未完成答案检查的文件
10. 若当前题目要求多解，则 `DuplicateMethodChecker` 处理尚未完成判重的文件
11. 若当前题目不要求多解，则直接把重复检查工序记为已完成且结果允许继续
12. `GeminiDetailChecker` 处理尚未完成细查的文件
13. 每一步一旦更新文件，都立即写盘
14. 若某文件在某一步被淘汰，则该工序先写终止结果，再删除文件
15. 程序结束时，不再执行“合并主包”步骤

## 13. 当前版本暂不展开的内容

以下部分故意留待后续讨论：

- OpenAI API 的具体客户端写法
- Gemini API 的具体客户端写法
- 线程池大小
- `AnswerMatcher` 的精确匹配规则
- `DuplicateMethodChecker` 调用 GPT 时的具体 prompt
- `GeminiDetailChecker` 的具体 prompt
- 是否保留原始生成版 CoT 作为额外审计字段
- 多解目标数量的最终配置规则

## 14. 当前版本说明

这份 spec 已经切换成你当前想要的结构：

- `cot` 是字符串，不是列表
- 第二层只维护单文件粒度的 CoT 结果
- CoT 内部具体格式暂未固定
- 三个串行工序统一使用三值状态
- 初始化扫描器保持只读
- 失败或重复候选只允许在对应工序完成后删除
- 由全局任务管理器负责发现未完成任务
- 下一层直接读取完整 CoT 文件
