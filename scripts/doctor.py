"""卡咔 本地自检工具。

这个脚本会检查配置字段、项目内导入、数据库路径和常用端口。
它不会打印 `.env` 里的密钥值。

PyCharm 右键运行即可，不需要配置 Parameters。

这个脚本目前没有筛选关键词，直接运行会检查：

- 项目目录和关键文件。
- Python 版本和是否使用项目 `.venv`。
- `.env` / `.env.example` / `.gitignore`。
- LLM、数据库和 qq-adapter 的配置字段形状。
- SQLite 表结构、废弃字段、字段顺序、记忆候选表和正式记忆表。
- 自动后台任务运行记录表。
- 自动候选区复核配置、回复时长期记忆注入配置、人设 Prompt 配置和关系上下文配置。
- 本地 Web 管理台访问保护配置。
- 项目内关键模块是否能导入。
- 8001 / 8081 / 8000 端口状态。

如果 `kaka-core` 或 `qq-adapter` 没有启动，端口检查出现 WARN 是正常的。
"""

from __future__ import annotations

import importlib
import socket
import sqlite3
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CORE_URL = "http://127.0.0.1:8001"
EXPECTED_NAPCAT_WS = "ws://127.0.0.1:8081/onebot/v11/ws"
EXPECTED_INPUT_COLUMNS = [
    "id",
    "event_id",
    "user_id",
    "scene_id",
    "content_type",
    "content_text",
    "raw_event",
    "metadata",
    "analysis_status",
    "created_at",
]
EXPECTED_OUTPUT_COLUMNS = [
    "id",
    "output_id",
    "input_id",
    "scene_id",
    "user_id",
    "output_origin",
    "output_reason",
    "should_reply",
    "no_reply_reason",
    "content_text",
    "metadata",
    "created_at",
]
EXPECTED_MEMORY_CANDIDATE_COLUMNS = [
    "id",
    "source_input_id",
    "source_user_id",
    "source_scene_id",
    "source_text",
    "candidate_memory",
    "memory_type",
    "confidence",
    "reason",
    "analysis_model",
    "analysis_prompt_version",
    "status",
    "created_at",
    "updated_at",
]
EXPECTED_MEMORY_COLUMNS = [
    "id",
    "source_candidate_id",
    "user_id",
    "scene_id",
    "memory_text",
    "normalized_text",
    "memory_type",
    "confidence",
    "source_text",
    "source",
    "status",
    "merge_reason",
    "created_at",
    "updated_at",
]
EXPECTED_AUTO_JOB_RUN_COLUMNS = [
    "id",
    "job_name",
    "status",
    "reason",
    "checked_count",
    "processed_runs",
    "inserted_count",
    "updated_count",
    "skipped_count",
    "error_count",
    "error_message",
    "metadata",
    "started_at",
    "finished_at",
    "created_at",
]


@dataclass(frozen=True)
class CheckResult:
    level: str
    title: str
    detail: str


def add(results: list[CheckResult], level: str, title: str, detail: str) -> None:
    results.append(CheckResult(level, title, detail))


def ok(results: list[CheckResult], title: str, detail: str) -> None:
    add(results, "OK", title, detail)


def warn(results: list[CheckResult], title: str, detail: str) -> None:
    add(results, "WARN", title, detail)


def fail(results: list[CheckResult], title: str, detail: str) -> None:
    add(results, "FAIL", title, detail)


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def check_project_layout(results: list[CheckResult]) -> None:
    ok(results, "项目目录", str(ROOT))

    required_paths = [
        ROOT / "packages" / "kaka-protocol",
        ROOT / "services" / "kaka-core",
        ROOT / "apps" / "qq-adapter",
        ROOT / "prompts" / "kaka_persona.md",
        ROOT / "docs" / "运行手册.md",
        ROOT / "services" / "kaka-core" / "run.py",
        ROOT / "apps" / "qq-adapter" / "bot.py",
    ]
    for path in required_paths:
        if path.exists():
            ok(results, f"存在 {path.relative_to(ROOT)}", "已找到")
        else:
            fail(results, f"缺少 {path.relative_to(ROOT)}", "必需的项目文件不存在")


