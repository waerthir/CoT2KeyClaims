# Raw2Problems Spec

## 1. 目标

本 spec 描述当前版本 `Raw2Problems` 的具体设计。

当前代码文件对应关系：

- `config.py`：保存全部配置项
- `raw2problems.py`：保存完整处理逻辑

当前运行入口：

- `python raw2problems.py`

当前版本的目标很明确：

- 读取一个原始 `json` 文件
- 从原始数据中提取题目、标准答案、图片信息
- 将原始图片名字改写为标准相对路径
- 打包成统一的 `ProblemPackage`
- 写出到 `layer_problem/aaa/aaa.json`

本版本故意保持简单，不做多余抽象。

## 2. 当前版本的输入输出边界

### 2.1 输入

当前版本按“工作单元”处理输入。

工作单元发现规则：

- 默认遍历 `layer_input/` 下的所有一级子目录
- 也就是说，当前默认行为是：把 `layer_input/` 下的每一个工作单元文件夹都视为应处理对象
- 若 `config.py` 中设置了 `target_work_units`，则只处理指定工作单元
- 工作单元按名称排序后依次处理

`list_work_units()` 的实际作用：

- 它不是直接处理题目内容
- 它会先遍历 `layer_input/` 下的候选工作单元目录
- 再为每个目录构建一个 `WorkUnit`
- 最后把这些 `WorkUnit` 组成一个有序的工作单元列表

这个列表就是当前一次运行中要处理的“工作单元集群列表”或“工作集合”。

### 2.1.1 `WorkUnit` 的含义

`WorkUnit` 是当前代码中的运行期对象，用来表示“一个待处理工作单元”的完整路径与标识信息。

它不是输出 JSON 的字段，而是 pipeline 在内存中传递的中间对象。

当前代码中的 `WorkUnit` 包含：

- `file_id`
- `input_dir`
- `input_file`
- `image_dir`
- `output_dir`
- `output_file`

这些字段的作用分别是：

- `file_id`：当前工作单元的名字，也是后续主包中的文件级标识
- `input_dir`：当前工作单元输入目录，例如 `layer_input/aaa/`
- `input_file`：当前工作单元真正读取的输入 `json`
- `image_dir`：当前工作单元对应的图片目录
- `output_dir`：当前工作单元输出目录，例如 `layer_problem/aaa/`
- `output_file`：当前工作单元最终写出的主包路径

补充说明：

- 当前代码中，`WorkUnit` 是由 `RawJsonReader._build_work_unit()` 构建的
- 当前代码中，`image_dir` 统一由全局配置 `image_dir_name = test` 推出
- 未来如果不同工作单元允许使用不同图片目录名，那么最自然的承载位置也是 `WorkUnit.image_dir`

单个工作单元的输入示例是：

- `layer_input/aaa/aaa.json`

同时，工作单元根目录下应存在图片目录：

- `layer_input/aaa/test/`

说明：

- 当前代码会在每个工作单元目录中查找唯一一个匹配 `*.json` 的输入文件
- 若找不到匹配文件，会报错
- 若找到多个匹配文件，也会报错
- 图片统一认为放在工作单元根目录下的 `test/` 文件夹中
- 当前这套“遍历全部工作单元目录”的做法是可接受的默认策略，除非后续再单独设计筛选机制
- 输入格式本身不是这份 spec 的强绑定点
- 后续如果要换输入形式，应通过替换或修改 `RawJsonReader` 的行为实现，而不是改动后续标准化接口
- 未来设计上允许不同工作单元使用不同的图片目录名
- 但当前代码尚未实现“按工作单元分别指定图片目录名”的机制
- 因此当前版本仍统一使用 `test/` 作为图片目录

### 2.2 输出

输出固定为：

- `layer_problem/aaa/aaa.json`

输出对象为：

- `ProblemPackage`

补充说明：

- 输出目录不存在时，代码会自动创建
- `source_file_name` 记录的不是固定字符串 `aaa.json`，而是当前工作单元中实际读取到的输入文件名

