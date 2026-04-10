本文档仅由人类负责编写，严禁引入任何非严格审查的内容；如有可能，应该避免重复描述以及复制粘贴
本文档不负责md格式的维护
本文档意图在于清晰地描述程序的意图，唯一的目的只有一个：不影响速度的前提下，最大化表达编写者的意图，最大化软件的可理解性
本文档管理了项目的所有意图或者部分意图

----
这部分描述了CoT_Generator的实现
----

文件形如：
layer_problem
|-- problem_set
|   |-- certain_problem.json
|
|-- problem_set_2
    |-- certain_problem.json

customed_folder
|-- picture_1.jpg
|-- picture_2.png

每一个certain_problem.json应该关注的字段如下：
"problems": [
    {
        "problem_id": str, 描述了问题的id, 是一个特定的字符串, 且每个文件内保证唯一
        "question_text": str, 问题的具体文本
        "standard_answer": str, 描述了问题的答案
        "images": [
            "picture_1.jpg"
        ]
        "multi_solution_hint": {...}, 保留字段，可能之后会有用处
    },
    {
        ...
    },
    ...
]

仅关注"problems"

输出形如
layer_CoT
|-- problem_set
    |-- prob_12345678901234567890abcd_1.json
    |-- prob_12345678901234567890abcd_2.json

对于每个json，内部内容和具体含义如下：
json的命名为对应的<problem_id>_<method_id>组成
<problem_id>直接取自于对应的problem问题，method_id是数字，指示了是该问题的解法序号
如上所示，这意味着上述两个文件分别是problem_id为prob_12345678901234567890abcd的问题的解法1和解法2

解法内部应该有的字段如下所示：
{
    "problem_id": 原问题对应字段保留下来
    "question_text": 原问题对应字段保留下来
    "standard_answer": 原问题对应字段保留下来
    "images": 原问题对应字段保留下来
    "multi_solution_hint": 原问题对应字段保留下来

    "method_id": int, 指示了问题解法的内部编号，在每个问题下唯一
    "CoT": str, 文本化的解法的CoT, 例如"1, xxxx. 2, xxxx. 3, 答案是xxxx"
    "model_answer": 模型返回的答案

    "is_answer_check": "true" | "false" | "null", 这三个参数指示了回答有没有被检查, true为已经检查且正确, 相对应的false为错误, null表示仍未被检查

    "is_detail_check": "true" | "null", 含义true为已经校正过，null表示仍未被检查
    "detail_checked_CoT": "" | "具体字符串", 含义为被Gemini检查调整过的新CoT.

    "is_answer_unique_check": "true" | "false" | "null", 含义同上
}

输入参数如下：
folder_name: 对应的文件夹名字
allow_send_standard_answer: true | false , 该模式下，同时向模型发送标准答案以获取答案匹配的CoT，同时不再进行answer_check部分
allow_send_other_answer: true | false , 该模式下，同时向模型发送已有的其他解法以获取不同解法的CoT
allow_multiple_answer: true | false, 该模式下调用多解判断器会正常解析，否则会返回只需要一个解
allow_answer_check = true | false, 指示应不应该对答案进行检查
answer_check_mode: "regular" | "LLM" , 指示如何对答案进行比对检查，使用机械匹配还是LLM检查
allow_detail_check: true | false , 指示应该不应该进行细化检查
allow_answer_unique_check: true | false , 指示是否应该进行答案重复的检查
picture_path: 指示了应该在哪个文件夹下按照images指定的路径进行图片寻找



具体情景1：
layer_problem
|-- problem_set
    |-- certain_problem.json

layer_CoT
|

customed_folder
|-- picture_1.jpg
|-- picture_2.png


certain_problem.json内部的内容为：
"problems": [
    {
        "problem_id": "prob_12345678901234567890abc1"
        "question_text": "xxxx"
        "standard_answer": "xxxx"
        "images": [
            "picture_1.jpg"
        ]
        "multi_solution_hint": ""
    },
    {
        "problem_id": "prob_12345678901234567890abc2"
        "question_text": "xxxx"
        "standard_answer": "xxxx"
        "images": [
            "picture_1.jpg"
        ]
        "multi_solution_hint": ""
    }
]

