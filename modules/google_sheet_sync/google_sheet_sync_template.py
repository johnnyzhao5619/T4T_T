# -*- coding: utf-8 -*-
"""Google Sheet 同步任务模板。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from core.task_manager import TaskExecutionError


@dataclass(frozen=True)
class _OAuthConfig:
    credentials_file: str
    token_file: str
    scopes: tuple[str, ...]

    @classmethod
    def from_config(cls, task_path: str, oauth_config: dict[str, Any]):
        if not isinstance(oauth_config, dict):
            raise GoogleSheetConfigurationError(
                "oauth 配置缺失或格式错误，无法初始化 Google Sheet 模块。")

        missing_keys = [
            key for key in ("credentials_file", "token_file", "scopes")
            if not oauth_config.get(key)
        ]
        if missing_keys:
            raise GoogleSheetConfigurationError(
                f"oauth 配置缺少字段: {', '.join(sorted(missing_keys))}")

        scopes = oauth_config["scopes"]
        if isinstance(scopes, str):
            scopes = (scopes,)
        elif isinstance(scopes, Iterable):
            scopes = tuple(str(scope) for scope in scopes if scope)
        else:
            raise GoogleSheetConfigurationError("oauth.scopes 必须是字符串或字符串列表。")

        if not scopes:
            raise GoogleSheetConfigurationError("oauth.scopes 不能为空。")

        credentials_path = os.path.join(task_path, oauth_config["credentials_file"])
        token_path = os.path.join(task_path, oauth_config["token_file"])

        return cls(credentials_file=credentials_path,
                   token_file=token_path,
                   scopes=scopes)


class GoogleSheetConfigurationError(TaskExecutionError):
    """Raised when task configuration is invalid."""


class GoogleSheetAuthorizationError(TaskExecutionError):
    """Raised when OAuth credential files are missing or invalid."""


class GoogleSheetNetworkError(TaskExecutionError):
    """Raised when Google API returns network related errors."""


def _load_credentials(oauth_config: _OAuthConfig) -> Credentials:
    if not os.path.exists(oauth_config.credentials_file):
        raise GoogleSheetAuthorizationError(
            f"未找到 OAuth 凭据文件: {oauth_config.credentials_file}")

    if not os.path.exists(oauth_config.token_file):
        raise GoogleSheetAuthorizationError(
            f"未找到 OAuth Token 文件: {oauth_config.token_file}")

    credentials = Credentials.from_authorized_user_file(
        oauth_config.token_file,
        list(oauth_config.scopes))

    if credentials.valid:
        return credentials

    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
        except RefreshError as exc:
            raise GoogleSheetAuthorizationError(
                "刷新 OAuth Token 失败，请重新授权。") from exc
        _persist_credentials(credentials, oauth_config.token_file)
        return credentials

    raise GoogleSheetAuthorizationError(
        "OAuth 凭据无效或缺少刷新 Token，请重新授权。")


def _persist_credentials(credentials: Credentials, token_path: str) -> None:
    os.makedirs(os.path.dirname(token_path), exist_ok=True)
    with open(token_path, "w", encoding="utf-8") as token_file:
        token_file.write(credentials.to_json())


def _build_service(credentials: Credentials):
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def _resolve_settings(config: dict[str, Any]) -> dict[str, Any]:
    settings = config.get("settings", {}) if isinstance(config, dict) else {}
    spreadsheet_id = settings.get("spreadsheet_id", "").strip()
    read_range = settings.get("read_range", "").strip()
    write_range = settings.get("write_range", "").strip()

    if not spreadsheet_id:
        raise GoogleSheetConfigurationError("settings.spreadsheet_id 不能为空。")
    if not read_range:
        raise GoogleSheetConfigurationError("settings.read_range 不能为空。")
    if not write_range:
        raise GoogleSheetConfigurationError("settings.write_range 不能为空。")

    return {
        "spreadsheet_id": spreadsheet_id,
        "read_range": read_range,
        "write_range": write_range,
        "value_input_option": settings.get("value_input_option", "RAW")
    }


def _normalize_values(values: Any) -> list[list[Any]]:
    if values is None:
        return []

    if isinstance(values, list):
        if all(isinstance(row, list) for row in values):
            return values
    raise GoogleSheetConfigurationError("inputs.values 必须是二维数组。")


def run(context, inputs):
    context.logger.info("开始执行 Google Sheet 同步任务。")
    oauth_config = _OAuthConfig.from_config(context.task_path,
                                            context.config.get("oauth", {}))
    settings = _resolve_settings(context.config)
    prepared_values = _normalize_values(inputs.get("values"))

    try:
        credentials = _load_credentials(oauth_config)
        service = _build_service(credentials)
        values_resource = service.spreadsheets().values()

        read_result = values_resource.get(
            spreadsheetId=settings["spreadsheet_id"],
            range=settings["read_range"]
        ).execute()
        read_values = read_result.get("values", [])
        context.logger.info(
            "已读取 %d 行数据，范围 %s。",
            len(read_values), settings["read_range"])

        updated_cells = 0
        if prepared_values:
            update_body = {"values": prepared_values}
            update_result = values_resource.update(
                spreadsheetId=settings["spreadsheet_id"],
                range=settings["write_range"],
                valueInputOption=settings["value_input_option"],
                body=update_body
            ).execute()
            updated_cells = int(update_result.get("updatedCells", 0))
            context.logger.info(
                "已写入 %d 个单元格，范围 %s。",
                updated_cells, settings["write_range"])
        else:
            context.logger.info("未提供写入数据，仅执行读取。")

        sync_state = {
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
            "fetched_rows": len(read_values),
            "updated_cells": updated_cells
        }
        context.update_state("google_sheet_sync", sync_state)
        context.logger.debug("同步状态已保存: %s", json.dumps(sync_state, ensure_ascii=False))

        return {
            "fetched_rows": len(read_values),
            "updated_cells": updated_cells
        }

    except HttpError as exc:
        raise GoogleSheetNetworkError(
            f"调用 Google Sheet API 失败: {exc}") from exc
    except RefreshError as exc:
        raise GoogleSheetAuthorizationError(
            "OAuth Token 刷新失败。") from exc
    except OSError as exc:
        raise GoogleSheetNetworkError(
            f"访问网络或凭据文件失败: {exc}") from exc
