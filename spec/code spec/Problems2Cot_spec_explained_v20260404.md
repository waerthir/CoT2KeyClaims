# Problems2Cot 代码解释说明

## 1. 文档定位

这份说明是 [Problems2Cot_spec_v20260402.md](./Problems2Cot_spec_v20260402.md) 的配套阅读文档，目标不是重新定义设计，而是解释当前 `problems2cot.py` 里每个类、每个函数分别负责什么，以及它们是怎样串起来的。

建议把这份文档和代码一起看。阅读顺序可以按下面六层来理解:

1. 配置与基础校验
2. 数据结构
3. 模型接口
4. 读取、扫描、任务规划
5. 生成步骤与三道检查工序
6. 执行器与总流水线

这里先和设计口径对齐一次:

- `CoTGenerator` 负责“生成 CoT 碎片”
- 生成完成之后，才进入“生成后的三道检查工序”
- 这三道检查工序固定是 `AnswerMatcher`、`DuplicateMethodChecker`、`GeminiDetailChecker`
- 所以“三道工序”不包含 CoT 生成本身；生成是前置步骤

## 2. 配置层与基础校验函数

### `Problems2CotConfig`

- 作用: 集中保存第二层的路径配置、字段名配置、JSON 序列化配置、三值状态相关字段，以及多解判断的基础参数。
- `input_root`: 第二层输入目录，指向 `layer_problem/`
- `output_root`: 第二层输出目录，指向 `layer_CoT/`
- `image_root`: 图片根目录，固定指向 `layer_input/`
- `problem_list_field` 等字段: 用来屏蔽 JSON 字段名，避免实现里写死字符串
- `multi_solution_false_values`: 用来把 `"false"`, `"single"` 之类的值归类为“不是多解”
- `cot_generation_backend` / `duplicate_check_backend` / `gemini_review_backend`: 三个默认模型后端的配置入口
- `cot_generation_system_prompt` / `duplicate_check_system_prompt` / `gemini_review_system_prompt`: 三个模型后端使用的系统提示词
- 这个类没有成员函数。它的职责是“提供统一配置”，而不是执行业务逻辑。

### `OpenAICompatibleBackendConfig`

- 作用: 表示一个 OpenAI-compatible 后端的最小配置对象
- `name`: 后端名称，只用于报错和日志定位
- `base_url`: OpenAI-compatible 接口根地址
- `api_key`: API key。仓库里默认写的是假的占位值，真正使用前需要替换
- `model`: 模型名
- `timeout_seconds`: 单次请求超时
- `temperature`: 采样温度
- `max_tokens`: 单次返回的最大 token 数

### `_require_object(value, label)`

- 作用: 断言 `value` 必须是 `dict`
- 使用位置: 读取 ProblemPackage、读取 fragment、读取单题记录时
- 设计意图: 把 JSON 结构错误尽量提前暴露

### `_require_str(value, label)`

- 作用: 断言 `value` 必须是字符串
- 使用位置: `problem_id`、`question_text`、`standard_answer`、`cot`、`generated_answer` 等字段

### `_require_int(value, label)`

- 作用: 断言 `value` 必须是整数，并且显式排除 `bool`
- 使用位置: `method_id`
- 设计意图: 避免把 `True` / `False` 当成 `1` / `0`

### `_require_bool(value, label)`

- 作用: 断言 `value` 必须是布尔值
- 使用位置: 解析 duplicate backend 和 gemini backend 的 JSON 结果

### `_require_string_list(value, label)`

- 作用: 断言 `value` 必须是“由字符串组成的列表”
- 使用位置: `images`

## 3. 数据结构类

### `WorkUnit`

- 作用: 表示一个项目级输入单元，也就是一个 `file_id`
- `file_id`: 当前项目名
- `input_dir`: `layer_problem/<file_id>/`
- `input_file`: `layer_problem/<file_id>/<file_id>.json`
- `image_root`: `layer_input/<file_id>/`
- `output_dir`: `layer_CoT/<file_id>/`

### `ProblemContext`