参数为：
folder_name = problem_set
allow_send_standard_answer = false
allow_send_other_answer = false
allow_multiple_answer = false
allow_answer_check = true
answer_check_mode = "LLM"
allow_detail_check = true
allow_answer_unique_check = false
picture_path = customed_folder

流程描述：
layer_problem里面读入problem_set，检查里面存在唯一的json problem_set.json；
layer_CoT检查有没有文件夹名为problem_set，如果没有，则创建，如果有，则调用检查器进行检查（检查的具体行为会在下一个例子给出）。
检查器阅读layer_problem内的problem_set，得到原始任务id，阅读layer_CoT内的problem_set，根据先前的格式<problem_id>_<method_id>获取碎片任务，最后得到两个任务池：
|-- 碎片任务池：(任务id, 解法id, 是否完成)这样的元组的集合，其中根据参数allow_answer_check = true，allow_detail_check = true，allow_answer_unique_check = false，来判断layer_CoT内的problem_set内的每个解法碎片是否被完成，如果完成，对应的是否完成位标记为true，否则false。这里由于完全没有解法，所以为空。
    |-- 判断是否完成的标准如下：例如，对于allow_answer_check = true，则应该检查碎片内对应的位(is_answer_check)是不是null，若是，则记为未完成
    |-- 对于allow_answer_unique_check = false，则可以不检查is_answer_unique_check里面的状态
    |-- 三项之中有一项没有完成就视为未完成
|-- 原始任务池: (原始任务id, 对应的multi_solution_hint, 已有解法数量)的集合，其中已有解法数量这一项可以从碎片任务池里面获取相关信息。里面这有("prob_12345678901234567890abc1", "", 0)和("prob_12345678901234567890abc2", "", 0)
任务调度器根据已有的两个任务池，先使用多解判断器
|-- 多解判断器对已有的两个任务池进行探查
|-- 多解判断器对每个原始任务池里面的元组进行判断，并判断应该被执行的任务池。例如("prob_12345678901234567890abc1", "", 0)，由于参数allow_multiple_answer = false，不需要进行具体判断，所以得到该任务需要解法数量为1；如果allow_multiple_answer = true，则需要根据对应的multi_solution_hint字段内容进行判断，给出对应的需要的解法数量。最后得到需要解法数量为1，已有解法数量0，因此对这个问题，"prob_12345678901234567890abc1"应该被执行，会被加进执行任务池里面
|-- 多解判断器最后给出执行任务池，里面有"prob_12345678901234567890abc1"和"prob_12345678901234567890abc2"
任务调度器根据执行任务池，调用多线程进行任务分发。多线程的线程数配置在config里面的problem2CoT里面的multi_thread_worker_num给出
接下来跟踪一个任务"prob_12345678901234567890abc1"
|-- 进入碎片管理器
    |-- 先去碎片任务池里面找是否有未完成的碎片任务，发现没有
    |-- 产生碎片记录号，也就是<problem_id>, <method_id>的形式，这里使用元组储存，是(prob_12345678901234567890abc1, 1)，碎片会在下一步被创建
    |-- method_id从1开始使用
    |-- 要注意这里不能和碎片任务池里面的已完成任务的解法id重合，也就是说需要去碎片任务池找到已有的编号并且避开，产生顺位新编号
        |-- 例如，碎片任务池里面里面有两个该问题的已完成解法，method_id分别为1，2，则这里应该创建的method_id应该是3
    |-- 另一种情况是，如果去碎片任务池里面找是否有未完成的碎片任务而发现有一个，因此不会创建新的碎片，则直接返回这个碎片对应的碎片记录号，可以直接从碎片任务池里面得知这个信息
    |-- 因此，碎片管理器会知道两个信息，一个是碎片记录号，一个是对应的当前碎片是否被被创建
