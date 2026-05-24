"""MiHealthClient —— 小米运动健康 API 客户端。

薄编排层：持有 HTTP 客户端与认证状态，
所有业务逻辑委托给 relatives / data / messages 子模块。
"""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from typing import Any, Self

from mi_fitness.auth import XiaomiAuth
from mi_fitness.client import data as _data
from mi_fitness.client import messages as _msg
from mi_fitness.client import relatives as _rel
from mi_fitness.client.base import create_api_http, encrypted_request
from mi_fitness.const import HEALTH_API_BASE
from mi_fitness.exceptions import TokenExpiredError
from mi_fitness.models import (
    AggregatedDataResponse,
    BloodPressureData,
    CaloriesData,
    DailySummary,
    FamilyMember,
    GoalData,
    HeartRateData,
    IntensityData,
    InviteMessage,
    LatestDataItem,
    LatestDataSnapshot,
    SleepData,
    Spo2Data,
    Spo2SummaryData,
    StepData,
    ValidStandData,
    VerifiedUserInfo,
    WeightData,
)


class MiHealthClient:
    """小米运动健康 API 客户端。

    通过已登录的 XiaomiAuth 实例访问亲友健康数据 API。
    所有请求使用 RC4 加密，通过 cookie 认证。

    Attributes:
        auth: 认证管理器。
        base_url: API 基础 URL。
    """

    def __init__(
        self,
        auth: XiaomiAuth,
        base_url: str = HEALTH_API_BASE,
    ):
        """
        Args:
            auth: 已通过登录的认证管理器。
            base_url: API 基础 URL（默认国内节点）。
        """
        self.auth = auth
        self.base_url = base_url.rstrip("/")
        self._http = create_api_http()
        self._refresh_lock = asyncio.Lock()

    @classmethod
    def from_token(cls, path: Path | str, **kwargs: Any) -> Self:
        """从 token 文件一步创建客户端。

        Args:
            path: token 文件路径。
            **kwargs: 传递给 MiHealthClient 的额外参数（如 base_url）。

        Returns:
            已就绪的 MiHealthClient 实例。

        Raises:
            AuthError: 文件不存在或格式错误。
        """
        auth = XiaomiAuth.from_token(path)
        return cls(auth, **kwargs)

    def __repr__(self) -> str:
        uid = self.auth.token.user_id or "N/A"
        return f"MiHealthClient(user_id={uid!r}, base_url={self.base_url!r})"

    # region 内部请求
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        _allow_refresh: bool = True,
    ) -> dict[str, Any]:
        """发送 RC4 加密的 API 请求。"""
        expired_service_token = self.auth.token.service_token
        try:
            return await encrypted_request(
                self._http,
                self.auth.token,
                method,
                path,
                self.base_url,
                params=params,
            )
        except TokenExpiredError:
            if not _allow_refresh:
                raise
            await self._refresh_auth(expired_service_token)
            return await self._request(method, path, params=params, _allow_refresh=False)

    async def _refresh_auth(self, expired_service_token: str) -> None:
        """串行化自动刷新，避免并发请求重复刷新 token。"""
        async with self._refresh_lock:
            current_service_token = self.auth.token.service_token
            if (
                expired_service_token
                and current_service_token
                and current_service_token != expired_service_token
                and self.auth.is_authenticated
            ):
                return
            await self.auth.refresh()

    # endregion

    # region 亲友管理
    async def get_relatives(self) -> list[FamilyMember]:
        """获取亲友列表。"""
        return await _rel.get_relatives(self)

    async def find_relative(self, keyword: str | int) -> FamilyMember:
        """按备注名或 UID 查找亲友。"""
        return await _rel.find_relative(self, keyword)

    async def verify_user(
        self,
        verify_id: int,
        *,
        verify_type: int = 1,
    ) -> VerifiedUserInfo | None:
        """按 UID 或扫码 ID 验证用户信息。"""
        return await _rel.verify_user(self, verify_id, verify_type=verify_type)

    async def invite_relative(
        self,
        relative_uid: int,
        *,
        shared_data_types: list[str] | None = None,
        auth_time_range: int = 3,
        relative_note: str = "",
    ) -> bool:
        """发送亲友邀请。"""
        return await _rel.invite_relative(
            self,
            relative_uid,
            shared_data_types=shared_data_types,
            auth_time_range=auth_time_range,
            relative_note=relative_note,
        )

    async def accept_invite(
        self,
        invite_id: int,
        msg_id: int,
        *,
        shared_data_types: list[str] | None = None,
        auth_time_range: int = 3,
    ) -> bool:
        """同意亲友邀请。"""
        return await _rel.accept_invite(
            self,
            invite_id,
            msg_id,
            shared_data_types=shared_data_types,
            auth_time_range=auth_time_range,
        )

    async def reject_invite(self, invite_id: int, msg_id: int) -> bool:
        """拒绝亲友邀请。"""
        return await _rel.reject_invite(self, invite_id, msg_id)

    async def delete_relative(self, relative_uid: int) -> bool:
        """删除亲友关系。"""
        return await _rel.delete_relative(self, relative_uid)

    async def get_invite_link_id(self) -> int:
        """获取二维码邀请链接 ID。"""
        return await _rel.get_invite_link_id(self)

    async def get_shared_data_types(
        self,
        relative_uid: int,
        *,
        direction: int = 2,
    ) -> list[str]:
        """获取亲友共享的数据类型列表。"""
        return await _rel.get_shared_data_types(self, relative_uid, direction=direction)

    async def get_applied_shared_data_types(self, relative_uid: int) -> list[str]:
        """获取已申请的共享数据类型。"""
        return await _rel.get_applied_shared_data_types(self, relative_uid)

    async def get_family_members(self) -> list[dict[str, Any]]:
        """获取家庭成员列表。"""
        return await _rel.get_family_members(self)

    async def get_topic_subscriptions(
        self,
        relative_uid: int,
        topics: list[str] | None = None,
    ) -> dict[str, Any]:
        """获取亲友的消息订阅状态。"""
        return await _rel.get_topic_subscriptions(self, relative_uid, topics)

    # endregion

    # region 数据查询
    async def get_latest_items(self, relative_uid: int) -> list[LatestDataItem]:
        """获取亲友的原始最新数据项列表。"""
        return await _data.get_latest_items(self, relative_uid)

    async def get_latest_data(self, relative_uid: int) -> LatestDataSnapshot:
        """获取亲友的最新数据快照（强类型聚合视图）。"""
        return await _data.get_latest_data(self, relative_uid)

    async def get_aggregated_data(
        self,
        relative_uid: int,
        key: str,
        start_time: int,
        end_time: int,
        *,
        tag: str = "daily_report",
        limit: int = 30,
    ) -> AggregatedDataResponse:
        """获取亲友的聚合数据。"""
        return await _data.get_aggregated_data(
            self,
            relative_uid,
            key,
            start_time,
            end_time,
            tag=tag,
            limit=limit,
        )

    async def get_fitness_data(
        self,
        relative_uid: int,
        key: str,
        start_time: int,
        end_time: int,
        *,
        limit: int = 30,
    ) -> AggregatedDataResponse:
        """获取亲友的原始测量/事件数据（如体重、血压、异常心率等）。"""
        return await _data.get_fitness_data(
            self,
            relative_uid,
            key,
            start_time,
            end_time,
            limit=limit,
        )

    async def get_heart_rate(
        self,
        relative_uid: int,
        query_date: date | None = None,
        *,
        days: int = 1,
    ) -> list[HeartRateData]:
        """获取亲友的心率数据。"""
        return await _data.get_heart_rate(self, relative_uid, query_date, days=days)

    async def get_sleep(
        self,
        relative_uid: int,
        query_date: date | None = None,
        *,
        days: int = 1,
    ) -> list[SleepData]:
        """获取亲友的睡眠数据。"""
        return await _data.get_sleep(self, relative_uid, query_date, days=days)

    async def get_steps(
        self,
        relative_uid: int,
        query_date: date | None = None,
        *,
        days: int = 1,
    ) -> list[StepData]:
        """获取亲友的步数数据。"""
        return await _data.get_steps(self, relative_uid, query_date, days=days)

    async def get_weight_history(
        self,
        relative_uid: int,
        query_date: date | None = None,
        *,
        days: int = 1,
    ) -> list[WeightData]:
        """获取亲友在指定窗口内的体重测量记录。"""
        return await _data.get_weight_history(self, relative_uid, query_date, days=days)

    async def get_blood_pressure_history(
        self,
        relative_uid: int,
        query_date: date | None = None,
        *,
        days: int = 1,
    ) -> list[BloodPressureData]:
        """获取亲友在指定窗口内的血压测量记录。"""
        return await _data.get_blood_pressure_history(self, relative_uid, query_date, days=days)

    async def get_weight(self, relative_uid: int) -> WeightData | None:
        """获取亲友最新体重数据。"""
        return await _data.get_weight(self, relative_uid)

    async def get_calories_history(
        self,
        relative_uid: int,
        query_date: date | None = None,
        *,
        days: int = 1,
    ) -> list[CaloriesData]:
        """获取亲友按天聚合的活动卡路里数据。"""
        return await _data.get_calories_history(self, relative_uid, query_date, days=days)

    async def get_valid_stand_history(
        self,
        relative_uid: int,
        query_date: date | None = None,
        *,
        days: int = 1,
    ) -> list[ValidStandData]:
        """获取亲友按天聚合的有效站立次数。"""
        return await _data.get_valid_stand_history(self, relative_uid, query_date, days=days)

    async def get_intensity_history(
        self,
        relative_uid: int,
        query_date: date | None = None,
        *,
        days: int = 1,
    ) -> list[IntensityData]:
        """获取亲友按天聚合的中高强度活动时长。"""
        return await _data.get_intensity_history(self, relative_uid, query_date, days=days)

    async def get_spo2_history(
        self,
        relative_uid: int,
        query_date: date | None = None,
        *,
        days: int = 1,
    ) -> list[Spo2SummaryData]:
        """获取亲友按天聚合的血氧摘要。"""
        return await _data.get_spo2_history(self, relative_uid, query_date, days=days)

    async def get_goal(self, relative_uid: int) -> GoalData | None:
        """获取亲友最新目标完成情况。"""
        return await _data.get_goal(self, relative_uid)

    async def get_blood_pressure(self, relative_uid: int) -> BloodPressureData | None:
        """获取亲友最新血压数据。"""
        return await _data.get_blood_pressure(self, relative_uid)

    async def get_calories(self, relative_uid: int) -> CaloriesData | None:
        """获取亲友最新活动卡路里。"""
        return await _data.get_calories(self, relative_uid)

    async def get_valid_stand(self, relative_uid: int) -> ValidStandData | None:
        """获取亲友最新有效站立次数。"""
        return await _data.get_valid_stand(self, relative_uid)

    async def get_intensity(self, relative_uid: int) -> IntensityData | None:
        """获取亲友最新中高强度活动时长。"""
        return await _data.get_intensity(self, relative_uid)

    async def get_spo2(self, relative_uid: int) -> Spo2Data | None:
        """获取亲友最新血氧数据。"""
        return await _data.get_spo2(self, relative_uid)

    async def get_daily_summary(
        self,
        relative_uid: int,
        query_date: date | None = None,
    ) -> DailySummary:
        """获取亲友的每日综合健康摘要。"""
        return await _data.get_daily_summary(self, relative_uid, query_date)

    async def get_latest_daily_summary(self, relative_uid: int) -> DailySummary:
        """获取亲友最近一次同步数据的每日综合健康摘要。"""
        return await _data.get_latest_daily_summary(self, relative_uid)

    # endregion

    # region 消息
    async def get_invite_messages(
        self,
        *,
        limit: int = 30,
        pending_only: bool = False,
    ) -> list[InviteMessage]:
        """获取亲友邀请消息列表。"""
        return await _msg.get_invite_messages(self, limit=limit, pending_only=pending_only)

    async def has_new_invite(self) -> bool:
        """检查是否有新的亲友邀请消息。"""
        return await _msg.has_new_invite(self)

    # endregion

    # region 静态工具
    @staticmethod
    def _date_to_timestamps(query_date: date | None = None) -> tuple[int, int]:
        """将日期转换为当日 00:00 ~ 23:59:59 的时间戳。"""
        return _data._date_to_timestamps(query_date)

    # endregion

    # region 生命周期
    async def close(self) -> None:
        """关闭 HTTP 客户端。"""
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # endregion
