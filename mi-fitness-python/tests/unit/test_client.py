"""测试 API 客户端 (client.py)。

使用 mock 替换 _request 方法，验证各业务方法的参数组装和响应解析。
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from mi_fitness.client import MiHealthClient
from mi_fitness.const import (
    ALL_SHARED_DATA_TYPES,
    MESSAGE_GET_LIST_PATH,
    MESSAGE_MODULE_RELATIVES,
    RELATIVES_DELETE_PATH,
    RELATIVES_GET_INVITE_ID_PATH,
    RELATIVES_LIST_PATH,
    RELATIVES_OPERATE_INVITE_PATH,
    RELATIVES_VERIFY_USER_PATH,
    VERIFY_TYPE_XIAOMI_ID,
)
from mi_fitness.exceptions import (
    DataNotSharedError,
    DataOutOfSharedTimeScopeError,
    FamilyMemberNotFoundError,
    TokenExpiredError,
)
from mi_fitness.models import (
    CaloriesData,
    GoalData,
    HeartRateData,
    IntensityData,
    LatestDataSnapshot,
    SleepData,
    Spo2Data,
    Spo2SummaryData,
    StepData,
    ValidStandData,
    WeightData,
)

from .conftest import (
    AGGREGATED_HR_RESPONSE,
    AGGREGATED_SLEEP_RESPONSE,
    AGGREGATED_STEPS_RESPONSE,
    CHECK_NEW_MSG_RESPONSE,
    CHECK_NO_NEW_MSG_RESPONSE,
    DELETE_RESPONSE,
    FAMILY_MEMBER_RESPONSE,
    FITNESS_BLOOD_PRESSURE_RESPONSE,
    FITNESS_WEIGHT_RESPONSE,
    INVITE_ID_RESPONSE,
    INVITE_RESPONSE,
    LATEST_DATA_RESPONSE,
    MESSAGE_LIST_RESPONSE,
    OPERATE_INVITE_RESPONSE,
    RELATIVE_LIST_RESPONSE,
    SHARED_TYPES_RESPONSE,
    VERIFY_USER_RESPONSE,
)

# 使用 pytest fixture 中的 mock_auth
pytestmark = pytest.mark.asyncio


def _make_client(mock_auth: Any) -> MiHealthClient:
    """用 mock auth 构造客户端实例。"""
    return MiHealthClient(mock_auth)


# region 亲友列表
class TestGetRelatives:
    async def test_returns_family_members(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=RELATIVE_LIST_RESPONSE)

        members = await client.get_relatives()
        assert len(members) == 2
        assert members[0].relative_uid == 1452722403
        assert members[0].relative_note == "妈妈"
        assert members[1].relative_note == "爸爸"

        client._request.assert_called_once_with("GET", RELATIVES_LIST_PATH)

    async def test_empty_list(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value={"code": 0, "result": {"relative_list": []}})
        members = await client.get_relatives()
        assert members == []


# endregion


# region 查找亲友
class TestFindRelative:
    async def test_find_by_uid(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=RELATIVE_LIST_RESPONSE)

        member = await client.find_relative(1452722403)
        assert member.relative_uid == 1452722403

    async def test_find_by_note(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=RELATIVE_LIST_RESPONSE)

        member = await client.find_relative("妈")
        assert member.relative_note == "妈妈"

    async def test_not_found_raises(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=RELATIVE_LIST_RESPONSE)

        with pytest.raises(FamilyMemberNotFoundError):
            await client.find_relative("不存在的人")


# endregion


# region 验证用户
class TestVerifyUser:
    async def test_verify_by_xiaomi_id(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=VERIFY_USER_RESPONSE)

        info = await client.verify_user(1452722403)
        assert info is not None
        assert info.user_id == 1452722403
        assert info.nickname == "测试用户"

        client._request.assert_called_once_with(
            "GET",
            RELATIVES_VERIFY_USER_PATH,
            params={"verify_id": 1452722403, "verify_type": VERIFY_TYPE_XIAOMI_ID},
        )

    async def test_verify_returns_none_for_missing_user(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value={"code": 0, "result": {}})
        info = await client.verify_user(999)
        assert info is None


# endregion


# region 邀请亲友
class TestInviteRelative:
    async def test_invite_success(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=INVITE_RESPONSE)

        result = await client.invite_relative(1452722403)
        assert result is True

        call_args = client._request.call_args
        params = call_args.kwargs["params"]
        assert params["relative_uid"] == 1452722403
        assert params["auth_content"]["auth_data"] == ALL_SHARED_DATA_TYPES
        assert params["auth_content"]["auth_time_range"] == 3

    async def test_invite_with_custom_types(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=INVITE_RESPONSE)

        await client.invite_relative(
            123,
            shared_data_types=["heart_rate", "sleep"],
            auth_time_range=1,
        )

        params = client._request.call_args.kwargs["params"]
        assert params["auth_content"]["auth_data"] == ["heart_rate", "sleep"]
        assert params["auth_content"]["auth_time_range"] == 1

    async def test_invite_with_note(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=INVITE_RESPONSE)

        await client.invite_relative(123, relative_note="好友")

        params = client._request.call_args.kwargs["params"]
        assert params["relative_note"] == "好友"

    async def test_invite_failure(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value={"code": 0, "result": {"send_ret": 0}})
        result = await client.invite_relative(123)
        assert result is False


# endregion


# region 操作邀请（同意/拒绝）
class TestOperateInvite:
    async def test_accept_success(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=OPERATE_INVITE_RESPONSE)

        result = await client.accept_invite(4777767, 152824796151809)
        assert result is True

        call_args = client._request.call_args
        params = call_args.kwargs["params"]
        assert params["invite_id"] == 4777767
        assert params["msg_id"] == 152824796151809
        assert params["operate"] == 1
        assert params["auth_content"]["auth_data"] == ALL_SHARED_DATA_TYPES

    async def test_accept_with_custom_types(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=OPERATE_INVITE_RESPONSE)

        await client.accept_invite(123, 456, shared_data_types=["heart_rate", "sleep"])

        params = client._request.call_args.kwargs["params"]
        assert params["auth_content"]["auth_data"] == ["heart_rate", "sleep"]

    async def test_reject_success(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=OPERATE_INVITE_RESPONSE)

        result = await client.reject_invite(4777767, 152824796151809)
        assert result is True

        params = client._request.call_args.kwargs["params"]
        assert params["operate"] == 2

    async def test_accept_calls_correct_endpoint(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=OPERATE_INVITE_RESPONSE)

        await client.accept_invite(1, 2)

        client._request.assert_called_once_with(
            "POST",
            RELATIVES_OPERATE_INVITE_PATH,
            params={
                "auth_content": {
                    "auth_time_range": 3,
                    "auth_data": ALL_SHARED_DATA_TYPES,
                },
                "invite_id": 1,
                "msg_id": 2,
                "operate": 1,
            },
        )

    async def test_operate_failure(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value={"code": 0, "result": {"operate_ret": False}})
        result = await client.accept_invite(1, 2)
        assert result is False


# endregion


# region 删除亲友
class TestDeleteRelative:
    async def test_delete_success(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=DELETE_RESPONSE)

        result = await client.delete_relative(1452722403)
        assert result is True

        client._request.assert_called_once_with(
            "POST",
            RELATIVES_DELETE_PATH,
            params={"relative_uid": 1452722403},
        )

    async def test_delete_failure(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value={"code": 0, "result": {"delete_ret": False}})
        result = await client.delete_relative(123)
        assert result is False


# endregion


# region 邀请链接 ID
class TestGetInviteLinkId:
    async def test_returns_snowflake_id(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=INVITE_ID_RESPONSE)

        link_id = await client.get_invite_link_id()
        assert link_id == 467184968352742400

        client._request.assert_called_once_with("GET", RELATIVES_GET_INVITE_ID_PATH)


# endregion


# region 共享数据类型
class TestGetSharedDataTypes:
    async def test_returns_keys(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=SHARED_TYPES_RESPONSE)

        keys = await client.get_shared_data_types(123)
        assert "heart_rate" in keys

    async def test_direction_parameter(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=SHARED_TYPES_RESPONSE)

        await client.get_shared_data_types(123, direction=1)
        params = client._request.call_args.kwargs["params"]
        assert params["type"] == 1


# endregion


# region 家庭成员
class TestGetFamilyMembers:
    async def test_returns_list(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=FAMILY_MEMBER_RESPONSE)

        members = await client.get_family_members()
        assert len(members) == 1
        assert members[0]["userId"] == 123


# endregion


# region 最新数据
class TestGetLatestData:
    async def test_returns_typed_snapshot(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=LATEST_DATA_RESPONSE)

        latest = await client.get_latest_data(123)
        assert isinstance(latest, LatestDataSnapshot)
        assert latest.updated_time == 1717495200
        assert latest.goal is not None
        assert len(latest.goal.goal_items) == 2
        assert latest.heart_rate is not None
        assert latest.heart_rate.bpm == 84
        assert latest.sleep is not None
        assert latest.sleep.total_duration == 436
        assert latest.steps is not None
        assert latest.steps.goal == 6000
        assert latest.calories is not None
        assert latest.calories.calories == 230
        assert latest.valid_stand is not None
        assert latest.valid_stand.count == 7
        assert latest.intensity is not None
        assert latest.intensity.duration == 15
        assert latest.weight is not None
        assert latest.weight.weight == 65.5
        assert latest.spo2 is not None
        assert latest.spo2.spo2 == 96
        assert latest.blood_pressure is None


class TestGetLatestItems:
    async def test_returns_raw_items(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=LATEST_DATA_RESPONSE)

        items = await client.get_latest_items(123)
        assert len(items) == 10
        assert items[0].key == "goal"
        assert items[1].key == "heart_rate"


# endregion


# region 心率数据
class TestGetHeartRate:
    async def test_returns_heart_rate_data(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=AGGREGATED_HR_RESPONSE)

        data = await client.get_heart_rate(123, date(2024, 6, 4))
        assert len(data) == 1
        assert isinstance(data[0], HeartRateData)
        assert data[0].avg_hr == 72
        assert data[0].latest_hr is not None
        assert data[0].latest_hr.bpm == 75

    async def test_skips_invalid_heart_rate_item(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(
            return_value={
                "code": 0,
                "result": {
                    "data_list": [
                        {
                            "sid": "miothealth",
                            "tag": "daily_report",
                            "key": "heart_rate",
                            "time": 1717430400,
                            "value": '{"avg_hr":{"bad":1}}',
                            "update_time": 1717488000,
                            "watermark": "w1",
                            "source_sid_list": [],
                        },
                        AGGREGATED_HR_RESPONSE["result"]["data_list"][0],
                    ]
                },
            }
        )

        data = await client.get_heart_rate(123, date(2024, 6, 4))

        assert len(data) == 1
        assert data[0].avg_hr == 72


# endregion


# region 睡眠数据
class TestGetSleep:
    async def test_returns_sleep_data(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=AGGREGATED_SLEEP_RESPONSE)

        data = await client.get_sleep(123, date(2024, 6, 4))
        assert len(data) == 1
        assert isinstance(data[0], SleepData)
        assert data[0].total_duration == 480
        assert data[0].sleep_score == 85
        assert len(data[0].segment_details) == 1


# endregion


# region 步数数据
class TestGetSteps:
    async def test_returns_step_data(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=AGGREGATED_STEPS_RESPONSE)

        data = await client.get_steps(123, date(2024, 6, 4))
        assert len(data) == 1
        assert isinstance(data[0], StepData)
        assert data[0].steps == 8500


# endregion


# region 其它聚合指标
class TestOtherAggregatedMetrics:
    async def test_history_days_uses_trailing_window(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value={"code": 0, "result": {"data_list": []}})

        await client.get_calories_history(123, date(2024, 6, 4), days=7)

        call = client._request.call_args
        assert call is not None
        params = call.kwargs["params"]
        assert params["key"] == "calories"
        assert params["limit"] == 7
        assert params["end_time"] - params["start_time"] == 86400 * 7 - 1

    async def test_returns_calories_valid_stand_and_intensity(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(
            side_effect=[
                {
                    "code": 0,
                    "result": {
                        "data_list": [
                            {
                                "sid": "default",
                                "tag": "daily_report",
                                "key": "calories",
                                "time": 1717430400,
                                "value": '{"calories":338}',
                                "update_time": 1717488000,
                                "watermark": "w1",
                                "source_sid_list": [],
                            }
                        ]
                    },
                },
                {
                    "code": 0,
                    "result": {
                        "data_list": [
                            {
                                "sid": "default",
                                "tag": "daily_report",
                                "key": "valid_stand",
                                "time": 1717430400,
                                "value": '{"count":10}',
                                "update_time": 1717488000,
                                "watermark": "w2",
                                "source_sid_list": [],
                            }
                        ]
                    },
                },
                {
                    "code": 0,
                    "result": {
                        "data_list": [
                            {
                                "sid": "default",
                                "tag": "daily_report",
                                "key": "intensity",
                                "time": 1717430400,
                                "value": '{"duration":19}',
                                "update_time": 1717488000,
                                "watermark": "w3",
                                "source_sid_list": [],
                            }
                        ]
                    },
                },
            ]
        )

        calories = await client.get_calories_history(123, date(2024, 6, 4))
        stand = await client.get_valid_stand_history(123, date(2024, 6, 4))
        intensity = await client.get_intensity_history(123, date(2024, 6, 4))

        assert isinstance(calories[0], CaloriesData)
        assert calories[0].calories == 338
        assert isinstance(stand[0], ValidStandData)
        assert stand[0].count == 10
        assert isinstance(intensity[0], IntensityData)
        assert intensity[0].duration == 19

    async def test_returns_spo2_history(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(
            return_value={
                "code": 0,
                "result": {
                    "data_list": [
                        {
                            "sid": "default",
                            "tag": "daily_report",
                            "key": "spo2",
                            "time": 1761091200,
                            "value": (
                                '{"avg_spo2":96,"lack_spo2_count":0,'
                                '"latest_spo2":{"spo2":96,"time":1761161730},'
                                '"max_spo2":96,"min_spo2":96}'
                            ),
                            "update_time": 1762064917,
                            "watermark": "w4",
                            "source_sid_list": [],
                        }
                    ]
                },
            }
        )

        series = await client.get_spo2_history(123, date(2025, 10, 22))

        assert len(series) == 1
        assert isinstance(series[0], Spo2SummaryData)
        assert series[0].avg_spo2 == 96
        assert series[0].latest_spo2 is not None
        assert series[0].latest_spo2.spo2 == 96

    async def test_returns_weight_history(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=FITNESS_WEIGHT_RESPONSE)

        series = await client.get_weight_history(123, date(2026, 3, 17), days=7)

        assert len(series) == 1
        assert isinstance(series[0], WeightData)
        assert series[0].weight == 55.0
        assert series[0].bmi == 16.97531

    async def test_returns_blood_pressure_history(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=FITNESS_BLOOD_PRESSURE_RESPONSE)

        series = await client.get_blood_pressure_history(123, date(2026, 3, 17), days=7)

        assert len(series) == 1
        assert series[0].systolic == 33
        assert series[0].diastolic == 30
        assert series[0].pulse == 60


# endregion


# region 体重数据
class TestGetWeight:
    async def test_returns_weight_data(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=LATEST_DATA_RESPONSE)

        weight = await client.get_weight(123)
        assert weight is not None
        assert isinstance(weight, WeightData)
        assert weight.weight == 65.5
        assert weight.bmi == 22.1

    async def test_returns_none_when_no_weight(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        resp = {
            "code": 0,
            "result": {
                "data_list": [
                    {"time": 100, "key": "heart_rate", "value": "{}"},
                ]
            },
        }
        client._request = AsyncMock(return_value=resp)
        client.get_shared_data_types = AsyncMock(return_value=["weight"])  # type: ignore[method-assign]

        weight = await client.get_weight(123)
        assert weight is None

    async def test_raises_not_shared_when_weight_disabled(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value={"code": 0, "result": {"data_list": []}})
        client.get_shared_data_types = AsyncMock(return_value=["steps"])  # type: ignore[method-assign]

        with pytest.raises(DataNotSharedError, match="weight"):
            await client.get_weight(123)


class TestGetLatestMetricHelpers:
    async def test_returns_goal_and_other_latest_metric_types(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=LATEST_DATA_RESPONSE)

        goal = await client.get_goal(123)
        calories = await client.get_calories(123)
        stand = await client.get_valid_stand(123)
        intensity = await client.get_intensity(123)
        spo2 = await client.get_spo2(123)

        assert isinstance(goal, GoalData)
        assert len(goal.goal_items) == 2
        assert goal.steps_goal is not None
        assert goal.steps_goal.target_value == 6000
        assert goal.calories_goal is not None
        assert goal.calories_goal.target_value == 400
        assert goal.intensity_goal is None
        assert isinstance(calories, CaloriesData)
        assert calories.calories == 230
        assert isinstance(stand, ValidStandData)
        assert stand.count == 7
        assert isinstance(intensity, IntensityData)
        assert intensity.duration == 15
        assert isinstance(spo2, Spo2Data)
        assert spo2.spo2 == 96

    async def test_blood_pressure_returns_none_when_shared_but_no_payload(
        self, mock_auth: Any
    ) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=LATEST_DATA_RESPONSE)
        client.get_shared_data_types = AsyncMock(return_value=["blood_pressure"])  # type: ignore[method-assign]

        blood_pressure = await client.get_blood_pressure(123)

        assert blood_pressure is None

    async def test_blood_pressure_supports_fitness_aliases_in_latest_payload(
        self, mock_auth: Any
    ) -> None:
        client = _make_client(mock_auth)
        resp = {
            "code": 0,
            "result": {
                "data_list": [
                    {
                        "time": 1773753098,
                        "key": "blood_pressure",
                        "value": (
                            '{"systolic_pressure":33,"diastolic_pressure":30,'
                            '"pulse":60,"time":1773753098}'
                        ),
                    }
                ]
            },
        }
        client._request = AsyncMock(return_value=resp)

        blood_pressure = await client.get_blood_pressure(123)

        assert blood_pressure is not None
        assert blood_pressure.systolic == 33
        assert blood_pressure.diastolic == 30
        assert blood_pressure.pulse == 60


# endregion


# region 每日摘要
class TestGetDailySummary:
    async def test_returns_summary_dict(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        # 依次返回心率、睡眠、步数的响应
        client._request = AsyncMock(
            side_effect=[
                AGGREGATED_HR_RESPONSE,
                AGGREGATED_SLEEP_RESPONSE,
                AGGREGATED_STEPS_RESPONSE,
            ]
        )

        summary = await client.get_daily_summary(123, date(2024, 6, 4))
        assert summary.date == "2024-06-04"
        assert summary.relative_uid == 123
        assert summary.heart_rate is not None
        assert summary.sleep is not None
        assert summary.steps is not None

    async def test_get_latest_daily_summary_uses_relative_latest_date(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client.find_relative = AsyncMock(
            return_value=type(
                "Member",
                (),
                {
                    "relative_uid": 123,
                    "relative_note": "测试",
                    "latest_data_time": 1717488000,
                },
            )()
        )
        client._request = AsyncMock(
            side_effect=[
                AGGREGATED_HR_RESPONSE,
                AGGREGATED_SLEEP_RESPONSE,
                AGGREGATED_STEPS_RESPONSE,
            ]
        )

        summary = await client.get_latest_daily_summary(123)

        assert summary.date == "2024-06-04"
        assert summary.heart_rate is not None
        assert summary.sleep is not None
        assert summary.steps is not None

    async def test_get_latest_daily_summary_falls_back_to_latest_snapshot_time(
        self, mock_auth: Any
    ) -> None:
        client = _make_client(mock_auth)
        client.find_relative = AsyncMock(
            return_value=type(
                "Member",
                (),
                {
                    "relative_uid": 123,
                    "relative_note": "测试",
                    "latest_data_time": 0,
                },
            )()
        )
        client._request = AsyncMock(
            side_effect=[
                LATEST_DATA_RESPONSE,
                AGGREGATED_HR_RESPONSE,
                AGGREGATED_SLEEP_RESPONSE,
                AGGREGATED_STEPS_RESPONSE,
            ]
        )

        summary = await client.get_latest_daily_summary(123)

        assert summary.date == "2024-06-04"
        assert summary.heart_rate is not None
        assert summary.sleep is not None
        assert summary.steps is not None

    async def test_daily_summary_returns_partial_results_when_some_data_not_shared(
        self,
        mock_auth: Any,
    ) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(
            side_effect=[
                DataNotSharedError("未共享该数据类型", data_type="heart_rate"),
                DataNotSharedError("未共享该数据类型", data_type="sleep"),
                AGGREGATED_STEPS_RESPONSE,
            ]
        )

        summary = await client.get_daily_summary(123, date(2024, 6, 4))

        assert summary.date == "2024-06-04"
        assert summary.heart_rate is None
        assert summary.sleep is None
        assert summary.steps is not None
        assert summary.steps.steps == 8500

    async def test_daily_summary_raises_when_query_date_exceeds_shared_time_scope(
        self,
        mock_auth: Any,
    ) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(
            side_effect=[
                DataOutOfSharedTimeScopeError("超出亲友共享时间范围", data_type="heart_rate"),
                AGGREGATED_SLEEP_RESPONSE,
                AGGREGATED_STEPS_RESPONSE,
            ]
        )

        with pytest.raises(DataOutOfSharedTimeScopeError, match="超出亲友共享时间范围"):
            await client.get_daily_summary(123, date(2024, 6, 4))


# endregion


# region 上下文管理器
class TestContextManager:
    async def test_async_context_manager(self, mock_auth: Any) -> None:
        async with MiHealthClient(mock_auth) as client:
            assert client is not None


# endregion


# region 自动刷新
class TestAutoRefresh:
    async def test_request_refreshes_and_retries_once(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)

        async def refresh() -> Any:
            mock_auth.token.service_token = "refreshed-token"
            return mock_auth.token

        mock_auth.refresh = AsyncMock(side_effect=refresh)
        client._http = MagicMock()

        with pytest.MonkeyPatch.context() as mp:
            import mi_fitness.client.api as client_api_module

            encrypted = AsyncMock(
                side_effect=[
                    TokenExpiredError("expired"),
                    RELATIVE_LIST_RESPONSE,
                ]
            )
            mp.setattr(client_api_module, "encrypted_request", encrypted)

            members = await client.get_relatives()

        assert len(members) == 2
        mock_auth.refresh.assert_awaited_once()
        assert encrypted.await_count == 2

    async def test_request_does_not_refresh_twice(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        mock_auth.refresh = AsyncMock(return_value=mock_auth.token)
        client._http = MagicMock()

        with pytest.MonkeyPatch.context() as mp:
            import mi_fitness.client.api as client_api_module

            encrypted = AsyncMock(side_effect=TokenExpiredError("expired"))
            mp.setattr(client_api_module, "encrypted_request", encrypted)

            with pytest.raises(TokenExpiredError):
                await client._request("GET", RELATIVES_LIST_PATH)

        mock_auth.refresh.assert_awaited_once()
        assert encrypted.await_count == 2


# endregion


# region 消息接口
class TestGetInviteMessages:
    async def test_returns_all_messages(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=MESSAGE_LIST_RESPONSE)

        messages = await client.get_invite_messages()
        assert len(messages) == 2
        assert messages[0].msg_id == 152824796151809
        assert messages[0].sender == 1452722403
        assert messages[0].invite_id == 4777767
        assert messages[0].nick_name == "测试用户"
        assert messages[0].is_pending is True

        client._request.assert_called_once_with(
            "POST",
            MESSAGE_GET_LIST_PATH,
            params={"module": MESSAGE_MODULE_RELATIVES, "limit": 30},
        )

    async def test_pending_only(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=MESSAGE_LIST_RESPONSE)

        messages = await client.get_invite_messages(pending_only=True)
        assert len(messages) == 1
        assert messages[0].is_pending is True
        assert messages[0].invite_id == 4777767

    async def test_custom_limit(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=MESSAGE_LIST_RESPONSE)

        await client.get_invite_messages(limit=10)

        params = client._request.call_args.kwargs["params"]
        assert params["limit"] == 10


class TestHasNewInvite:
    async def test_has_new(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=CHECK_NEW_MSG_RESPONSE)

        result = await client.has_new_invite()
        assert result is True

    async def test_no_new(self, mock_auth: Any) -> None:
        client = _make_client(mock_auth)
        client._request = AsyncMock(return_value=CHECK_NO_NEW_MSG_RESPONSE)

        result = await client.has_new_invite()
        assert result is False


# endregion


# region 时间戳工具（同步测试，不需要 asyncio mark）
@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
class TestDateToTimestamps:
    def test_specific_date(self) -> None:
        start, end = MiHealthClient._date_to_timestamps(date(2024, 6, 4))
        assert end - start == 86399  # 23:59:59

    def test_today_default(self) -> None:
        start, end = MiHealthClient._date_to_timestamps()
        assert end - start == 86399


# endregion
