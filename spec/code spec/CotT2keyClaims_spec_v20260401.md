# CotT2keyClaims Spec

## 1. 目标

本层负责读取上一层的 `CoTPackage`，将其中每个方法的 CoT 拆成 `key claims`，并组织成：

- claims 碎片
- claims 主包

本层必须遵循：

1. 先逐方法生成碎片
2. 每个碎片生成后立即保存
3. 碎片收齐后再打包主 JSON

## 2. 标识规则

### 2.1 `file_id`

- `file_id` 直接取自工作单元文件名
- `file_id` 是字符串字段
- 例如 `aaa`

### 2.2 `problem_id`

- `problem_id` 来自上一层主包中的题目对象
- `problem_id` 原样继承，不重新生成

### 2.3 `method_id`

- `method_id` 来自上一层
- 本层只能继承，不能重排
- `method_id` 是字符串字段
- `method_id = problem_id + "_" + 序数id`

因此，`method_id` 本身就是方法与碎片的唯一标识。

### 2.4 碎片命名规则

本层不生成额外碎片 id。

碎片文件名固定为：

- `method_id + ".json"`

示例：

- 若 `problem_id = sample_unique_id_string`
- 且 `method_id = sample_unique_id_string_1`
- 则碎片文件名为 `sample_unique_id_string_1.json`

说明：

- 这里的 `sample_unique_id_string` 只是占位写法
- 不代表真实 `problem_id` 必须采用这种格式

## 3. 文件组织

### 3.1 相关目录

- `layer_cot`
- `layer_key_claims`

### 3.2 工作单元目录

假设工作单元名为 `aaa`，则：

- 输入主包：`layer_cot/aaa/aaa.json`
- 输出主包：`layer_key_claims/aaa/aaa.json`
- 碎片目录：`layer_key_claims/aaa/key_claims_fragments/`

## 4. 输入

本层标准输入是上一层主包文件：

- `layer_cot/aaa/aaa.json`

本层不直接以零散 CoT 片段为主输入。
输入中的 `images` 沿用第一层标准化结果，每个元素都是相对于工作单元根目录 `aaa/` 的相对路径。

## 5. 碎片对象：`ClaimFragment`

本层最小保存单位是 claims 碎片。

每个碎片对应：

- 某个 `problem_id`
- 某个 `method_id`
- 该方法下的一整组 key claims

文件位置示意：

- `layer_key_claims/aaa/key_claims_fragments/<method_id>.json`

推荐逻辑结构：

```json
{
  "file_id": "aaa",
  "problem_id": "sample_unique_id_string",
  "method_id": "sample_unique_id_string_1",
  "key_claims": [
    {
      "claim_id": "m1_c1",
      "text": "题干给出 r 组为 rhc1 功能缺失突变体。",
      "claim_type": "题目信息",
      "is_final_answer": false
    },
    {
      "claim_id": "m1_c2",
      "text": "图2中高浓度 CO2 条件下 r 组气孔开放度高于 wt 组。",
      "claim_type": "图片信息",
      "is_final_answer": false
    },
    {
      "claim_id": "m1_c3",
      "text": "rhc1 基因产物促进气孔关闭。",
      "claim_type": "推理信息",
      "is_final_answer": true
    }
  ],
  "extraction_status": "accepted",
  "ready_for_packaging": true
}
```

## 6. 保存原则

本层必须“生成即保存”：

- 每完成一个方法的 claims 提取，就立刻保存为 `ClaimFragment`
- 不等待整批题结束后再统一写出
- 最终主包只从已保存碎片汇总

## 7. 主包对象：`ClaimsPackage`

本层最终输出主包文件：

- `layer_key_claims/aaa/aaa.json`

这个文件的 id 直接就是：

- `aaa`

需要明确的是：

- 这个主 JSON 文件的内容不是“题目原文”
- 而是本层最终汇总后的 key claims package
- 它是本层标准结果文件

推荐逻辑结构：