- 作用: 把单题原始记录和运行期上下文封装在一起，让后续模块只面对“题目对象”，而不需要反复关心 package 结构。
- `file_id(self)`: 从所属 `WorkUnit` 返回当前 `file_id`
- `image_root(self)`: 返回该题对应的图片根目录 `layer_input/<file_id>/`
- `problem_id(self)`: 从原始题目记录中读取 `problem_id`
- `question_text(self)`: 读取题面文本
- `standard_answer(self)`: 读取标准答案
- `images(self)`: 读取图片相对路径列表
- `multi_solution_hint(self)`: 读取多解提示原值，不在这里做业务判断

### `GeneratedCoT`

- 作用: 表示 CoT 生成器的直接输出
- `cot`: 当前版本中只是一个文本串，不预设内部结构
- `generated_answer`: 生成出来的答案文本

### `GeminiReviewResult`

- 作用: 表示 Gemini 细查的返回结果
- `passed`: 是否通过细查
- `cot`: 可选。如果 Gemini 通过后给出了修订版 CoT，就写在这里
- `generated_answer`: 可选。如果 Gemini 通过后给出了修订版答案，就写在这里

### `FragmentSnapshot`

- 作用: 把 fragment 的磁盘路径和其 JSON payload 封装在一起
- `problem_id(self)`: 从 fragment payload 中读取 `problem_id`
- `method_id(self)`: 从 fragment payload 中读取 `method_id`

### `ProblemFragmentGroup`

- 作用: 表示某一道题当前已有的全部碎片，并按状态分组
- `complete_fragments`: 已完成碎片
- `pending_fragments`: 尚未完成、后续要继续跑的碎片
- `cleanup_pending_fragments`: 已经写出终止结果，但文件还残留在磁盘上的碎片

### `WorkUnitScanResult`

- 作用: 保存一次项目扫描的结果
- `work_unit`: 对应项目
- `fragments_by_problem`: `problem_id -> ProblemFragmentGroup`

### `FragmentTask`

- 作用: 表示任务管理器下发的一个具体任务
- `action`: 当前支持 `cleanup_fragment`、`resume_fragment`、`create_new_fragment`
- `work_unit`: 任务属于哪个项目
- `problem_context`: 对应哪道题。只有工作任务需要
- `fragment_path`: 对应哪个碎片文件。清理任务和续跑任务需要

### `TaskPlan`

- 作用: 表示一次全局规划后的任务清单
- `cleanup_tasks`: 先执行的清理任务
- `work_tasks`: 后执行的工作任务

### `Problems2CotReport`

- 作用: 保存本轮运行的统计结果
- `work_units_processed`: 本轮处理了多少个项目
- `fragments_created`: 新建了多少个碎片
- `fragments_completed`: 完成了多少个碎片
- `fragments_cleaned`: 删除了多少个碎片

### `WorkUnitRuntimeState`

- 作用: 把某个项目在“任务规划前”需要的全部上下文捆在一起
- `work_unit`: 当前项目
- `package`: 当前项目的 ProblemPackage
- `problem_contexts`: 当前项目所有题目的 `ProblemContext`
- `scan_result`: 当前项目已有 fragment 的扫描结果

## 4. 模型接口与占位后端

### `CoTGenerationBackend`

- 作用: CoT 生成接口协议
- `generate(...)`: 输入题面、标准答案、图片路径、`method_id`、多解提示等信息，返回 `GeneratedCoT`

### `DuplicateCheckBackend`

- 作用: 多解判重接口协议
- `is_duplicate(...)`: 输入候选碎片和已有完整碎片，判断是否重复

### `GeminiReviewBackend`

- 作用: Gemini 细查接口协议
- `review(...)`: 输入当前 fragment 和图片信息，返回 `GeminiReviewResult`

### `DisabledCoTGenerationBackend`

- 作用: 没有注入真实生成后端时的占位实现
- `generate(...)`: 直接报错，防止测试或本地运行时误调 API

### `DisabledDuplicateCheckBackend`

- 作用: 没有注入真实判重后端时的占位实现
- `is_duplicate(...)`: 直接报错

### `DisabledGeminiReviewBackend`