## 3. 标识规则

### 3.1 `file_id`

- `file_id` 取自生信息文件名
- `file_id` 是字符串字段
- 例如工作单元名为 `aaa`

### 3.2 `problem_id`

- `problem_id` 是字符串字段
- 从长期设计意图看，`problem_id` 最好由上游或外部数据直接提供
- 第一层的理想职责是继承并保留这个外部给定的 `problem_id`
- 当前代码中，`problem_id` 由本层临时生成，这只是当前阶段的权宜实现
- `problem_id` 的当前目标格式固定为：`prob_` + 24 位 hex 字符串
- 当前推荐使用小写 hex
- 示例：`prob_9b0a7ef70ee83d702776eea6`

当前版本对 `problem_id` 的生成策略只锁定两点：

- 必须由专门的 `ProblemIdGenerator` 负责生成
- 必须方便后续替换生成规则

补充说明：

- 原始文件中的题目顺序是稳定的
- 当前代码确实按遍历顺序逐题生成 `problem_id`
- 当前代码的具体算法如下：
  1. 取 `file_id`
  2. 取当前题目的 `record_index`
  3. 取原始字段中的 `picture`
  4. 取原始字段中的 `question`
  5. 取原始字段中的 `standard_answer`，若不存在则回退取 `answer`
  6. 将上述内容组成一个字典
  7. 用 `json.dumps(..., ensure_ascii=False, sort_keys=True)` 转成字符串
  8. 对该字符串做 `sha1`
  9. 取前 24 位小写 hex
  10. 最前面加上前缀 `prob_`

因此，当前代码中的 `problem_id` 是“由文件标识 + 题目顺序 + 题目关键内容”共同决定的稳定字符串。

但需要明确：

- 这套生成逻辑只是当前实现的过渡方案
- 它不代表长期架构中 `problem_id` 必须由第一层自行生成
- 一旦上游开始稳定提供 `problem_id`，第一层应优先直接继承外部给定值
- 到那时，`ProblemIdGenerator` 可以被降级为兼容旧数据的过渡工具，或被移除

本层不引入：

- `problem_info_id`
- 任何额外题目级哈希 id

## 4. 内部职责设计

当前版本建议分成五个职责块，外面再由一个总 pipeline 串起来。

### 4.1 `RawJsonReader`

职责：

- 遍历 `layer_input/`，构建 `WorkUnit` 列表
- 读取 `layer_input/aaa/aaa.json`
- 将原始 `json` 解析为内存中的原始对象
- 不做字段标准化
- 不做图片路径改写

边界：

- 负责“找出有哪些工作单元要处理”
- 负责把目录信息组装成 `WorkUnit`
- 负责“读进来”
- 不负责业务字段提取
- 不负责输出文件写入

当前代码中，`RawJsonReader` 主要分成两步：

1. `list_work_units()`
   - 遍历 `layer_input/` 下的一级目录
   - 调用 `_build_work_unit()` 为每个目录构建 `WorkUnit`
   - 返回一个 `list[WorkUnit]`
2. `read(work_unit)`
   - 根据给定的 `WorkUnit.input_file` 读取并解析原始 `json`

当前代码中的额外校验：

- 顶层必须是 `[]`
- 列表中的每个元素必须是 `{}`

当前已确认的一版原始 `json` 结构是：

```json
[
  {
    "picture": "img1.png",
    "question": "题目文本",
    "standard_answer": "标准答案"
  }
]
```

说明：

- 整体是一个 `[]`
- 列表中的每个元素是一个 `{}` 题目对象
- 当前已确认需要消费的原始字段只有：
  - `picture`
  - `question`
  - `standard_answer`

当前代码的兼容行为：

- 若题目对象里没有 `standard_answer`，但有 `answer`，则后续仍可继续处理

### 4.2 `ProblemIdGenerator`

职责：

- 为每道题生成标准化的 `problem_id`
- 将 `problem_id` 生成规则与其余字段处理逻辑解耦

