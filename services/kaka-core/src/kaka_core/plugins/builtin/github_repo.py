from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx

from kaka_core.plugins.context import PluginContext
from kaka_core.plugins.result import PluginResult


OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MAX_SEARCH_RESULTS = 5


class GitHubRepositoryPlugin:
    id = "github_repo"
    name = "GitHub 项目"
    description = "查看 GitHub 仓库基本信息或按关键词搜索项目。"

    def __init__(
        self,
        *,
        api_base_url: str = "https://api.github.com",
        token: str = "",
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._token = token.strip()
        self._timeout_seconds = timeout_seconds
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "kaka-github-repo-plugin",
            }
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            self._client = httpx.AsyncClient(
                timeout=self._timeout_seconds,
                headers=headers,
                transport=self._transport,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def can_handle(self, context: PluginContext) -> bool:
        return bool(context.command_text.strip())

    async def run(self, context: PluginContext) -> PluginResult:
        mode, query = self._parse_command_text(context.command_text)
        if not query:
            return PluginResult.text_reply(
                self.id,
                "可以用 /项目 owner/repo、/项目 GitHub 链接，或 /项目搜索 关键词。",
                metadata={"plugin_error": "missing_github_query"},
            )

        repo = self._extract_owner_repo(query)
        if mode != "search" and repo:
            return await self._lookup_repository(repo)
        return await self._search_repositories(query)

    async def _lookup_repository(self, repo: str) -> PluginResult:
        if not self._api_base_url:
            return self._error_result("repo", "missing_github_api_base_url", "还没有配置 GitHub API 地址。")

        try:
            response = await self._get_client().get(f"{self._api_base_url}/repos/{repo}")
        except httpx.HTTPError as exc:
            return self._error_result("repo", "request_failed", str(exc), repo=repo)

        if response.status_code == 404:
            return PluginResult.text_reply(
                self.id,
                f"没有找到 GitHub 项目：{repo}",
                metadata={"mode": "repo", "repo": repo, "plugin_error": "not_found"},
            )
        if response.status_code != 200:
            return self._error_result(
                "repo",
                "unexpected_status",
                f"HTTP {response.status_code}",
                repo=repo,
                status_code=response.status_code,
            )

        try:
            body = response.json()
        except ValueError:
            return self._error_result("repo", "invalid_json", "GitHub 返回了非 JSON 内容。", repo=repo)

        return PluginResult(
            plugin_id=self.id,
            text=self._format_repository(body),
            data={"repo": body if isinstance(body, dict) else {}},
            metadata={"mode": "repo", "repo": repo, "source": "github-api"},
        )

    async def _search_repositories(self, query: str) -> PluginResult:
        if not self._api_base_url:
            return self._error_result(
                "search",
                "missing_github_api_base_url",
                "还没有配置 GitHub API 地址。",
                query=query,
            )

        try:
            response = await self._get_client().get(
                f"{self._api_base_url}/search/repositories",
                params={
                    "q": query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": str(MAX_SEARCH_RESULTS),
                },
            )
        except httpx.HTTPError as exc:
            return self._error_result("search", "request_failed", str(exc), query=query)

        if response.status_code != 200:
            return self._error_result(
                "search",
                "unexpected_status",
                f"HTTP {response.status_code}",
                query=query,
                status_code=response.status_code,
            )

        try:
            body = response.json()
        except ValueError:
            return self._error_result("search", "invalid_json", "GitHub 返回了非 JSON 内容。", query=query)

        return PluginResult(
            plugin_id=self.id,
            text=self._format_search_results(query, body),
            data={"search": body if isinstance(body, dict) else {}},
            metadata={"mode": "search", "query": query, "source": "github-api"},
        )

    def _parse_command_text(self, command_text: str) -> tuple[str, str]:
        command = command_text.strip()
        first, _, rest = command.partition(" ")
        if first.lower() in {"repo", "search"}:
            return first.lower(), rest.strip()
        return "auto", command

    def _extract_owner_repo(self, query: str) -> str | None:
        value = query.strip().rstrip("/")
        parsed = urlparse(value)
        if parsed.netloc.lower() == "github.com":
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
            return None
        if OWNER_REPO_RE.match(value):
            return value
        return None

    def _format_repository(self, repo: Any) -> str:
        if not isinstance(repo, dict):
            return "GitHub 返回格式不正确。"

        full_name = self._as_text(repo.get("full_name"), "unknown/repo")
        description = self._as_text(repo.get("description"), "暂无简介")
        language = self._as_text(repo.get("language"), "未知")
        license_info = repo.get("license") if isinstance(repo.get("license"), dict) else {}
        license_name = self._as_text(license_info.get("spdx_id") or license_info.get("name"), "未声明")
        lines = [
            f"GitHub 项目：{full_name}",
            f"简介：{description}",
            f"Stars：{self._format_number(repo.get('stargazers_count'))}",
            f"Forks：{self._format_number(repo.get('forks_count'))}",
            f"Issues：{self._format_number(repo.get('open_issues_count'))}",
            f"语言：{language}",
            f"许可：{license_name}",
            f"默认分支：{self._as_text(repo.get('default_branch'), '未知')}",
            f"最近推送：{self._format_date(repo.get('pushed_at'))}",
            f"最近更新：{self._format_date(repo.get('updated_at'))}",
            f"状态：{self._format_status(repo)}",
            f"链接：{self._as_text(repo.get('html_url'), '')}",
        ]
        return "\n".join(line for line in lines if line.rstrip("："))

    def _format_search_results(self, query: str, body: Any) -> str:
        if not isinstance(body, dict):
            return "GitHub 返回格式不正确。"

        total_count = self._format_number(body.get("total_count"))
        items = body.get("items") if isinstance(body.get("items"), list) else []
        lines = [f"GitHub 搜索：{query}", f"找到约 {total_count} 个结果", ""]
        if not items:
            lines.append("没有找到匹配的项目。")
            return "\n".join(lines).rstrip()

        for index, repo in enumerate(items[:MAX_SEARCH_RESULTS], start=1):
            if not isinstance(repo, dict):
                continue
            lines.append(f"{index}. {self._as_text(repo.get('full_name'), 'unknown/repo')}")
            lines.append(
                "   "
                f"Stars：{self._format_number(repo.get('stargazers_count'))}，"
                f"Forks：{self._format_number(repo.get('forks_count'))}，"
                f"语言：{self._as_text(repo.get('language'), '未知')}"
            )
            lines.append(f"   简介：{self._as_text(repo.get('description'), '暂无简介')}")
            lines.append(f"   更新：{self._format_date(repo.get('updated_at'))}")
            lines.append(f"   {self._as_text(repo.get('html_url'), '')}")
        return "\n".join(lines).rstrip()

    def _format_status(self, repo: dict[str, Any]) -> str:
        status = []
        if repo.get("archived") is True:
            status.append("已归档")
        if repo.get("fork") is True:
            status.append("Fork")
        return "、".join(status) if status else "正常"

    def _format_number(self, value: Any) -> str:
        try:
            return f"{int(value):,}"
        except (TypeError, ValueError):
            return "0"

    def _format_date(self, value: Any) -> str:
        text = self._as_text(value, "未知")
        return text[:10] if len(text) >= 10 else text

    def _as_text(self, value: Any, fallback: str) -> str:
        if value is None:
            return fallback
        text = str(value).strip()
        return text or fallback

    def _error_result(
        self,
        mode: str,
        error: str,
        detail: str,
        *,
        repo: str | None = None,
        query: str | None = None,
        status_code: int | None = None,
    ) -> PluginResult:
        metadata: dict[str, object] = {
            "mode": mode,
            "plugin_error": error,
            "error_detail": detail,
        }
        if repo:
            metadata["repo"] = repo
        if query:
            metadata["query"] = query
        if status_code is not None:
            metadata["status_code"] = status_code
        return PluginResult.text_reply(
            self.id,
            "GitHub 项目查询暂时失败，卡咔晚点再试。",
            metadata=metadata,
        )