def check_python(results: list[CheckResult]) -> None:
    version = sys.version_info
    if version >= (3, 12):
        ok(results, "Python 版本", f"{version.major}.{version.minor}.{version.micro}")
    else:
        fail(results, "Python 版本", f"需要 >= 3.12，当前是 {version.major}.{version.minor}.{version.micro}")

    expected_venv = (ROOT / ".venv").resolve()
    executable = Path(sys.executable).resolve()
    try:
        executable.relative_to(expected_venv)
        ok(results, "Python 解释器", str(executable))
    except ValueError:
        warn(
            results,
            "Python 解释器",
            f"当前不是项目 .venv: {executable}",
        )


def check_env_template(results: list[CheckResult]) -> None:
    env_example = ROOT / ".env.example"
    if env_example.exists():
        ok(results, ".env.example", "配置模板存在")
    else:
        fail(results, ".env.example", "配置模板不存在")

    gitignore = ROOT / ".gitignore"
    if not gitignore.exists():
        warn(results, ".gitignore", "未找到 .gitignore")
        return

    text = gitignore.read_text(encoding="utf-8")
    if ".env" in text and "!.env.example" in text:
        ok(results, ".gitignore", ".env 会被忽略，.env.example 可被保留")
    elif ".env" in text:
        warn(results, ".gitignore", ".env 已忽略，但 .env.example 可能也会被忽略")
    else:
        fail(results, ".gitignore", ".env 未被忽略，可能泄露密钥")


