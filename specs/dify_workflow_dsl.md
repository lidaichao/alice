# Dify 工作流 DSL YAML 格式（参考存档）

> ⚠️ [DEPRECATED v3.0] Alice v3.0 不采用 Dify 工作流做 AI 编排——AI 编排层改用 LangGraph（Python）。
> Dify 在 v3.0 中仅用于知识库 RAG，其 REST API 见 `specs/dify_api.md`。
> 保留此文件仅供格式参考（如未来需要了解 Dify 工作流 YAML 结构时查阅）。
>
> 来源：https://github.com/langgenius/dify · Apache 2.0 开源
> 原用途：杰尼龟编写 Dify 工作流 YAML 文件（不再使用）

---

## 一、DSL 顶层结构

```yaml
kind: app
version: 0.6.0           # 当前版本
app:
  name: Alice 对话工作流
  description: 意图识别 → 知识库检索 → 生成回复
  icon: 🐰
  icon_background: '#E9F2FF'
  mode: workflow          # workflow（单轮）/ advanced-chat（多轮）
  model_config: {}        # 默认模型配置（可选）
workflow:
  conversation_variables: []
  environment_variables: []
  features:               # UI 特性
    file_upload:
      enabled: false
    opening_statement: ''
    retriever_resource:
      enabled: false
    sensitive_word_avoidance:
      enabled: false
    speech_to_text:
      enabled: false
    suggested_questions: []
    suggested_questions_after_answer:
      enabled: false
    text_to_speech:
      enabled: false
  graph:
    nodes: []             # 节点数组
    edges: []             # 连线数组
```

---

## 二、节点定义（通用格式）

每个节点必须是以下结构：

```yaml
nodes:
  - id: '1732007415808'       # 唯一字符串 ID（建议时间戳）
    type: custom              # 固定值 "custom"
    data:
      type: start             # 实际节点类型（见 §三）
      title: 开始
      desc: ''                # 可选描述
      selected: false
      # 节点类型特定配置...
    position:
      x: 100.5
      y: 200.0
    positionAbsolute:
      x: 100.5
      y: 200.0
    width: 244
    height: 90
    selected: false
    sourcePosition: right     # 输出端位置
    targetPosition: left      # 输入端位置
```

---

## 三、常用节点类型

### 3.1 Start 节点

```yaml
data:
  type: start
  title: Start
  variables:
    - variable: user_query
      label: 用户输入
      type: paragraph
      required: true
      max_length: 2000
    - variable: user_id
      label: 用户 ID
      type: text-input
      required: false
```

### 3.2 LLM 节点

```yaml
data:
  type: llm
  title: 生成回复
  model:
    provider: deepseek
    name: deepseek-chat
    mode: chat
    completion_params:
      temperature: 0.7
      max_tokens: 2000
  prompt_template:
    - role: system
      text: "你是一个研发助手。\n上下文：\n{{#1720000000002.text#}}"
    - role: user
      text: "{{#start.user_query#}}"
  memory: null
  variables: []
```

**变量引用语法：** `{{#node_id.field_name#}}`

### 3.3 Knowledge Retrieval 节点

```yaml
data:
  type: knowledge-retrieval
  title: 知识库检索
  query_variable_selector:
    - 'start'
    - 'user_query'
  dataset_ids:
    - 'dataset-uuid-here'
  retrieval_mode: multiple
  multiple_retrieval_config:
    top_k: 5
    score_threshold_enabled: false
    reranking_mode: null
```

### 3.4 Code 节点

```yaml
data:
  type: code
  title: 数据清洗
  code_language: python3
  code: |
    def main(input_text: str) -> str:
        # 在此处理数据
        return input_text.strip()[:1000]
  variables:
    - variable: input_text
      value_selector:
        - '1720000000001'
        - 'text'
```

### 3.5 HTTP Request 节点（调用 n8n Webhook）

```yaml
data:
  type: http-request
  title: 调用 n8n 查 Jira
  method: post
  url: 'http://n8n:5678/webhook/jira-search'
  authorization:
    type: no-auth
  headers: 'Content-Type: application/json'
  body:
    type: json
    data: '{"jql": "project=CT AND status=Open", "user_id": "{{#start.user_id#}}"}'
```

### 3.6 IF/ELSE 条件分支

```yaml
data:
  type: if-else
  title: 是否为操作类请求
  conditions:
    - comparison_operator: contains
      value: '创建'
      variable_selector:
        - 'start'
        - 'user_query'
```