- 作用: 没有注入真实 Gemini 后端时的占位实现
- `review(...)`: 直接报错

这一层还要明确一件事:

- 当前代码已经有真实的后端实现，但实现方式不是直接依赖第三方 SDK，而是通过标准库发起 OpenAI-compatible HTTP 请求
- 真正的“调用模型”位置，仍然被抽象成下面三个后端接口方法:
  - `CoTGenerationBackend.generate(...)`
  - `DuplicateCheckBackend.is_duplicate(...)`
  - `GeminiReviewBackend.review(...)`
- 默认情况下，流水线会根据 `Problems2CotConfig` 里的 backend 配置自动创建真实后端
- `Disabled...Backend` 仍然保留，作用是给测试或显式禁用场景使用
- 默认配置里的 API key 是假的占位值；如果不先替换，后端会在发请求前直接报错
- 当前实现没有重试逻辑，每个请求只尝试一次

### `JsonHttpTransport`

- 作用: HTTP JSON 传输协议
- `post_json(...)`: 定义“向某个 URL 发送 JSON 并返回 JSON”的最小接口，方便后端测试时注入假 transport

### `UrllibJsonHttpTransport`

- 作用: `JsonHttpTransport` 的默认实现
- `post_json(...)`: 使用 Python 标准库 `urllib.request` 发起 POST 请求；负责基础的 HTTP 错误处理和 JSON 解析

### `OpenAICompatibleChatClient`

- 作用: 把 OpenAI-compatible `/chat/completions` 调用封装成统一客户端，供三个后端复用
- `__init__(config, transport)`: 注入后端配置和可替换 transport
- `create_json_response(system_prompt, user_prompt, image_paths)`: 组装消息、附带图片、发请求、抽取模型文本，再从文本里解析 JSON 对象
- `_validate_api_key()`: 检查 API key 是否为空或仍然是假 key
- `_build_request_url()`: 统一拼接 `/chat/completions`
- `_build_user_content(...)`: 构造 OpenAI-compatible 多模态 `content` 列表
- `_read_image_as_data_url(path)`: 读取本地图片并转成 data URL，写入 `image_url`
- `_extract_message_text(response)`: 从返回的 `choices[0].message.content` 中抽出文本
- `_parse_json_object(text)`: 从模型文本中提取第一个 JSON 对象

### `OpenAICompatibleCoTGenerationBackend`

- 作用: `CoTGenerationBackend` 的真实默认实现
- `__init__(config, client)`: 读取 `config.cot_generation_backend`，必要时创建默认 client
- `generate(...)`: 根据题目和图片构造请求，调用 GPT 类模型，要求输出 `{"cot": ..., "generated_answer": ...}`

### `OpenAICompatibleDuplicateCheckBackend`

- 作用: `DuplicateCheckBackend` 的真实默认实现
- `__init__(config, client)`: 读取 `config.duplicate_check_backend`
- `is_duplicate(...)`: 把候选 fragment 和已有完整 fragment 发给模型，要求输出 `{"is_duplicate": true/false, ...}`

### `OpenAICompatibleGeminiReviewBackend`

- 作用: `GeminiReviewBackend` 的真实默认实现
- `__init__(config, client)`: 读取 `config.gemini_review_backend`
- `review(...)`: 把 fragment 和图片发给 Gemini 的 OpenAI-compatible 接口，要求输出 `{"passed": ..., "cot": ..., "generated_answer": ...}`

## 5. 读取、定位、存储、扫描、任务规划

### `ProblemPackageReader`

- 作用: 第二层输入读取器。负责从 `layer_problem/` 读取 package，并转成内部使用的 `WorkUnit` 和 `ProblemContext`。
- `__init__(self, config)`: 保存配置
- `list_work_units(self)`: 列出当前所有待处理项目。如果配置了 `target_work_units`，则只读取指定项目
- `read(self, work_unit)`: 打开 `work_unit.input_file`，检查顶层结构和 `problems` 列表是否合法
- `build_problem_contexts(self, work_unit, package, quota_inspector)`: 遍历题目列表，为每一题构造 `ProblemContext`，并在这里写入 `multi_solution_mode`
- `_build_work_unit(self, work_unit_name)`: 构造 `WorkUnit`。这里会同时检查 `layer_problem/<file_id>/`、`<file_id>.json` 和 `layer_input/<file_id>/` 是否存在
- `_validate_problem_record(self, problem, work_unit, index)`: 校验单题最基础的字段完备性和字段类型