def check_env_file(results: list[CheckResult]) -> dict[str, str]:
    env_path = ROOT / ".env"
    if not env_path.exists():
        fail(results, ".env", "未找到 .env；复制 .env.example 后填写本地配置")
        return {}

    ok(results, ".env", "存在；只检查字段，不打印任何密钥")
    values = parse_env_file(env_path)

    llm_enabled = values.get("LLM_ENABLED")
    if llm_enabled is None:
        warn(results, "LLM_ENABLED", "未设置，将按默认 false 处理")
    elif is_truthy(llm_enabled):
        ok(results, "LLM_ENABLED", "true")
    else:
        warn(results, "LLM_ENABLED", "不是 true，kaka-core 将不会调用远程模型")

    api_key = values.get("LLM_API_KEY", "")
    if is_truthy(llm_enabled) and not api_key:
        fail(results, "LLM_API_KEY", "LLM_ENABLED=true 时必须设置 API Key")
    elif api_key:
        ok(results, "LLM_API_KEY", "已设置，值已隐藏")
    else:
        warn(results, "LLM_API_KEY", "未设置；只能使用 fallback 回复")

    check_url_value(results, "LLM_BASE_URL", values.get("LLM_BASE_URL", "https://api.deepseek.com"))
    check_non_empty(results, "LLM_CHAT_MODEL", values.get("LLM_CHAT_MODEL", "deepseek-v4-flash"))
    check_float_value(results, "LLM_TEMPERATURE", values.get("LLM_TEMPERATURE", "0.7"))
    check_int_value(results, "LLM_MAX_TOKENS", values.get("LLM_MAX_TOKENS", "800"))
    check_bool_value(
        results,
        "MEMORY_AUTO_ANALYSIS_ENABLED",
        values.get("MEMORY_AUTO_ANALYSIS_ENABLED", "false"),
    )
    check_int_value(
        results,
        "MEMORY_AUTO_ANALYSIS_TRIGGER_COUNT",
        values.get("MEMORY_AUTO_ANALYSIS_TRIGGER_COUNT", "50"),
    )
    check_int_value(
        results,
        "MEMORY_AUTO_ANALYSIS_BATCH_LIMIT",
        values.get("MEMORY_AUTO_ANALYSIS_BATCH_LIMIT", "50"),
    )
    check_int_value(
        results,
        "MEMORY_AUTO_ANALYSIS_MAX_RUNS_PER_CHECK",
        values.get("MEMORY_AUTO_ANALYSIS_MAX_RUNS_PER_CHECK", "2"),
    )
    check_non_negative_int_value(
        results,
        "MEMORY_AUTO_ANALYSIS_INTERVAL_SECONDS",
        values.get("MEMORY_AUTO_ANALYSIS_INTERVAL_SECONDS", "0"),
    )
    check_bool_value(
        results,
        "MEMORY_AUTO_REVIEW_ENABLED",
        values.get("MEMORY_AUTO_REVIEW_ENABLED", "false"),
    )
    check_int_value(
        results,
        "MEMORY_AUTO_REVIEW_TRIGGER_COUNT",
        values.get("MEMORY_AUTO_REVIEW_TRIGGER_COUNT", "20"),
    )
    check_int_value(
        results,
        "MEMORY_AUTO_REVIEW_BATCH_SIZE",
        values.get("MEMORY_AUTO_REVIEW_BATCH_SIZE", "10"),
    )
    check_int_value(
        results,
        "MEMORY_AUTO_REVIEW_MAX_RUNS_PER_CHECK",
        values.get("MEMORY_AUTO_REVIEW_MAX_RUNS_PER_CHECK", "1"),
    )
    check_bool_value(
        results,
        "MEMORY_REPLY_INJECTION_ENABLED",
        values.get("MEMORY_REPLY_INJECTION_ENABLED", "true"),
    )
    check_int_value(results, "MEMORY_REPLY_LIMIT", values.get("MEMORY_REPLY_LIMIT", "5"))
    check_non_negative_float_value(
        results,
        "MEMORY_REPLY_MIN_SCORE",
        values.get("MEMORY_REPLY_MIN_SCORE", "1.0"),
    )
    check_int_value(
        results,
        "MEMORY_REPLY_POOL_SIZE",
        values.get("MEMORY_REPLY_POOL_SIZE", "300"),
    )
    check_persona_prompt_path(
        results,
        values.get("KAKA_PERSONA_PROMPT_PATH", str(ROOT / "prompts" / "kaka_persona.md")),
    )
    owner_ids = values.get("KAKA_OWNER_USER_IDS", "").strip()
    if owner_ids:
        ok(results, "KAKA_OWNER_USER_IDS", "已设置，值已隐藏")
    else:
        warn(results, "KAKA_OWNER_USER_IDS", "未设置；特殊用户关系会按普通用户判断")
    admin_local_only = values.get("ADMIN_LOCAL_ONLY", "true")
    check_bool_value(results, "ADMIN_LOCAL_ONLY", admin_local_only)
    admin_token = values.get("ADMIN_API_TOKEN", "")
    if is_truthy(admin_local_only):
        if admin_token:
            ok(results, "ADMIN_API_TOKEN", "已设置，值已隐藏")
        else:
            warn(results, "ADMIN_API_TOKEN", "未设置；当前仅本机管理台可访问")
    elif admin_token:
        ok(results, "ADMIN_API_TOKEN", "已设置，值已隐藏")
    else:
        fail(results, "ADMIN_API_TOKEN", "ADMIN_LOCAL_ONLY=false 时必须设置")

    core_url = values.get("KAKA_CORE_BASE_URL", EXPECTED_CORE_URL).rstrip("/")
    if core_url == EXPECTED_CORE_URL:
        ok(results, "KAKA_CORE_BASE_URL", core_url)
    elif ":8000" in core_url:
        fail(results, "KAKA_CORE_BASE_URL", f"仍指向旧端口: {core_url}")
    else:
        warn(results, "KAKA_CORE_BASE_URL", f"不是当前推荐值: {core_url}")

    check_float_value(
        results,
        "QQ_ADAPTER_REQUEST_TIMEOUT",
        values.get("QQ_ADAPTER_REQUEST_TIMEOUT", "60"),
    )
    check_database_url(results, values.get("DATABASE_URL"))

    return values


