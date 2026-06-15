import json
from pathlib import Path


WORKFLOW_PATH = Path(__file__).resolve().parents[1] / "n8n" / "github_weekly_stars.workflow.json"


def load_workflow() -> dict:
    return json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))


def node_by_name(workflow: dict, name: str) -> dict:
    nodes = {node["name"]: node for node in workflow["nodes"]}
    assert name in nodes
    return nodes[name]


def all_code(workflow: dict) -> str:
    snippets: list[str] = []
    for node in workflow["nodes"]:
        code = node.get("parameters", {}).get("jsCode")
        if isinstance(code, str):
            snippets.append(code)
    return "\n".join(snippets)


def test_workflow_is_importable_project_radar() -> None:
    workflow = load_workflow()

    assert workflow["name"] == "Kaka GitHub Project Radar"
    assert node_by_name(workflow, "Command Webhook")["parameters"]["path"] == "kaka/github_weekly_stars"
    assert node_by_name(workflow, "Weekly Schedule")["type"] == "n8n-nodes-base.scheduleTrigger"
    assert node_by_name(workflow, "Respond to Command")["type"] == "n8n-nodes-base.respondToWebhook"
    assert node_by_name(workflow, "Post Scheduled Digest to Kaka")["type"] == "n8n-nodes-base.httpRequest"


def test_workflow_uses_radar_queries_and_three_sections() -> None:
    code = all_code(load_workflow())

    assert "GITHUB_RADAR_SECTION_LIMIT" in code
    assert "GITHUB_RADAR_ACTIVE_DAYS" in code
    assert "GITHUB_RADAR_MATURE_MIN_STARS" in code
    assert "GITHUB_RADAR_POTENTIAL_MIN_STARS" in code
    assert "GITHUB_RADAR_POTENTIAL_MAX_STARS" in code
    assert "GITHUB_RADAR_GROWTH_MIN_STARS" in code
    assert "fork:false archived:false" in code
    assert "pushed:>" in code
    assert '"matureSection": "一、成熟活跃项目"' in code
    assert '"potentialSection": "二、潜力项目"' in code
    assert '"growthTitle": "三、增长最快项目"' in code
    assert "Top ${sectionLimit}" in code


def test_workflow_labels_synthetic_growth_and_stores_snapshots() -> None:
    code = all_code(load_workflow())

    assert "getWorkflowStaticData('global')" in code
    assert "github_project_radar_snapshots" in code
    assert "GITHUB_RADAR_FAKE_GROWTH_ON_FIRST_RUN" in code
    assert "测试数据" in code
    assert "真实增长榜将在下次周报生成" in code


def test_scheduled_notification_uses_radar_target_with_weekly_fallback() -> None:
    workflow = load_workflow()
    post_node = node_by_name(workflow, "Post Scheduled Digest to Kaka")
    request_body = json.dumps(post_node["parameters"], ensure_ascii=False)

    assert "GITHUB_RADAR_TARGET_SCENE_TYPE" in request_body
    assert "GITHUB_RADAR_TARGET_SCENE_ID" in request_body
    assert "GITHUB_WEEKLY_TARGET_SCENE_TYPE" in request_body
    assert "GITHUB_WEEKLY_TARGET_SCENE_ID" in request_body
    assert "n8n:github_project_radar" in request_body
    assert "github-project-radar" in request_body