### `MethodQuotaInspector`

- 作用: 当前版本的“多解判断器”
- `__init__(self, config)`: 保存配置
- `is_multi_solution_mode(self, problem)`: 只判断当前题目是否进入多解模式，不负责决定生成几个解法，也不负责停止策略

### `ProblemImageLocator`

- 作用: 把题目里的相对图片路径翻译成磁盘绝对路径
- `resolve_paths(self, problem_context)`: 基于 `problem_context.image_root` 和 `problem_context.images` 计算完整路径列表
- 设计重点: 图片目录永远从 `layer_input/<file_id>/` 读，而不是从当前层的输出目录读

### `CoTFragmentStore`

- 作用: 统一处理 fragment 文件的路径生成、读写、删除
- `__init__(self, config)`: 保存配置
- `list_fragment_paths(self, output_dir)`: 列出当前项目输出目录下的全部 fragment 文件
- `read_fragment(self, path)`: 读取 fragment，并保证 `problem_id` 和 `method_id` 至少可用
- `write_fragment(self, path, payload)`: 按统一 JSON 配置写回 fragment
- `delete_fragment(self, path)`: 删除一个 fragment 文件
- `build_fragment_path(self, output_dir, problem_id, method_id)`: 按 `<problem_id>_<method_id>.json` 规则构造路径
- `next_method_id(self, output_dir, problem_id)`: 扫描当前题目已有碎片，分配下一个 `method_id`
- `build_initial_fragment_payload(self, problem_context, method_id, generated)`: 用第一层保留字段加上第二层增量字段，构造一个新的 fragment，并把三个工序的状态初始化为 `null`

### `CoTFragmentScanner`

- 作用: 启动时扫描现有 fragment，并把它们分成“完整”“未完成”“待清理”三类
- `__init__(self, config, store)`: 保存配置和存储器
- `scan(self, work_unit)`: 扫描某个项目目录，把所有 fragment 按 `problem_id` 归组，并在组内按 `method_id` 排序
- `_classify(self, payload)`: 根据三值状态和完成状态决定该 fragment 属于哪一类

这里必须强调当前实现的边界:

- 扫描器只能分类，不能删文件
- `cleanup_pending` 只是内存中的临时分类，不是要写回 JSON 的新字段
- 只有在单个工序已经写出了终止结果之后，后续执行阶段才允许删除对应文件

### `GlobalTaskManager`

- 作用: 全局任务管理器。它把“上一层输入包”和“当前层已有碎片状态”一起转成真正要执行的任务
- `build_plan(self, states)`: 先收集 `cleanup_tasks`，再收集 `work_tasks`
- `_task_sort_key(self, task)`: 让任务顺序稳定，便于复现和调试

`build_plan()` 的核心逻辑可以这样理解:

- 对所有 `cleanup_pending_fragments`，分配 `cleanup_fragment`
- 对所有 `pending_fragments`，分配 `resume_fragment`
- 对单解题，如果既没有完整碎片，也没有待续跑碎片，则分配 `create_new_fragment`
- 对多解题，只要当前没有待续跑碎片，就允许继续分配新的 `create_new_fragment`

## 6. 生成步骤与三道检查工序

### `CoTGenerator`

- 作用: 生成步骤，负责生成新的 CoT fragment
- `__init__(self, config, store, image_locator, backend)`: 注入依赖
- `create(self, problem_context, method_id)`: 先解析图片路径，再调用生成后端，随后把初始 fragment 写入磁盘并返回最新快照

这里要特别区分:

- `CoTGenerator` 属于“生成步骤”
- 它发生在三道检查工序之前
- 它不属于“生成后的三道检查工序”本身

### `AnswerMatcher`