def check_url_value(results: list[CheckResult], name: str, value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        ok(results, name, value)
    else:
        fail(results, name, f"URL 格式不正确: {value}")


def check_non_empty(results: list[CheckResult], name: str, value: str) -> None:
    if str(value or "").strip():
        ok(results, name, "已设置")
    else:
        fail(results, name, "不能为空")


def check_bool_value(results: list[CheckResult], name: str, value: str) -> None:
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
        ok(results, name, normalized)
    else:
        fail(results, name, f"不是有效布尔值: {value}")


def check_float_value(results: list[CheckResult], name: str, value: str) -> None:
    try:
        number = float(value)
    except ValueError:
        fail(results, name, f"不是有效数字: {value}")
        return
    if number > 0:
        ok(results, name, str(number))
    else:
        fail(results, name, "必须大于 0")


def check_non_negative_float_value(results: list[CheckResult], name: str, value: str) -> None:
    try:
        number = float(value)
    except ValueError:
        fail(results, name, f"不是有效数字: {value}")
        return
    if number >= 0:
        ok(results, name, str(number))
    else:
        fail(results, name, "必须大于等于 0")


def check_int_value(results: list[CheckResult], name: str, value: str) -> None:
    try:
        number = int(value)
    except ValueError:
        fail(results, name, f"不是有效整数: {value}")
        return
    if number > 0:
        ok(results, name, str(number))
    else:
        fail(results, name, "必须大于 0")


def check_non_negative_int_value(results: list[CheckResult], name: str, value: str) -> None:
    try:
        number = int(value)
    except ValueError:
        fail(results, name, f"不是有效整数: {value}")
        return
    if number >= 0:
        ok(results, name, str(number))
    else:
        fail(results, name, "必须大于等于 0")


def check_database_url(results: list[CheckResult], database_url: str | None) -> None:
    if not database_url:
        database_url = f"sqlite:///{ROOT / 'data' / 'kaka.sqlite3'}"
        ok(results, "DATABASE_URL", f"未设置，将使用默认值: {database_url}")
    else:
        ok(results, "DATABASE_URL", "已设置")

    if not database_url.startswith("sqlite:///"):
        warn(results, "DATABASE_URL", "当前 doctor 只深入检查 SQLite 路径")
        return

    raw_path = database_url.removeprefix("sqlite:///")
    db_path = Path(raw_path)
    if not db_path.is_absolute():
        db_path = ROOT / db_path

    parent = db_path.parent
    if not parent.exists():
        warn(results, "数据库目录", f"目录不存在，kaka-core 启动时会尝试创建: {parent}")
        return

    if is_directory_writable(parent):
        ok(results, "数据库目录", f"可写: {parent}")
    else:
        fail(results, "数据库目录", f"不可写: {parent}")
        return

    if db_path.exists():
        check_sqlite_schema(results, db_path)
    else:
        warn(results, "SQLite 文件", f"尚不存在，kaka-core 启动时会创建: {db_path}")


def check_persona_prompt_path(results: list[CheckResult], value: str) -> None:
    raw_path = str(value or "").strip()
    if not raw_path:
        fail(results, "KAKA_PERSONA_PROMPT_PATH", "不能为空")
        return

    prompt_path = Path(raw_path)
    if not prompt_path.is_absolute():
        prompt_path = ROOT / prompt_path

    if not prompt_path.exists():
        warn(
            results,
            "KAKA_PERSONA_PROMPT_PATH",
            f"文件不存在，将回退到内置基础人设: {prompt_path}",
        )
        return

    if not prompt_path.is_file():
        fail(results, "KAKA_PERSONA_PROMPT_PATH", f"不是文件: {prompt_path}")
        return

    try:
        content = prompt_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        fail(results, "KAKA_PERSONA_PROMPT_PATH", f"无法读取: {exc}")
        return

    if content:
        ok(results, "KAKA_PERSONA_PROMPT_PATH", f"可读取: {prompt_path}")
    else:
        warn(results, "KAKA_PERSONA_PROMPT_PATH", f"文件为空，将回退到内置基础人设: {prompt_path}")


def is_directory_writable(path: Path) -> bool:
    probe = path / ".doctor_write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def check_sqlite_schema(results: list[CheckResult], db_path: Path) -> None:
    required_tables = {"users", "scenes", "inputs", "outputs"}
    required_input_columns = {"analysis_status"}
    deprecated_input_columns = {"is_processed", "process_reason"}
    required_output_columns = {
        "input_id",
        "scene_id",
        "user_id",
        "output_origin",
        "output_reason",
        "no_reply_reason",
    }
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            input_columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(inputs)").fetchall()
            }
            ordered_input_columns = [
                str(row[1])
                for row in conn.execute("PRAGMA table_info(inputs)").fetchall()
            ]
            output_columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(outputs)").fetchall()
            }
            ordered_output_columns = [
                str(row[1])
                for row in conn.execute("PRAGMA table_info(outputs)").fetchall()
            ]
            ordered_candidate_columns = [
                str(row[1])
                for row in conn.execute("PRAGMA table_info(memory_candidates)").fetchall()
            ]
            ordered_memory_columns = [
                str(row[1])
                for row in conn.execute("PRAGMA table_info(memories)").fetchall()
            ]
            ordered_auto_job_run_columns = [
                str(row[1])
                for row in conn.execute("PRAGMA table_info(auto_job_runs)").fetchall()
            ]
    except sqlite3.Error as exc:
        fail(results, "SQLite 文件", f"无法打开: {exc}")
        return

    table_names = {str(row[0]) for row in rows}
    missing = sorted(required_tables - table_names)
    if missing:
        fail(results, "SQLite 表结构", f"缺少表: {', '.join(missing)}")
    else:
        ok(results, "SQLite 表结构", "users / scenes / inputs / outputs 存在")

    if "memory_candidates" in table_names:
        ok(results, "memory_candidates 表", "存在")
    else:
        warn(
            results,
            "memory_candidates 表",
            "尚不存在；启动 kaka-core 或运行分析脚本初始化数据库后会自动创建",
        )

    if "memories" in table_names:
        ok(results, "memories 表", "存在")
    else:
        warn(
            results,
            "memories 表",
            "尚不存在；启动 kaka-core 或运行合并脚本初始化数据库后会自动创建",
        )

    if "auto_job_runs" in table_names:
        ok(results, "auto_job_runs 表", "存在")
    else:
        warn(
            results,
            "auto_job_runs 表",
            "尚不存在；启动 kaka-core 初始化数据库后会自动创建",
        )

    if "inputs" not in table_names:
        return

    missing_columns = sorted(required_input_columns - input_columns)
    if missing_columns:
        warn(
            results,
            "inputs 分析字段",
            f"缺少字段: {', '.join(missing_columns)}；启动 kaka-core 后会自动补齐",
        )
    else:
        ok(results, "inputs 分析字段", "analysis_status 存在")

    deprecated_columns = sorted(deprecated_input_columns & input_columns)
    if deprecated_columns:
        fail(
            results,
            "inputs 废弃字段",
            f"仍存在字段: {', '.join(deprecated_columns)}；需要运行数据库迁移整理",
        )
    else:
        ok(results, "inputs 废弃字段", "is_processed / process_reason 已删除")

    if ordered_input_columns == EXPECTED_INPUT_COLUMNS:
        ok(results, "inputs 字段顺序", "符合当前模型")
    else:
        warn(
            results,
            "inputs 字段顺序",
            "当前顺序与模型不一致；启动 kaka-core 后会自动整理",
        )

    if "outputs" not in table_names:
        return

    missing_output_columns = sorted(required_output_columns - output_columns)
    if missing_output_columns:
        warn(
            results,
            "outputs 决策字段",
            f"缺少字段: {', '.join(missing_output_columns)}；启动 kaka-core 后会自动补齐",
        )
    else:
        ok(results, "outputs 决策字段", "input_id / scene_id / user_id / output_origin / output_reason / no_reply_reason 存在")

    if ordered_output_columns == EXPECTED_OUTPUT_COLUMNS:
        ok(results, "outputs 字段顺序", "符合当前模型")
    else:
        warn(
            results,
            "outputs 字段顺序",
            "当前顺序与模型不一致；启动 kaka-core 后会自动整理",
        )

    if "memory_candidates" not in table_names:
        return

    if ordered_candidate_columns == EXPECTED_MEMORY_CANDIDATE_COLUMNS:
        ok(results, "memory_candidates 字段顺序", "符合当前模型")
    else:
        warn(
            results,
            "memory_candidates 字段顺序",
            "当前顺序与模型不一致；启动 kaka-core 后会自动补齐或创建新库",
        )

    if "memories" not in table_names:
        return

    if ordered_memory_columns == EXPECTED_MEMORY_COLUMNS:
        ok(results, "memories 字段顺序", "符合当前模型")
    else:
        warn(
            results,
            "memories 字段顺序",
            "当前顺序与模型不一致；启动 kaka-core 后会自动整理",
        )

    if "auto_job_runs" not in table_names:
        return

    if ordered_auto_job_run_columns == EXPECTED_AUTO_JOB_RUN_COLUMNS:
        ok(results, "auto_job_runs 字段顺序", "符合当前模型")
    else:
        warn(
            results,
            "auto_job_runs 字段顺序",
            "当前顺序与模型不一致；启动 kaka-core 后会自动整理",
        )