定位说明：

- `ProblemIdGenerator` 是当前实现中的过渡组件
- 它存在的主要原因，是当前输入数据里还没有稳定给好的 `problem_id`
- 它的设计目的之一，就是方便后续在“外部直接提供 `problem_id`”后被替换、旁路或移除

当前版本锁定的输出格式：

- `prob_` + 24 位 hex 字符串

示例：

- `prob_9b0a7ef70ee83d702776eea6`

当前版本的设计要求：

- `ProblemIdGenerator` 必须是独立类
- 后续如果要改 `problem_id` 规则，应只修改这个类
- 当前 spec 允许后续替换算法
- 但当前代码实际采用的是 `sha1 + 截断 24 位 hex` 的生成方式
- 由于原始文件有序，当前实现会基于题目遍历顺序生成稳定 id

长期期望：

- 若未来原始输入中已直接包含可靠的 `problem_id`
- 则第一层应优先读取并继承该值
- 而不是继续无条件调用 `ProblemIdGenerator`

边界：

- 只负责生成 `problem_id`
- 不负责读取原始 `json`
- 不负责处理图片路径
- 不负责最终写出文件

### 4.3 `ImagePathResolver`

职责：

- 接收原始图片标注信息
- 将“只有图片名字”的旧标注改写成标准相对路径

当前版本的固定规则：

- 原始图片标注只提供图片名字，不提供完整路径
- 标准化后统一写成相对于工作单元根目录 `aaa/` 的相对路径
- 图片目录固定为 `test/`
- 规则是：`test/` + 图片名字

示例：

- 原始图片名：`img1.png`
- 标准化结果：`test/img1.png`

补充约束：

- JSON 中的路径字符串统一使用正斜杠 `/`
- 当前版本只做路径字符串改写，不负责移动图片文件
- 当前版本不负责检查图片文件是否真实存在

当前代码的兼容行为：