### 3.7 End 节点

```yaml
data:
  type: end
  title: End
  outputs:
    - variable: result
      value_selector:
        - '1720000000002'
        - 'text'
```

---

## 四、边（Edges）定义

```yaml
edges:
  - id: 'edge-1'
    source: '1732007415808'       # 源节点 ID
    target: '1732007415809'       # 目标节点 ID
    sourceHandle: 'source'        # 固定值
    targetHandle: 'target'        # 固定值
    data:
      isInIteration: false
      sourceType: start           # 源节点 data.type
      targetType: llm             # 目标节点 data.type
```

**IF/ELSE 分支的边需要指定 `sourceHandle`：**

- `true` → 条件为真时走的分支
- `false` → 条件为假时走的分支

```yaml
edges:
  - id: 'edge-if-true'
    source: 'if-node-id'
    target: '操作节点'
    sourceHandle: 'true'
    targetHandle: 'target'
  - id: 'edge-if-false'
    source: 'if-node-id'
    target: '生成回复节点'
    sourceHandle: 'false'
    targetHandle: 'target'
```

---

## 五、Alice 工作流模板（意图识别 → 检索 → 生成）

```yaml
kind: app
version: 0.6.0
app:
  name: Alice 对话路由
  mode: workflow
workflow:
  graph:
    nodes:
      # 1. Start - 接收用户输入
      - id: 'start'
        type: custom
        data:
          type: start
          title: Start
          variables:
            - variable: user_query
              type: paragraph
              required: true
            - variable: user_id
              type: text-input
              required: false

      # 2. IF-ELSE - 意图路由
      - id: 'router'
        type: custom
        data:
          type: if-else
          title: 意图判断
          conditions:
            - comparison_operator: contains
              value: 'Jira'
              variable_selector: ['start', 'user_query']
            - comparison_operator: contains
              value: '创建'
              variable_selector: ['start', 'user_query']

      # 3. HTTP Request - 调 n8n 查 Jira（操作路径）
      - id: 'fetch-jira'
        type: custom
        data:
          type: http-request
          title: 从 n8n 拉取 Jira 数据
          method: post
          url: 'http://n8n:5678/webhook/alice-jira-search'
          body:
            type: json
            data: '{"query": "{{#start.user_query#}}"}'

      # 4. Knowledge Retrieval - 知识库检索（知识路径）
      - id: 'kb-search'
        type: custom
        data:
          type: knowledge-retrieval
          title: 知识库检索
          query_variable_selector: ['start', 'user_query']
          dataset_ids: ['alice-knowledge-base-uuid']
          multiple_retrieval_config:
            top_k: 5

      # 5. LLM - 生成回复
      - id: 'generate'
        type: custom
        data:
          type: llm
          title: 生成回复
          model:
            provider: deepseek
            name: deepseek-chat
            mode: chat
            completion_params:
              temperature: 0.7
          prompt_template:
            - role: system
              text: "你是一个研发助手。\n\n已知信息：\n{{#kb-search.text#}}\n\nJira 数据：\n{{#fetch-jira.body#}}"
            - role: user
              text: "{{#start.user_query#}}"

      # 6. End
      - id: 'end'
        type: custom
        data:
          type: end
          title: End
          outputs:
            - variable: reply
              value_selector: ['generate', 'text']

    edges:
      - { source: 'start',   target: 'router',     sourceHandle: 'source', targetHandle: 'target' }
      - { source: 'router',  target: 'fetch-jira',  sourceHandle: 'true',  targetHandle: 'target' }
      - { source: 'router',  target: 'kb-search',   sourceHandle: 'false', targetHandle: 'target' }
      - { source: 'fetch-jira', target: 'generate', sourceHandle: 'source', targetHandle: 'target' }
      - { source: 'kb-search',  target: 'generate', sourceHandle: 'source', targetHandle: 'target' }
      - { source: 'generate',   target: 'end',      sourceHandle: 'source', targetHandle: 'target' }
```

---

## 六、不可编造的规则

- `type` 永远是 `custom`——真正的节点类型在 `data.type`
- 节点 `id` 必须是字符串，不重复
- 变量引用格式：`{{#node_id.field#}}`
- `value_selector` 是数组：`["node_id", "field_name"]`
- `edges` 里 `source` 和 `target` 必须是已存在的节点 `id`
- 工作流导入 Dify 后需要在 UI 上配置知识库 ID、API Key 等具体参数