|-- 碎片管理器返回(碎片记录号, 该碎片是否被创建)
|-- 这里是((prob_12345678901234567890abc1, 1), false)
|-- 进入CoT生成器，同时发送碎片记录号里面携带的method_id信息，以及该碎片是否被创建
    |-- 由于获取信息：该碎片没有被创建，所以CoT生成器不会被跳过执行；反之CoT生成器会直接返回，不执行
    |-- 生成器有两个部分，第一部分是获取回复器，根据对应的参数发送问题然后获取模型的CoT回复
    |-- 会根据参数allow_send_standard_answer = false和allow_send_other_answer = false判断是否发送对应内容
        |-- 若allow_send_standard_answer = true，则应该同时发送标准答案
        |-- 其中若allow_send_other_answer = true，还需要去碎片任务池找到这个问题下已经完成的解法id，读取里面的文件内容找到对应的解法，并一起打包发送过去
            |-- 这里还要装一个解法寻找器，根据problem_id和对应的method_id，找到对应的解法碎片文件的路径，并且把解法载入进来，进行发送
    |-- 此外，图片的发送会因为参数picture_path = customed_folder，而会在customed_folder下寻找对应的picture_1.jpg
    |-- 第二部分是将获取的信息写入到将创建的碎片里面，包括了一个模型返回的CoT和模型给出的model_answer和碎片记录号给出的method_id
    |-- 这里案例是创建新碎片，内容如下：
{
    "problem_id": "prob_12345678901234567890abc1"
    "question_text": "xxxx"
    "standard_answer": "xxxx"
    "images": [
        "picture_1.jpg"
    ]
    "multi_solution_hint": ""
    也就是原内容的保留

    "method_id": 1，即对应的碎片管理器给出的编号
    "CoT": 设为模型的对应回复
    "model_answer": 设为模型的对应回复

    "is_answer_check": 设为"null"

    "is_detail_check": 设为"null"
    "detail_checked_CoT": 设为""

    "is_answer_unique_check": 设为"null", 
}
|-- 将其保存在layer_CoT/problem_set/prob_12345678901234567890abc1_1.json。应该将其保存下来
|-- 接下来进入答案检查器
    |-- 根据先前的碎片记录号读取刚刚保存好的碎片
    |-- 根据参数allow_answer_check = true判断应该进行答案检查
    |-- 然后，根据参数is_answer_check是null，可以看出来答案检查这步还没有进行
        |-- 如果这个is_answer_check不是null，也就是是true或者false，则应该判断答案检查已经完成，那么应该直接退出
    |-- 由于参数answer_check_mode = "LLM"，将标准答案和模型答案打包发送给模型，模型返回两个答案是否匹配
        |-- 如果参数是"regular"，那么使用一个常规匹配器判断答案是否等效
    |-- 如果匹配，那么is_answer_check就设置为true，反之设置为false
    |-- 将内容写回至碎片prob_12345678901234567890abc1_1.json内
    |-- 现在内容如下，假设模型认为答案匹配：
{
    "problem_id": "prob_12345678901234567890abc1"
    "question_text": "xxxx"
    "standard_answer": "xxxx"
    "images": [
        "picture_1.jpg"
    ]
    "multi_solution_hint": ""
    也就是原内容的保留

    "method_id": 1，即对应的碎片管理器给出的编号
    "CoT": "模型的对应回复"
    "model_answer": "模型的对应回复"

    "is_answer_check": "true"

    "is_detail_check": "null"
    "detail_checked_CoT": ""

    "is_answer_unique_check": "null", 
}
|-- 进入细节验证器
    |-- 根据先前的碎片记录号读取刚刚保存好的碎片
    |-- 根据参数allow_detail_check = true判断应该进行细节检查
    |-- 然后，根据参数is_detail_check是null，可以看出来答案检查这步还没有进行
        |-- 如果这个is_detail_check不是null，也就是是true，则应该判断答案检查已经完成，那么应该直接退出
    |-- 将标准答案和模型答案打包发送给模型，模型返回细节校正好的CoT
    |-- 如果校正完成，那么is_detail_check就设置为true
    |-- 将内容写回至碎片prob_12345678901234567890abc1_1.json内
    |-- 现在内容如下，假设模型已经检查好了：
{
    "problem_id": "prob_12345678901234567890abc1"
    "question_text": "xxxx"
    "standard_answer": "xxxx"
    "images": [
        "picture_1.jpg"
    ]
    "multi_solution_hint": ""
    也就是原内容的保留

    "method_id": 1，即对应的碎片管理器给出的编号
    "CoT": "模型的对应回复"
    "model_answer": "模型的对应回复"

    "is_answer_check": "true"

    "is_detail_check": "true"
    "detail_checked_CoT": "模型返回的校正过的CoT"

    "is_answer_unique_check": "null", 
}
|-- 进入解法重复判断器
    |-- 根据先前的碎片记录号读取刚刚保存好的碎片
    |-- 根据参数allow_answer_unique_check = false判断不应该进行重复解法检查
    |-- 直接退出
    