def check_imports(results: list[CheckResult]) -> None:
    src_paths = [
        ROOT / "packages" / "kaka-protocol" / "src",
        ROOT / "services" / "kaka-core" / "src",
        ROOT / "apps" / "qq-adapter" / "src",
    ]
    for path in reversed(src_paths):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)

    modules = [
        ("kaka_protocol", "kaka-protocol"),
        ("kaka_core.config.settings", "kaka-core"),
        ("kaka_core.relationship.context", "kaka-core relationship"),
        ("qq_adapter.config", "qq-adapter"),
        ("fastapi", "FastAPI"),
        ("httpx", "httpx"),
        ("sqlalchemy", "SQLAlchemy"),
        ("nonebot", "NoneBot2"),
        ("nonebot.adapters.onebot.v11", "OneBot V11 adapter"),
    ]
    for module_name, label in modules:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            fail(results, f"导入 {label}", str(exc))
        else:
            ok(results, f"导入 {label}", "正常")


def check_ports(results: list[CheckResult]) -> None:
    if is_port_open("127.0.0.1", 8001):
        ok(results, "端口 8001", "kaka-core 可能正在运行")
        check_core_health(results)
    else:
        warn(results, "端口 8001", "当前未监听；如果还没启动 kaka-core，这是正常的")

    if is_port_open("127.0.0.1", 8081):
        ok(results, "端口 8081", "qq-adapter / NoneBot2 可能正在运行")
    else:
        warn(results, "端口 8081", "当前未监听；如果还没启动 qq-adapter，这是正常的")

    if is_port_open("127.0.0.1", 8000):
        warn(results, "端口 8000", "旧端口正在监听，确认 .env 不要指向 8000")
    else:
        ok(results, "端口 8000", "未监听")

    ok(results, "NapCat 反向 WS 推荐地址", EXPECTED_NAPCAT_WS)


