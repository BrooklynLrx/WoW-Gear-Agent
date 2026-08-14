# 数据库与迁移

应用使用本机 MySQL `wow_builder`，连接参数只保存在根目录 `.env`。应用与 Alembic 都使用受限账号 `wow_app`，不要在代码中使用 MySQL `root`。

## 常用命令

```bash
# 查看当前版本
alembic current

# 修改 backend/models.py 后生成迁移
alembic revision --autogenerate -m "describe change"

# 必须人工检查新生成的 upgrade/downgrade，再执行
alembic upgrade head

# 回退一个版本
alembic downgrade -1

# 检查模型是否存在遗漏的迁移
alembic check
```

## 约束

- 禁止使用 `Base.metadata.create_all()` 管理正式结构。
- 禁止直接在 MySQL 中手工改表。
- 每次模型变更必须提交对应的 Alembic 迁移。
- 数据导入脚本只写业务数据，不负责建表。
- 执行迁移前先备份；MySQL DDL 不保证事务回滚。

初始迁移同时包含游戏目录、用户、角色、配装、手动宝石、消耗品和配装对话表。