具体案例2:
layer_problem
|-- problem_set
    |-- certain_problem.json

layer_CoT
|-- problem_set
    |-- prob_12345678901234567890abc1_1.json
    |-- prob_12345678901234567890abc1_2.json

customed_folder
|-- picture_1.jpg
|-- picture_2.png

layer_problem/problem_set/certain_problem.json内容如下：
"problems": [
    {
        "problem_id": "prob_12345678901234567890abc1"
        "question_text": "xxxx"
        "standard_answer": "xxxx"
        "images": [
            "picture_1.jpg"
        ]
        "multi_solution_hint": "某个描述"
    }
]

layer_CoT/problem_set/prob_12345678901234567890abc1_1.json的内容如下：
{
    "problem_id": "prob_12345678901234567890abc1"
    "question_text": "xxxx"
    "standard_answer": "xxxx"
    "images": [
        "picture_1.jpg"
    ]
    "multi_solution_hint": "某个描述"

    "method_id": 1，即对应的碎片管理器给出的编号
    "CoT": "模型的对应回复"
    "model_answer": "模型的对应回复"

    "is_answer_check": "true"

    "is_detail_check": "true"
    "detail_checked_CoT": "模型返回的校正过的CoT"

    "is_answer_unique_check": "true", 
}

layer_CoT/problem_set/prob_12345678901234567890abc1_2.json的内容如下：
{
    "problem_id": "prob_12345678901234567890abc1"
    "question_text": "xxxx"
    "standard_answer": "xxxx"
    "images": [
        "picture_1.jpg"
    ]
    "multi_solution_hint": "某个描述"

    "method_id": 2
    "CoT": "模型的对应回复"
    "model_answer": "模型的对应回复"

    "is_answer_check": "true"

    "is_detail_check": "true"
    "detail_checked_CoT": "模型返回的校正过的CoT"

    "is_answer_unique_check": "false", 
}

参数为：
folder_name = problem_set
allow_send_standard_answer = false
allow_send_other_answer = false
allow_multiple_answer = true
allow_answer_check = true
answer_check_mode = "LLM"
allow_detail_check = true
allow_answer_unique_check = true
picture_path = customed_folder


流程描述：
layer_problem里面读入problem_set，检查里面存在唯一的json problem_set.json；
layer_CoT检查有没有文件夹名为problem_set，有，则调用检查器进行检查。
检查器阅读layer_problem内的problem_set，得到原始任务id，阅读layer_CoT内的problem_set，根据先前的格式<problem_id>_<method_id>获取碎片任务并读取，最后得到两个任务池：
这里是读取prob_12345678901234567890abc1_1.json和prob_12345678901234567890abc1_2.json
检查器得到两个任务池：
|-- 碎片任务池：(任务id, 解法id, 是否完成)这样的元组的集合，其中根据参数allow_answer_check = true，allow_detail_check = true，allow_answer_unique_check = true，来判断layer_CoT内的problem_set内的每个解法碎片是否被完成。
    |-- 最后得到的碎片任务池为{(prob_12345678901234567890abc1, 1, true), (prob_12345678901234567890abc1, 2, false)}
