# Builder API

启动：

```bash
PYTHONPATH=. uvicorn backend.main:app --reload --port 8008
```

接口文档：<http://127.0.0.1:8008/docs>

基本流程：

```text
POST /api/v1/builder/sessions
  → POST /api/v1/builder/sessions/{session_id}/messages/stream
  → 前端读取 proposal.solutions[0].equipment
  → PATCH /api/v1/builder/sessions/{session_id} 应用或手动修改装备
```

创建会话：

```json
{"spec":"paladin.holy"}
```

对话：

```json
{"message":"面板急速约30%、暴击约20%、全能约15%，精通尽量低，生成完整配装"}
```

`/messages/stream` 返回 SSE：状态和文字可实时展示，`proposal` 仍作为一个完整
JSON 事件返回。原 `/messages` 非流式接口继续保留。

共享方案流程：

```text
POST /api/v1/loadouts                         保存或另存为
PATCH /api/v1/loadouts/{id}                  重命名或用当前 Builder 覆盖
POST /api/v1/loadouts/{id}/open              恢复到新 Builder 会话
DELETE /api/v1/loadouts/{id}                 删除
```

保存时提交 `name`、`creator_name` 和 `builder_session_id`。当前不做注册登录，
创建人只作为可信小团队的展示与筛选字段；任何访问者都能修改或删除方案。

会话目前保存在进程内存中，服务重启后清空。用户登录与配装保存接入后再迁移到 MySQL。