- 若 `picture` 是字符串，则输出单元素列表
- 若 `picture` 是字符串列表，则逐个改写路径
- 若 `picture` 是 `null`，且配置 `allow_empty_picture=True`，则输出空列表 `[]`
- 若图片名中包含反斜杠 `\`，会先转成正斜杠 `/`
- 若图片名以 `/` 开头，会先去掉前导分隔符

未来设计意图：

- 从 spec 角度，图片目录名不必永久固定为 `test/`
- 后续允许为不同工作单元配置不同图片目录
- 一旦后续引入这项能力，`ImagePathResolver` 应从当前工作单元配置中读取图片目录名，而不是继续假定所有工作单元相同
- 当前版本先不要求代码实现这一点

### 4.4 `ProblemFieldProcessor`

职责：

- 从 `RawJsonReader` 读出的原始对象中提取目标字段
- 将提取结果整理成统一的问题对象
- 调用 `ImagePathResolver` 处理图片字段

当前版本必须提取并标准化的目标字段：

- `problem_id`
- `question_text`
- `standard_answer`
- `images`
- `multi_solution_hint`

当前版本已确认的原始字段到标准字段的映射是：

- `question` -> `question_text`
- `standard_answer` -> `standard_answer`
- `picture` -> `images`

当前代码对答案字段的兼容映射是：

- `standard_answer` -> `standard_answer`
- 若缺失，则 `answer` -> `standard_answer`

字段处理规则：

- `problem_id`：当前代码中由 `ProblemIdGenerator` 生成并写入标准字段；长期目标是优先继承外部提供的 `problem_id`
- `question_text`：从原始字段 `question` 提取并写入标准字段
- `standard_answer`：优先从原始字段 `standard_answer` 提取；若缺失则回退到 `answer`
- `images`：从原始字段 `picture` 取出图片名字，再交给 `ImagePathResolver` 转成相对路径列表
- `multi_solution_hint`：作为“是否多解”的预留接口字段，当前强制写为 `null`

当前版本可选补充的字段：

- `source_meta`
- `ingest_status`

建议默认值：

- `source_meta`: `{}`
- `ingest_status`: `"ready"`

边界：

- 负责字段提取与标准化
- 不负责最终文件写出

当前代码中的额外校验：

- `picture` 字段必须存在
- `question` 字段必须存在且必须是字符串
- `standard_answer` 或 `answer` 至少要存在一个，并且最终取到的值必须是字符串

说明：

- 当前 spec 已锁定三项原始字段映射：
  - `picture`
  - `question`
  - `standard_answer`
- 当前代码中，`problem_id` 由 `ProblemIdGenerator` 统一生成
- 但从目标架构看，`problem_id` 更应由外部直接提供，第一层只负责标准化继承
- 当前代码中的默认输出值为：
  - `source_meta = {}`
  - `multi_solution_hint = null`
  - `ingest_status = "ready"`

### 4.5 `ProblemPackageWriter`

职责：

- 接收 `ProblemFieldProcessor` 输出的标准化题目列表
- 按统一 schema 组装 `ProblemPackage`
- 将结果写到 `layer_problem/aaa/aaa.json`

当前版本固定写出的顶层字段：

- `file_id`
- `stage`
- `source_file_name`
- `problems`

固定值规则：

- `file_id = aaa`
- `stage = "raw_to_problem"`
- `source_file_name = 当前工作单元中实际读取到的输入文件名`

边界：

- 负责最终打包和写出
- 不负责原始数据解析
- 不负责字段抽取细节

当前代码中的写出行为：

- 使用 `utf-8`
- 使用 `indent = 2`
- 使用 `ensure_ascii = False`
- 写出后补一个换行符

### 4.6 `Raw2ProblemsPipeline`

职责：

- 统一组装并持有 reader、id generator、image resolver、field processor、writer
- 负责遍历全部工作单元
- 负责对每个工作单元调用完整处理流程

边界：

- 负责模块编排
- 不新增业务字段
- 不改变单题标准化规则

### 4.7 函数级说明

这一节不讨论抽象职责，只用最直接的话解释当前 `raw2problems.py` 里每个函数/方法在干什么。

#### 4.7.1 `WorkUnit`

- `WorkUnit(...)`
  这是一个数据容器。
  它本身不做处理，只负责把一个工作单元要用到的路径和标识打包在一起。

#### 4.7.2 `RawJsonReader`

- `RawJsonReader.__init__(config)`
  保存配置，后面所有读文件行为都从这里拿配置。

- `RawJsonReader.list_work_units()`
  遍历 `layer_input/` 下的工作单元目录。
  对每个目录调用 `_build_work_unit()`。
  最后返回一个 `WorkUnit` 列表。

- `RawJsonReader.read(work_unit)`
  读取某个工作单元真正的输入 `json` 文件。
  把文件内容解析成 Python 里的列表对象。
  同时检查顶层是不是列表、里面每项是不是字典。

- `RawJsonReader._build_work_unit(work_unit_name)`
  根据工作单元名字，推导出输入目录、输入文件、图片目录、输出目录、输出文件。
  然后把这些信息组装成一个 `WorkUnit`。

- `RawJsonReader._resolve_input_file(input_dir)`
  在某个工作单元目录里查找唯一一个匹配 `*.json` 的输入文件。
  如果没有找到，报错。
  如果找到多个，也报错。

#### 4.7.3 `ProblemIdGenerator`

- `ProblemIdGenerator.__init__(config)`
  保存配置，主要是 `problem_id` 前缀、长度、哈希算法这些。

- `ProblemIdGenerator.generate(file_id, record_index, raw_record)`
  为一条原始题目生成 `problem_id`。
  当前做法是把 `file_id`、题目序号、题目关键字段拼成一个字典，转成字符串后做哈希，再取前 24 位，最后前面加 `prob_`。

#### 4.7.4 `ImagePathResolver`

- `ImagePathResolver.__init__(config)`
  保存配置，主要是图片目录名和路径分隔符。

- `ImagePathResolver.resolve(picture_value)`
  接收原始 `picture` 字段。
  先把它规范成“图片名列表”，再把每个图片名改成相对路径列表。

- `ImagePathResolver._normalize_picture_names(picture_value)`
  处理各种可能的 `picture` 形态。
  例如字符串、字符串列表、`null`。
  最后统一变成干净的图片名列表。

- `ImagePathResolver._join_relative_path(prefix, picture_name)`
  只做一件事：把图片目录前缀和图片名拼成相对路径。
  例如把 `test` 和 `img1.png` 拼成 `test/img1.png`。

#### 4.7.5 `ProblemFieldProcessor`

- `ProblemFieldProcessor.__init__(config, id_generator, image_path_resolver)`
  保存配置，并接收两个辅助组件：
  一个负责生成 `problem_id`，一个负责处理图片路径。

- `ProblemFieldProcessor.process_records(file_id, raw_records)`
  处理一个工作单元里的全部原始题目。
  它会逐条遍历原始记录，先校验，再逐条标准化，最后返回标准化后的题目列表。

- `ProblemFieldProcessor._process_single_record(file_id, record_index, raw_record)`
  处理单条题目。
  它会生成 `problem_id`，提取题干和标准答案，处理图片路径，并补上默认字段。

- `ProblemFieldProcessor._validate_required_raw_fields(raw_record, file_id, record_index)`
  检查一条原始题目是不是具备最低要求字段。
  当前会检查 `picture`、`question`、以及 `standard_answer/answer`。

- `ProblemFieldProcessor._extract_picture(raw_record)`
  从原始题目里拿出 `picture` 字段本身，不做额外处理。

- `ProblemFieldProcessor._extract_question(raw_record)`
  从原始题目里拿出 `question`。
  同时检查它是不是字符串。

- `ProblemFieldProcessor._extract_standard_answer(raw_record)`
  优先取 `standard_answer`。
  如果没有，再尝试取 `answer`。
  如果都不对，就报错。

#### 4.7.6 `ProblemPackageWriter`

- `ProblemPackageWriter.__init__(config)`
  保存配置，主要是输出编码、缩进、`stage` 名称这些。

- `ProblemPackageWriter.build_package(file_id, source_file_name, processed_records)`
  把已经标准化好的题目列表包成一个完整的 `ProblemPackage` 字典。

- `ProblemPackageWriter.write(output_file, package)`
  把 `ProblemPackage` 真正写到磁盘。
  如果输出目录不存在，会先创建目录。

#### 4.7.7 `Raw2ProblemsPipeline`

- `Raw2ProblemsPipeline.__init__(config)`
  创建并组装整条流水线要用到的组件：
  reader、id generator、image resolver、field processor、writer。

- `Raw2ProblemsPipeline.run()`
  执行整条流水线。
  它会先拿到全部工作单元列表，再逐个处理，最后返回所有写出的输出文件路径。

- `Raw2ProblemsPipeline.process_work_unit(work_unit)`
  处理单个工作单元。
  它会检查图片目录是否存在，读取原始数据，标准化题目列表，打包，再写出结果。

#### 4.7.8 顶层入口

- `main()`
  这是脚本入口。
  它会创建 `Raw2ProblemsPipeline`，执行 `run()`，然后把写出的文件路径打印出来。

## 5. 处理流程

当前版本的处理流程固定为：

1. `Raw2ProblemsPipeline` 读取配置
2. `RawJsonReader` 枚举需要处理的工作单元
3. 对每个工作单元，先确认图片目录 `test/` 存在
4. `RawJsonReader` 找到该工作单元中唯一一个 `*.json`
5. `RawJsonReader` 将输入文件读成顶层 `list[dict]`
6. `ProblemFieldProcessor` 按原始题目对象的遍历顺序逐题处理
7. `ProblemFieldProcessor` 先检查原始字段是否满足最低要求
8. 当前实现中，`ProblemIdGenerator` 为当前题生成 `problem_id`
9. `ProblemFieldProcessor` 从 `question` 提取 `question_text`
10. `ProblemFieldProcessor` 提取 `standard_answer`，必要时从 `answer` 回退
11. `ProblemFieldProcessor` 从 `picture` 提取原始图片信息
12. `ImagePathResolver` 将图片名字改写为 `test/<image_name>` 或 `[]`
13. `ProblemFieldProcessor` 写入默认字段：
    - `source_meta = {}`
    - `multi_solution_hint = null`
    - `ingest_status = "ready"`
14. `ProblemPackageWriter` 将全部标准化题目打包为 `ProblemPackage`
15. `ProblemPackageWriter` 写出到 `layer_problem/aaa/aaa.json`

## 6. 标准输出结构

### 6.1 `ProblemPackage`

```json
{
  "file_id": "aaa",
  "stage": "raw_to_problem",
  "source_file_name": "aaa.json",
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

说明：

- 这里示例采用当前版本规定的 `prob_` + 24 位 hex 格式
- 具体 24 位 hex 如何生成，由 `ProblemIdGenerator` 决定

### 6.2 单题标准字段

每道题当前必须有：

- `problem_id`
- `question_text`
- `standard_answer`
- `images`
- `multi_solution_hint`

当前允许保留：

- `source_meta`
- `ingest_status`

## 7. 当前版本的约束

- 每个工作单元当前只允许存在一个可读取的 `*.json`
- 当前默认会处理 `layer_input/` 下的所有工作单元目录
- 图片目录固定按 `test/` 处理
- `images` 中保存的是相对工作单元根目录的相对路径
- 图片路径标准化规则固定为 `test/<image_name>`
- 输出中每道题都必须保留 `multi_solution_hint`
- 当前 `multi_solution_hint` 强制写为 `null`
- 当前版本只负责提取与标准化，不负责推理相关任务

## 8. 当前代码中的兼容策略

为了兼容当前已存在的数据，代码额外支持以下行为：

- 原始答案字段既可叫 `standard_answer`，也可叫 `answer`
- 原始 `picture` 可以是字符串、字符串列表，或 `null`
- 当 `picture = null` 时，当前配置下输出 `images = []`
- 当前代码检查图片目录是否存在，但不检查 `images` 中每个路径对应的图片文件是否真实存在

## 9. 当前配置项

当前 `config.py` 中与 `Raw2Problems` 直接相关的关键配置包括：

- `input_root`
- `output_root`
- `input_file_glob`
- `image_dir_name`
- `stage_name`
- `allow_empty_picture`
- `raw_picture_field`
- `raw_question_field`
- `raw_standard_answer_fields`
- `problem_id_prefix`
- `problem_id_hex_length`
- `hash_algorithm`
- `path_separator`
- `source_meta_default`
- `multi_solution_hint_default`
- `ingest_status_default`
- `json_encoding`
- `json_indent`
- `ensure_ascii`
- `target_work_units`

这些配置项当前都已集中写在 `config.py` 中，而不是散在主逻辑里。

## 10. 当前版本暂不展开的内容

以下部分故意留待后续讨论：

- 是否继续沿用当前 `ProblemIdGenerator` 的 `sha1 + 截断 24 位 hex` 算法
- 是否继续保留当前图片字段兼容策略（字符串 / 列表 / `null`）
- 是否需要引入“按工作单元分别配置图片目录名”的机制
- 是否需要引入“只处理部分工作单元”的正式筛选策略
- 坏样本、缺字段样本的处理规则
- 是否保留更多 `source_meta`
- 是否做图片存在性校验

## 11. 当前版本结论

这个版本的 `Raw2Problems` spec 已经明确成一个简单流水线：

- 先找工作单元
- 再读唯一输入 `json`
- 再逐题生成或继承 `problem_id`
- 再提字段并标准化图片路径
- 最后打包输出

这份 spec 现在已经不只是抽象设计，也基本等价于当前 `raw2problems.py` 的真实运行逻辑。
