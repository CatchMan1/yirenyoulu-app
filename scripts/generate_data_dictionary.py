"""Keep the public schema inventory consistent with the current ORM."""

import argparse
from pathlib import Path

from sqlalchemy.dialects import postgresql

from app.models import Base

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/技术开发/03数据库/数据字典.md"


def generate():
    lines = [
        "# 数据字典",
        "",
        f"当前 ORM 共 {len(Base.metadata.tables)} 张表。以下字段由模型生成；写入权限、输入校验和跨字段业务规则以 API 契约及服务层为准。",
        "",
        "UUID使用规范字符串存储，接口校验格式；金额使用整数分，时间戳使用UTC，行程日历与分钟使用城市时区。未知事实为NULL。普通Record表含id及创建/更新时间，关联表使用组合主键。",
        "",
    ]
    for table in Base.metadata.sorted_tables:
        lines += [
            "## " + table.name,
            "",
            "| 字段 | PostgreSQL 类型 | 可空 |",
            "|---|---|---|",
        ]
        for column in table.columns:
            kind = str(column.type.compile(dialect=postgresql.dialect()))
            lines.append(
                "| "
                + column.name
                + " | "
                + kind
                + " | "
                + ("是" if column.nullable else "否")
                + " |"
            )
        lines.append("")
    lines += [
        "## 关系与关键约束",
        "",
        "- 用户私有数据包括会话、收藏、行程、任务、聊天、行为及一次凭据；所有私有接口按当前用户限定归属。注销去除私有数据与个人资料，deletion_audits仅保存主体UUID用于恢复后的删除重放。",
        "- 地点统一place_id；来源和稳定external_id唯一关联；坐标完整并携带CRS。来源许可和图片展示权限分别控制。",
        "- 行程地点持久保存事实快照；原地点更新不改已保存事实。替换地点才重取快照；普通失效保留快照，来源撤回时隐藏，存储权限撤回时按来源清理事实快照。",
        "- 住宿起止分钟均NULL，每晚一项；其他活动分钟完整、合法且不冲突。数据库唯一键阻止同日重复地点，跨字段与预算由共享验证器检查。",
        "- 手动创建使用幂等摘要与过期标记；任务通过唯一generation_job_id连接结果行程，状态成功与结果保存原子提交，删除结果保留result_deleted。",
        "- 聊天按会话/序号、会话/message_id/角色唯一；重试复用原槽位，provider_mode持久区分模拟和真实来源。",
        "- 推荐批处理发布不含用户ID的地点相似度；每城市独立发布，模型有样本计数和有效期，注销或来源许可变更使现有模型立即失效。测试来源与测试行为不进入训练。",
        "- 来源政策默认拒绝，记录字段白名单、计算授权、版本与有效期；批次需城市/数量/请求预算和独立审核。每条地点提交与游标原子推进，可恢复失败。字段来源记录缺失原因和价格条件。",
        "- api_throttles保存HMAC摘要、窗口和计数；不记录原始IP。恢复令牌与刷新凭据仅存摘要，原文不得写入日志。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = generate()
    if args.check:
        if OUTPUT.read_text() != content:
            raise SystemExit("Data dictionary differs from ORM")
    else:
        OUTPUT.write_text(content)