def is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def check_core_health(results: list[CheckResult]) -> None:
    try:
        with urllib.request.urlopen(f"{EXPECTED_CORE_URL}/health", timeout=1) as response:
            status = response.status
    except (OSError, urllib.error.URLError) as exc:
        warn(results, "kaka-core /health", f"端口可连，但 health 请求失败: {exc}")
        return

    if status == 200:
        ok(results, "kaka-core /health", "HTTP 200")
    else:
        warn(results, "kaka-core /health", f"HTTP {status}")


def print_results(results: list[CheckResult]) -> None:
    print("卡咔 本地自检")
    print("=" * 60)
    for result in results:
        print(f"[{result.level}] {result.title}: {result.detail}")
    print("=" * 60)

    fail_count = sum(1 for item in results if item.level == "FAIL")
    warn_count = sum(1 for item in results if item.level == "WARN")
    ok_count = sum(1 for item in results if item.level == "OK")
    print(f"汇总: {ok_count} OK, {warn_count} WARN, {fail_count} FAIL")


def main() -> int:
    results: list[CheckResult] = []
    check_project_layout(results)
    check_python(results)
    check_env_template(results)
    check_env_file(results)
    check_imports(results)
    check_ports(results)
    print_results(results)
    return 1 if any(item.level == "FAIL" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