|-- 原始任务池: (原始任务id, 对应的multi_solution_hint, 已有解法数量)的集合，其中已有解法数量这一项可以从碎片任务池里面获取相关信息。里面这有("prob_12345678901234567890abc1", "某个描述", 1)
任务调度器根据已有的两个任务池，先使用多解判断器
|-- 多解判断器对已有的两个任务池进行探查
|-- 多解判断器对("prob_12345678901234567890abc1", "某个描述", 1)，由于参数allow_multiple_answer = true，则需要根据对应的multi_solution_hint字段内容进行判断，给出对应的需要的解法数量。
|-- 多解判断器内部有一个组件，根据输入"某个描述"，返回需要的多解数量，这里还没有确定好，先假定为3。
|-- 最后得到需要解法数量为3，已有解法数量1，因此对这个问题，"prob_12345678901234567890abc1"应该被执行，会被加进执行任务池里面
|-- 多解判断器最后给出执行任务池，里面有"prob_12345678901234567890abc1"
任务调度器根据执行任务池，调用多线程进行任务分发。
接下来跟踪一个任务"prob_12345678901234567890abc1"
|-- 进入碎片管理器
    |-- 先去碎片任务池里面找是否有未完成的碎片任务，发现有(prob_12345678901234567890abc1, 2, false)未完成
    |-- 产生碎片记录号，也就是<problem_id>, <method_id>的形式，碎片会在下一步被创建
    |-- 去碎片任务池里面找是否有未完成的碎片任务而发现有一个，因此不会创建新的碎片，则直接返回这个碎片对应的碎片记录号，可以直接从碎片任务池里面得知这个信息
    |-- 这里是(prob_12345678901234567890abc1, 2)未完成
    |-- 因此，碎片管理器会知道两个信息，一个是碎片记录号，一个是对应的当前碎片是否被被创建
|-- 碎片管理器返回(碎片记录号, 该碎片是否被创建)
|-- 这里是((prob_12345678901234567890abc1, 2), true)
|-- 进入CoT生成器，同时发送碎片记录号里面携带的method_id信息，以及该碎片是否被创建
    |-- 由于获取信息：该碎片已经被创建，所以CoT生成器会直接返回，不执行
|-- 接下来进入答案检查器
    |-- 根据先前的碎片记录号读取刚刚保存好的碎片
    |-- 根据参数allow_answer_check = true判断应该进行答案检查
    |-- 然后，根据参数is_answer_check是true，可以看出来答案检查这步还没有进行
        |-- 如果这个is_answer_check不是null，也就是是true或者false，则应该判断答案检查已经完成，那么应该直接退出
    |-- 由于参数answer_check_mode = "LLM"，将标准答案和模型答案打包发送给模型，模型返回两个答案是否匹配
        |-- 如果参数是"regular"，那么使用一个常规匹配器判断答案是否等效
    |-- 如果匹配，那么is_answer_check就设置为true，反之设置为false
    |-- 将内容写回至碎片prob_12345678901234567890abc1_1.json内
    |-- 现在内容如下，假设模型认为答案匹配：
{
    "problem_id": "prob_12345678901234567890abc1"
    "question_text": "xxxx"
    "standard_answer": "xxxx"
    "images": [
        "picture_1.jpg"
    ]
    "multi_solution_hint": ""
    也就是原内容的保留

    "method_id": 1，即对应的碎片管理器给出的编号
    "CoT": "模型的对应回复"
    "model_answer": "模型的对应回复"

    "is_answer_check": "true"

    "is_detail_check": "null"
    "detail_checked_CoT": ""

    "is_answer_unique_check": "null", 
}
|-- 进入细节验证器
    |-- 根据先前的碎片记录号读取刚刚保存好的碎片
    |-- 根据参数allow_detail_check = true判断应该进行细节检查
    |-- 然后，根据参数is_detail_check是null，可以看出来答案检查这步还没有进行
        |-- 如果这个is_detail_check不是null，也就是是true，则应该判断答案检查已经完成，那么应该直接退出
    |-- 将标准答案和模型答案打包发送给模型，模型返回细节校正好的CoT
    |-- 如果校正完成，那么is_detail_check就设置为true
    |-- 将内容写回至碎片prob_12345678901234567890abc1_1.json内
    |-- 现在内容如下，假设模型已经检查好了：
{
    "problem_id": "prob_12345678901234567890abc1"
    "question_text": "xxxx"
    "standard_answer": "xxxx"
    "images": [
        "picture_1.jpg"
    ]
    "multi_solution_hint": ""
    也就是原内容的保留

    "method_id": 1，即对应的碎片管理器给出的编号
    "CoT": "模型的对应回复"
    "model_answer": "模型的对应回复"

    "is_answer_check": "true"

    "is_detail_check": "true"
    "detail_checked_CoT": "模型返回的校正过的CoT"

    "is_answer_unique_check": "null", 
}
|-- 进入解法重复判断器
    |-- 根据先前的碎片记录号读取刚刚保存好的碎片
    |-- 根据参数allow_answer_unique_check = false判断不应该进行重复解法检查
    |-- 直接退出