```json
{
  "file_id": "aaa",
  "stage": "cot_to_claims",
  "source_cot_file_id": "aaa",
  "problems": [
    {
      "problem_id": "sample_unique_id_string",
      "question_text": "题目文本",
      "standard_answer": "标准答案",
      "images": ["image_dir_name_tbd/img1.png"],
      "cot_methods": [
        {
          "method_id": "sample_unique_id_string_1",
          "cot_steps": ["步骤1", "步骤2"],
          "key_claims": [
            {
              "claim_id": "m1_c1",
              "text": "图中给出三期岸线变化。",
              "claim_type": "图片信息",
              "is_final_answer": false
            },
            {
              "claim_id": "m1_c2",
              "text": "冬半年北侧侵蚀、南侧淤积。",
              "claim_type": "推理信息",
              "is_final_answer": false
            },
            {
              "claim_id": "m1_c3",
              "text": "冬季移动固沙障应主要布设在北侧。",
              "claim_type": "推理信息",
              "is_final_answer": true
            }
          ]
        }
      ]
    }
  ]
}
```

## 8. 打包条件

本层的完整性检查更明确，因为输入已经是上一层主包。

对本层而言：

- 上一层主包中每个被纳入的 `method_id`
- 都必须对应一个且仅一个合格的 `ClaimFragment`

## 9. `key claim` 定义

一个 `key claim` 是：

> 为了从当前题目的输入到达正确答案，所必需的一条最小命题单元。

这里的“最小”不是越细越好，而是：

- 再压缩会丢失解题必需信息
- 再拆分会退化成机械中间式或零散碎片

## 10. `key claims` 的粒度规则

### 10.1 基本要求

每条 claim 应满足：

- 一条 claim 只表达一个可独立使用的命题
- 只保留对最终答案真正必要的信息
- 尽量写成最简表达
- 不与其他 claims 重复

### 10.2 允许的合并

“原子化”不等于“每个数都单独一条”。

以下情形允许作为一条 claim 保留：

- 同一处题干中绑定出现且必须一起使用的一组条件
- 同一局部图像中一次性读取的一组视觉事实
- 同一个紧密绑定的关系表达

例如可以是一条：

- “图中有两个三角形，FE=3，DE=x，CB=15，AB=45”

### 10.3 不应单独保留的内容

以下内容通常不应成为 key claim：

- 纯机械代数变形的每个中间式
- 同义重复
- 修辞连接词
- 与答案无关的观察
- 模型自我确认、试错、回退痕迹

## 11. 标签体系

本层只使用三类标签：

- `题目信息`
- `图片信息`
- `推理信息`

### 11.1 `题目信息`

直接来自题干文本、选项、已知条件、实验设定、表格文字、符号定义的信息。

判定原则：

- 不看图也能直接从题目文字中读取的，归为 `题目信息`

### 11.2 `图片信息`

直接来自图像、图表、示意图、坐标图、流程图、实验图的必要视觉事实。

判定原则：

- 主要依赖“看图”获得，而不是依赖规则推导的，归为 `图片信息`

### 11.3 `推理信息`

基于题目信息和/或图片信息，经由比较、桥接、规则调用、计算、映射得到的必要结论。

判定原则：

- 一旦不是直接给定或直接看到，而是经过推导得到，就归为 `推理信息`

## 12. 最终答案与多解题规则

### 12.1 最终答案

- 每个 `method_id` 必须显式包含最终答案
- 最终答案 claim 的类型固定为 `推理信息`
- 最终答案默认位于该方法 claims 的末尾
- 若某条结论与最终答案完全同义，可直接把该条标为最终答案 claim，而不重复写一条

### 12.2 多解题

- 一道题的不同解法必须拆成不同 `method_id`
- 每个 `method_id` 都拥有自己独立的 CoT 和 claims
- 不同方法不得混合成一条链
- 若只是表述不同但骨架相同，不单列新方法
- 若核心推理路径不同，应分成不同方法

## 13. 自检标准

一个 claims 结果能进入主包，至少要满足：

- 有明确的 `problem_id` 和 `method_id`
- 每条 claim 的标签清晰
- 包含最终答案 claim
- 不含明显重复或明显无关内容

可用一个简单问题判断某条 claim 是否真的关键：

> 如果删掉这条 claim，这个方法还能否稳定到达正确答案？

若答案是“可以”，这条 claim 很可能不是 key claim。

## 14. 本层约束

- 本层不引入 `method_uid`、`fragment_id` 等额外 id
- 本层碎片文件名统一采用 `method_id + ".json"`
- 本层只负责 claims 抽取与结构化，不负责重新组织方法编号