- 作用: 第一检查工序，判断生成答案和标准答案是否一致
- `__init__(self, config, store)`: 注入依赖
- `process(self, fragment)`: 读取 `generated_answer` 与 `standard_answer`，做规范化比较。若不匹配，就先把 `answer_matches_standard = false` 写回，再删除 fragment
- `_normalize(self, text)`: 负责比较前的标准化。当前只处理空白相关问题

### `DuplicateMethodChecker`

- 作用: 第二检查工序，负责多解判重
- `__init__(self, config, store, backend)`: 注入依赖
- `process(self, fragment, existing_complete_fragments, multi_solution_mode)`: 单解模式下不调用后端，直接写 `false` 并继续；多解模式下调用后端判断是否与已有完整解法重复。如果重复，就先写 `true` 再删除 fragment

### `GeminiDetailChecker`

- 作用: 第三检查工序，负责最终图文细查
- `__init__(self, config, store, image_locator, backend)`: 注入依赖
- `process(self, fragment, problem_context)`: 调用 Gemini 后端检查当前 fragment。失败时先写 `gemini_checked = false` 再删除；通过时写入修订版 `cot`、可选修订版 `generated_answer`，并把 `is_complete_fragment = true`

## 7. 执行器与总流水线

### `FragmentTaskExecutor`

- 作用: 真正执行任务，并把“生成步骤 + 三道检查工序”按顺序串起来
- `__init__(...)`: 注入 store、scanner 和三个工序模块
- `execute_cleanup_task(self, task, report)`: 执行删除任务。这是当前实现里真正删除文件的统一入口
- `execute_work_task(self, task, report)`: 根据任务类型决定是创建新 fragment，还是续跑已有 fragment
- `_execute_create_task(self, problem_context, report)`: 先拿下一个 `method_id`，再创建 fragment，随后立即推进后续步骤
- `_advance_fragment(self, problem_context, fragment_path, report)`: 整个串行执行的核心函数。它会读取已有标志位，从尚未完成的那一步继续跑
- `_list_current_complete_fragments(self, work_unit, problem_id)`: 在判重前获取当前题目已经完成的解法列表

`_advance_fragment()` 是这份代码最关键的函数，可以按下面方式理解:

- 如果 `answer_matches_standard` 是 `false`，说明第二工序已经产生终止结果，此时只需要执行清理
- 如果 `is_duplicate_with_existing_complete_method` 是 `true`，说明判重已经产生终止结果，此时只需要执行清理
- 如果 `gemini_checked` 是 `false`，说明 Gemini 细查已经产生终止结果，此时只需要执行清理
- 如果某一步对应的标志还是 `null`，才说明那一步还没有完成，需要从这里继续执行
- 如果 `is_complete_fragment` 已经是 `true`，说明该 fragment 已经完整完成，不再重复处理

### `Problems2CotPipeline`

- 作用: 第二层的总装配器
- `__init__(self, config, generation_backend, duplicate_backend, gemini_backend)`: 组装 reader、scanner、task manager、executor，以及三个默认的配置驱动后端
- `run(self)`: 读取所有项目，构造 `WorkUnitRuntimeState`，生成 `TaskPlan`，先执行清理任务，再执行工作任务，最后返回统计报告

### `main()`

- 作用: 命令行入口
- 行为: 用默认配置构建 `Problems2CotPipeline`，执行 `run()`，最后打印统计结果

## 8. 建议的阅读顺序

如果现在直接看 `problems2cot.py`，建议按下面顺序读:

1. `Problems2CotConfig`
2. `OpenAICompatibleBackendConfig`
3. `ProblemContext`
4. `CoTFragmentStore`
5. `OpenAICompatibleChatClient`
6. `CoTFragmentScanner`
7. `GlobalTaskManager`
8. `CoTGenerator`
9. `AnswerMatcher`
10. `DuplicateMethodChecker`
11. `GeminiDetailChecker`
12. `FragmentTaskExecutor._advance_fragment`
13. `Problems2CotPipeline.run`

这样读的好处是，先把“数据怎么流动”和“状态怎么推进”看明白，再去看模型后端怎么接入，会清楚很多。