----
这部分描述了Key_Claims_Generator的实现
----
输入形如
layer_CoT
|-- problem_set
    |-- prob_12345678901234567890abc1_1.json
    |-- prob_12345678901234567890abc1_2.json

prob_12345678901234567890abc1_1.json内部的内容形如
{
    "problem_id": "prob_12345678901234567890abc1"
    "question_text": "xxxx"
    "standard_answer": "xxxx"
    "images": [
        "picture_1.jpg"
    ]
    "multi_solution_hint": ""

    "method_id": 1，即对应的碎片管理器给出的编号
    "CoT": "模型的对应回复"
    "model_answer": "模型的对应回复"

    "is_answer_check": "true"

    "is_detail_check": "true"
    "detail_checked_CoT": "gemini模型校正过的CoT" | "", 注意，这一段可能为空

    "is_answer_unique_check": "true", 
}

输出形如
layer_Key_Claims
|-- problem_set
    |-- prob_12345678901234567890abc1_1.json
    |-- prob_12345678901234567890abc1_2.json

prob_12345678901234567890abc1_1.json内部的内容形如
{
    "problem_id": "prob_12345678901234567890abc1"
    "question_text": "xxxx"
    "standard_answer": "xxxx"
    "images": [
        "picture_1.jpg"
    ]
    "multi_solution_hint": ""

    "method_id": 1，即对应的碎片管理器给出的编号
    "CoT": "模型的对应回复"
    "model_answer": "模型的对应回复"

    "is_answer_check": "true"

    "is_detail_check": "true"
    "detail_checked_CoT": "gemini模型校正过的CoT" | "", 注意，这一段可能为空

    "is_answer_unique_check": "true", 
    上述内容直接保留即可，下面才是新增字段

    "key_claims": [
        {
            这里是每个key claims的内容
        },
        {
            这里是每个key claims的内容
        },
        {...},
        ...
    ]
}

补充说明：
实际上，设计上只关心文字的CoT到Key Claims的转化
注意，在上面的设计中，如果"is_detail_check": "true"的情况下，应该使用"detail_checked_CoT"里面的CoT内容
反之，使用"CoT"里面的CoT内容
key_claims的内部设计尚未确定
这里，每一个CoT层的problem_set里面的json都可以一一对应地保留名字地对应上key_claims层的json，所以命名处理可以直接照搬旧文件的名字



---
等待施工
---
待施工部分：
"is_have_key_claims": "true" | "false"
    "key_claims": {
        "claim_id": 指示了key_claims在method内部的编号
        "text": str, 具体内容
        "claim_type": 种类,
        "is_final_answer": 是否是最后答案
    },