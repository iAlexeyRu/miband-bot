"""测试数据模型 (models.py)。

覆盖：模型构造、字段解析、响应包装器的属性方法。
"""

from __future__ import annotations

import json

from mi_fitness.models import (
    AggregatedDataItem,
    AggregatedDataResponse,
    AuthToken,
    BloodPressureData,
    CaloriesData,
    CheckNewMsgResponse,
    DeleteRelativeResponse,
    FamilyMember,
    FamilyMemberResponse,
    GoalData,
    GoalMetric,
    HeartRateData,
    IntensityData,
    InviteMessage,
    InviteResponse,
    InviteUniqueIdResponse,
    LatestDataItem,
    LatestDataResponse,
    LatestDataSnapshot,
    LatestHeartRate,
    MessageListResponse,
    OperateInviteResponse,
    RelativeListResponse,
    SharedDataTypesResponse,
    SleepData,
    SleepSegment,
    Spo2Data,
    Spo2SummaryData,
    StepData,
    ValidStandData,
    VerifiedUserInfo,
    VerifyUserResponse,
    WeightData,
)


# region 基础模型测试
class TestAuthToken:
    """AuthToken 模型测试。"""

    def test_defaults(self) -> None:
        """空构造应全部默认空串。"""
        t = AuthToken()
        assert t.user_id == ""
        assert t.ssecurity == ""
        assert t.service_token == ""

    def test_serialization_roundtrip(self) -> None:
        """JSON 序列化往返。"""
        t = AuthToken(user_id="123", ssecurity="abc")
        data = t.model_dump_json()
        t2 = AuthToken.model_validate_json(data)
        assert t2.user_id == t.user_id
        assert t2.ssecurity == t.ssecurity


class TestFamilyMember:
    """FamilyMember 模型测试。"""

    def test_construction(self) -> None:
        m = FamilyMember(relative_uid=123, relative_note="妈妈")
        assert m.relative_uid == 123
        assert m.relative_note == "妈妈"
        assert m.latest_data_time == 0

    def test_from_dict(self) -> None:
        data = {
            "relative_uid": 9999,
            "relative_note": "爸爸",
            "relative_icon": "https://img.example.com/a.jpg",
            "latest_data_time": 1717488000,
            "latest_abnormal_record_time": 0,
            "source_tag": 1,
        }
        m = FamilyMember(**data)
        assert m.relative_uid == 9999
        assert m.source_tag == 1


class TestLatestHeartRate:
    def test_defaults(self) -> None:
        hr = LatestHeartRate()
        assert hr.bpm == 0
        assert hr.time == 0


class TestHeartRateData:
    def test_full_construction(self) -> None:
        hr = HeartRateData(
            time=1717488000,
            avg_hr=72,
            max_hr=120,
            min_hr=55,
            latest_hr=LatestHeartRate(bpm=75, time=1717488000),
        )
        assert hr.avg_hr == 72
        assert hr.latest_hr is not None
        assert hr.latest_hr.bpm == 75


class TestSleepData:
    def test_with_segments(self) -> None:
        seg = SleepSegment(bedtime=100, wake_up_time=200, duration=100)
        sd = SleepData(
            time=1717488000,
            total_duration=480,
            sleep_score=85,
            segment_details=[seg],
        )
        assert sd.total_duration == 480
        assert len(sd.segment_details) == 1
        assert sd.segment_details[0].duration == 100


class TestStepData:
    def test_construction(self) -> None:
        s = StepData(time=1717488000, steps=8500, distance=6200, calories=320)
        assert s.steps == 8500


class TestWeightData:
    def test_construction(self) -> None:
        w = WeightData(time=1717488000, weight=65.5, bmi=22.1)
        assert w.weight == 65.5
        assert w.bmi == 22.1


class TestVerifiedUserInfo:
    def test_alias_user_id(self) -> None:
        """userId 别名应映射到 user_id。"""
        info = VerifiedUserInfo(**{"userId": 12345, "nickname": "测试", "icon": "url"})
        assert info.user_id == 12345
        assert info.nickname == "测试"

    def test_populate_by_name(self) -> None:
        """也可以用 user_id 直接构造。"""
        info = VerifiedUserInfo(user_id=999, nickname="直接")  # type: ignore[call-arg]
        assert info.user_id == 999


# endregion


# region LatestDataItem 测试
class TestLatestDataItem:
    def test_parse_json_value(self) -> None:
        item = LatestDataItem(
            time=1717488000,
            key="heart_rate",
            value='{"avg_hr": 72}',
        )
        parsed = item.parse_value()
        assert isinstance(parsed, dict)
        assert parsed["avg_hr"] == 72

    def test_parse_numeric_value(self) -> None:
        item = LatestDataItem(time=1717488000, key="goal", value=10000)
        parsed = item.parse_value()
        assert parsed == 10000

    def test_parse_invalid_json(self) -> None:
        item = LatestDataItem(time=1717488000, key="bad", value="not{json")
        parsed = item.parse_value()
        assert parsed == {}

    def test_parse_dict_value(self) -> None:
        item = LatestDataItem(
            time=1717488000,
            key="weight",
            value={"weight": 65.5},  # type: ignore[arg-type]
        )
        parsed = item.parse_value()
        assert parsed == {"weight": 65.5}

    def test_parse_json_list_returns_empty_dict(self) -> None:
        item = LatestDataItem(time=1717488000, key="bad", value='["unexpected"]')
        assert item.parse_value() == {}

    def test_as_goal(self) -> None:
        item = LatestDataItem(
            time=1717488000,
            key="goal",
            value={
                "date_time": 1717488000,
                "goal_items": [
                    {"field": 1, "target_value": 6000, "achieved_value": 3716},
                ],
            },  # type: ignore[arg-type]
        )
        goal = item.as_goal()
        assert isinstance(goal, GoalData)
        assert goal.time == 1717488000
        assert len(goal.goal_items) == 1
        assert goal.goal_items[0].target_value == 6000
        assert goal.goal_items[0].metric == GoalMetric.STEPS
        assert goal.goal_items[0].metric_key == "steps"
        assert goal.goal_items[0].metric_label == "步数"

    def test_goal_accessors_and_unknown_items(self) -> None:
        goal = GoalData.model_validate(
            {
                "time": 1717488000,
                "goal_items": [
                    {"field": 2, "target_value": 400, "achieved_value": 347},
                    {"field": 1, "target_value": 6000, "achieved_value": 6203},
                    {"field": 4, "target_value": 30, "achieved_value": 27},
                    {"field": 99, "target_value": 1, "achieved_value": 0},
                ],
            }
        )

        assert goal.calories_goal is not None
        assert goal.calories_goal.target_value == 400
        assert goal.steps_goal is not None
        assert goal.steps_goal.achieved_value == 6203
        assert goal.intensity_goal is not None
        assert goal.intensity_goal.target_value == 30
        assert goal.available_metrics == [
            GoalMetric.CALORIES,
            GoalMetric.STEPS,
            GoalMetric.INTENSITY,
        ]
        assert len(goal.unknown_goal_items) == 1
        assert goal.unknown_goal_items[0].metric is None
        assert goal.unknown_goal_items[0].metric_key == "unknown:99"
        assert goal.get_item(GoalMetric.STEPS) is goal.steps_goal

    def test_as_heart_rate(self) -> None:
        item = LatestDataItem(
            time=1717488000,
            key="heart_rate",
            value='{"time":1717491600,"bpm":84}',
        )
        heart_rate = item.as_heart_rate()
        assert isinstance(heart_rate, LatestHeartRate)
        assert heart_rate.time == 1717491600
        assert heart_rate.bpm == 84

    def test_as_heart_rate_returns_none_for_invalid_payload(self) -> None:
        item = LatestDataItem(
            time=1717488000,
            key="heart_rate",
            value='{"time":1717491600,"bpm":{"bad":1}}',
        )
        assert item.as_heart_rate() is None

    def test_as_sleep_uses_date_time_alias(self) -> None:
        item = LatestDataItem(
            time=1717488000,
            key="sleep",
            value='{"date_time":1717488000,"total_duration":436,"sleep_score":86}',
        )
        sleep = item.as_sleep()
        assert isinstance(sleep, SleepData)
        assert sleep.time == 1717488000
        assert sleep.total_duration == 436
        assert sleep.sleep_score == 86

    def test_as_steps_and_latest_metrics(self) -> None:
        steps_item = LatestDataItem(
            time=1717488000,
            key="steps",
            value='{"date_time":1717488000,"steps":3716,"distance":2193,"calories":143,"goal":6000}',
        )
        calories_item = LatestDataItem(
            time=1717488000,
            key="calories",
            value='{"date_time":1717488000,"calories":230,"goal":300}',
        )
        stand_item = LatestDataItem(
            time=1717488000,
            key="valid_stand",
            value='{"date_time":1717488000,"count":7}',
        )
        intensity_item = LatestDataItem(
            time=1717488000,
            key="intensity",
            value='{"date_time":1717488000,"duration":15}',
        )
        spo2_item = LatestDataItem(
            time=1717488000,
            key="spo2",
            value='{"time":1717495200,"spo2":96}',
        )

        steps = steps_item.as_steps()
        calories = calories_item.as_calories()
        stand = stand_item.as_valid_stand()
        intensity = intensity_item.as_intensity()
        spo2 = spo2_item.as_spo2()

        assert isinstance(steps, StepData)
        assert steps.goal == 6000
        assert isinstance(calories, CaloriesData)
        assert calories.goal == 300
        assert isinstance(stand, ValidStandData)
        assert stand.count == 7
        assert isinstance(intensity, IntensityData)
        assert intensity.duration == 15
        assert isinstance(spo2, Spo2Data)
        assert spo2.spo2 == 96

    def test_as_blood_pressure_returns_none_when_value_missing(self) -> None:
        item = LatestDataItem(time=1717488000, key="blood_pressure")
        assert item.as_blood_pressure() is None

    def test_as_blood_pressure_supports_fitness_aliases(self) -> None:
        item = LatestDataItem(
            time=1773753098,
            key="blood_pressure",
            value='{"systolic_pressure":33,"diastolic_pressure":30,"pulse":60,"time":1773753098}',
        )

        blood_pressure = item.as_blood_pressure()

        assert isinstance(blood_pressure, BloodPressureData)
        assert blood_pressure.systolic == 33
        assert blood_pressure.diastolic == 30
        assert blood_pressure.pulse == 60


# endregion


# region AggregatedDataItem 测试
class TestAggregatedDataItem:
    def test_stringify_dict_value(self) -> None:
        """dict value 应被自动转为 JSON 字符串。"""
        item = AggregatedDataItem(
            time=1717488000,
            key="heart_rate",
            value={"avg_hr": 72},  # type: ignore[arg-type]
        )
        assert isinstance(item.value, str)
        parsed = json.loads(item.value)
        assert parsed["avg_hr"] == 72

    def test_as_heart_rate(self) -> None:
        value = json.dumps(
            {
                "avg_hr": 72,
                "max_hr": 120,
                "min_hr": 55,
                "avg_rhr": 62,
                "latest_hr": {"bpm": 75, "time": 1717488000},
            }
        )
        item = AggregatedDataItem(time=1717430400, key="heart_rate", value=value)
        hr = item.as_heart_rate()
        assert isinstance(hr, HeartRateData)
        assert hr.avg_hr == 72
        assert hr.time == 1717430400
        assert hr.latest_hr is not None
        assert hr.latest_hr.bpm == 75

    def test_as_sleep(self) -> None:
        value = json.dumps(
            {
                "total_duration": 480,
                "sleep_score": 85,
                "segment_details": [
                    {"bedtime": 100, "wake_up_time": 200, "duration": 100},
                ],
            }
        )
        item = AggregatedDataItem(time=1717430400, key="sleep", value=value)
        sd = item.as_sleep()
        assert isinstance(sd, SleepData)
        assert sd.total_duration == 480
        assert len(sd.segment_details) == 1

    def test_as_sleep_ignores_invalid_segments(self) -> None:
        value = json.dumps(
            {
                "total_duration": 480,
                "segment_details": [
                    {"bedtime": 100, "wake_up_time": 200, "duration": 100},
                    "bad-segment",
                    1,
                ],
            }
        )
        item = AggregatedDataItem(time=1717430400, key="sleep", value=value)
        sd = item.as_sleep()
        assert len(sd.segment_details) == 1
        assert sd.segment_details[0].duration == 100

    def test_as_steps(self) -> None:
        value = json.dumps({"steps": 8500, "distance": 6200, "calories": 320})
        item = AggregatedDataItem(time=1717430400, key="steps", value=value)
        st = item.as_steps()
        assert isinstance(st, StepData)
        assert st.steps == 8500
        assert st.time == 1717430400

    def test_as_simple_latest_metrics(self) -> None:
        calories_item = AggregatedDataItem(
            time=1717430400, key="calories", value='{"calories":338}'
        )
        stand_item = AggregatedDataItem(time=1717430400, key="valid_stand", value='{"count":10}')
        intensity_item = AggregatedDataItem(
            time=1717430400, key="intensity", value='{"duration":19}'
        )

        calories = calories_item.as_calories()
        stand = stand_item.as_valid_stand()
        intensity = intensity_item.as_intensity()

        assert isinstance(calories, CaloriesData)
        assert calories.time == 1717430400
        assert calories.calories == 338
        assert isinstance(stand, ValidStandData)
        assert stand.count == 10
        assert isinstance(intensity, IntensityData)
        assert intensity.duration == 19

    def test_as_weight_and_blood_pressure(self) -> None:
        weight_item = AggregatedDataItem(
            time=1773753142,
            key="weight",
            value='{"time":1773753142,"weight":55.0,"bmi":16.97531}',
        )
        blood_pressure_item = AggregatedDataItem(
            time=1773753098,
            key="blood_pressure",
            value='{"systolic_pressure":33,"diastolic_pressure":30,"pulse":60,"time":1773753098}',
        )

        weight = weight_item.as_weight()
        blood_pressure = blood_pressure_item.as_blood_pressure()

        assert isinstance(weight, WeightData)
        assert weight.weight == 55.0
        assert weight.bmi == 16.97531
        assert isinstance(blood_pressure, BloodPressureData)
        assert blood_pressure.systolic == 33
        assert blood_pressure.diastolic == 30
        assert blood_pressure.pulse == 60

    def test_as_spo2_summary(self) -> None:
        value = json.dumps(
            {
                "avg_spo2": 96,
                "lack_spo2_count": 0,
                "latest_spo2": {
                    "spo2": 96,
                    "time": 1761161730,
                    "dbKey": "single_spo2",
                },
                "max_spo2": 96,
                "min_spo2": 96,
            }
        )
        item = AggregatedDataItem(time=1761091200, key="spo2", value=value)
        spo2 = item.as_spo2()

        assert isinstance(spo2, Spo2SummaryData)
        assert spo2.time == 1761091200
        assert spo2.avg_spo2 == 96
        assert spo2.latest_spo2 is not None
        assert spo2.latest_spo2.spo2 == 96


# endregion


# region 响应包装器测试
class TestRelativeListResponse:
    def test_parse_relatives(self) -> None:
        resp = RelativeListResponse(
            code=0,
            result={
                "relative_list": [
                    {"relative_uid": 111, "relative_note": "A"},
                    {"relative_uid": 222, "relative_note": "B"},
                ]
            },
        )
        members = resp.relatives
        assert len(members) == 2
        assert members[0].relative_uid == 111

    def test_empty_list(self) -> None:
        resp = RelativeListResponse(code=0, result={"relative_list": []})
        assert resp.relatives == []

    def test_skips_invalid_relatives(self) -> None:
        resp = RelativeListResponse(
            code=0,
            result={
                "relative_list": [
                    123,
                    {"relative_note": "缺少 uid"},
                    {"relative_uid": 222, "relative_note": "B"},
                ]
            },
        )
        members = resp.relatives
        assert len(members) == 1
        assert members[0].relative_uid == 222


class TestLatestDataResponse:
    def test_parse_data_items(self) -> None:
        resp = LatestDataResponse(
            code=0,
            result={
                "data_list": [
                    {"time": 100, "key": "hr", "value": "{}"},
                ]
            },
        )
        items = resp.data_items
        assert len(items) == 1
        assert items[0].key == "hr"

    def test_non_mapping_result_is_tolerated(self) -> None:
        resp = LatestDataResponse(code=0, result=None)  # type: ignore[arg-type]
        assert resp.data_items == []

    def test_snapshot_returns_typed_metrics(self) -> None:
        resp = LatestDataResponse(
            code=0,
            result={
                "data_list": [
                    {
                        "time": 1717488000,
                        "key": "heart_rate",
                        "value": '{"time":1717491600,"bpm":84}',
                    },
                    {
                        "time": 1717488000,
                        "key": "steps",
                        "value": '{"date_time":1717488000,"steps":3716,"distance":2193,"calories":143,"goal":6000}',
                    },
                    {"time": 1717488000, "key": "spo2", "value": '{"time":1717495200,"spo2":96}'},
                    {"time": 1717488000, "key": "mood", "value": '{"score":80}'},
                ],
                "latest_data_time": 1717495200,
            },
        )
        snapshot = resp.snapshot
        assert isinstance(snapshot, LatestDataSnapshot)
        assert snapshot.updated_time == 1717495200
        assert snapshot.heart_rate is not None
        assert snapshot.heart_rate.bpm == 84
        assert snapshot.steps is not None
        assert snapshot.steps.goal == 6000
        assert snapshot.spo2 is not None
        assert snapshot.spo2.spo2 == 96
        assert snapshot.extras == {"mood": {"score": 80}}
        assert snapshot.available_keys == ["heart_rate", "steps", "spo2", "mood"]

    def test_snapshot_preserves_invalid_known_payload_in_extras(self) -> None:
        resp = LatestDataResponse(
            code=0,
            result={
                "data_list": [
                    {
                        "time": 1717488000,
                        "key": "heart_rate",
                        "value": '{"time":1717491600,"bpm":{"bad":1}}',
                    },
                ],
                "latest_data_time": 1717495200,
            },
        )
        snapshot = resp.snapshot
        assert snapshot.heart_rate is None
        assert snapshot.extras == {"heart_rate": {"time": 1717491600, "bpm": {"bad": 1}}}
        assert snapshot.available_keys == ["heart_rate"]


class TestAggregatedDataResponse:
    def test_parse_data_items(self) -> None:
        resp = AggregatedDataResponse(
            code=0,
            result={
                "data_list": [
                    {
                        "sid": "test",
                        "tag": "daily_report",
                        "key": "steps",
                        "time": 100,
                        "value": "{}",
                        "update_time": 200,
                    }
                ],
                "has_more": True,
                "next_key": "abc",
            },
        )
        assert len(resp.data_items) == 1
        assert resp.has_more is True
        assert resp.next_key == "abc"

    def test_string_flags_are_normalized(self) -> None:
        resp = AggregatedDataResponse(
            code=0,
            result={
                "data_list": [],
                "has_more": "false",
                "next_key": 123,
            },
        )
        assert resp.has_more is False
        assert resp.next_key == "123"


class TestVerifyUserResponse:
    def test_with_user(self) -> None:
        resp = VerifyUserResponse(
            code=0,
            result={"userId": 12345, "nickname": "用户", "icon": "url"},
        )
        info = resp.user_info
        assert info is not None
        assert info.user_id == 12345

    def test_no_user(self) -> None:
        resp = VerifyUserResponse(code=0, result={})
        assert resp.user_info is None


class TestInviteResponse:
    def test_success(self) -> None:
        resp = InviteResponse(code=0, result={"send_ret": 1})
        assert resp.success is True

    def test_failure(self) -> None:
        resp = InviteResponse(code=0, result={"send_ret": 0})
        assert resp.success is False

    def test_string_success_flag(self) -> None:
        resp = InviteResponse(code=0, result={"send_ret": "1"})
        assert resp.success is True


class TestDeleteRelativeResponse:
    def test_success(self) -> None:
        resp = DeleteRelativeResponse(code=0, result={"delete_ret": True})
        assert resp.success is True

    def test_failure(self) -> None:
        resp = DeleteRelativeResponse(code=0, result={"delete_ret": False})
        assert resp.success is False

    def test_string_false_is_false(self) -> None:
        resp = DeleteRelativeResponse(code=0, result={"delete_ret": "false"})
        assert resp.success is False


class TestOperateInviteResponse:
    def test_success(self) -> None:
        resp = OperateInviteResponse(code=0, result={"operate_ret": True})
        assert resp.success is True

    def test_failure(self) -> None:
        resp = OperateInviteResponse(code=0, result={"operate_ret": False})
        assert resp.success is False


class TestSharedDataTypesResponse:
    def test_parse_keys(self) -> None:
        resp = SharedDataTypesResponse(
            code=0,
            result={"keys": ["goal", "heart_rate", "sleep"]},
        )
        assert resp.keys == ["goal", "heart_rate", "sleep"]

    def test_empty(self) -> None:
        resp = SharedDataTypesResponse(code=0, result={})
        assert resp.keys == []

    def test_ignores_non_string_keys(self) -> None:
        resp = SharedDataTypesResponse(
            code=0,
            result={"keys": ["goal", 1, None, "sleep"]},
        )
        assert resp.keys == ["goal", "sleep"]


class TestInviteUniqueIdResponse:
    def test_parse_id(self) -> None:
        resp = InviteUniqueIdResponse(
            code=0,
            result={"invite_link_id": 467184968352742400},
        )
        assert resp.invite_link_id == 467184968352742400


class TestFamilyMemberResponse:
    def test_parse_list(self) -> None:
        resp = FamilyMemberResponse(
            code=0,
            result={"family_user_list": [{"userId": 1}, {"userId": 2}]},
        )
        assert len(resp.family_user_list) == 2

    def test_empty(self) -> None:
        resp = FamilyMemberResponse(code=0, result={})
        assert resp.family_user_list == []


# endregion


# region 消息模型测试
class TestInviteMessage:
    def test_pending_invite(self) -> None:
        msg = InviteMessage(
            msg_id=152824796151809,
            module=1,
            type=1,
            sender=1452722403,
            extra_data='{"invite_id":4777767,"nick_name":"测试","icon":"https://example.com/a.jpg"}',
            data_status=0,
        )
        assert msg.invite_id == 4777767
        assert msg.nick_name == "测试"
        assert msg.icon == "https://example.com/a.jpg"
        assert msg.is_pending is True

    def test_processed_notification(self) -> None:
        msg = InviteMessage(type=5, data_status=1, extra_data='{"nick_name":"用户"}')
        assert msg.invite_id is None
        assert msg.nick_name == "用户"
        assert msg.is_pending is False

    def test_invalid_extra_data(self) -> None:
        msg = InviteMessage(extra_data="not json")
        assert msg.invite_id is None
        assert msg.nick_name == ""
        assert msg.icon == ""

    def test_empty_extra_data(self) -> None:
        msg = InviteMessage(extra_data="")
        assert msg.invite_id is None
        assert msg.nick_name == ""

    def test_json_list_extra_data_is_ignored(self) -> None:
        msg = InviteMessage(extra_data='["bad-shape"]')
        assert msg.invite_id is None
        assert msg.nick_name == ""
        assert msg.icon == ""


class TestMessageListResponse:
    def test_parse_messages(self) -> None:
        resp = MessageListResponse(
            code=0,
            result={
                "messages": [
                    {"msg_id": 1, "type": 1, "sender": 100, "data_status": 0},
                    {"msg_id": 2, "type": 5, "sender": 200, "data_status": 1},
                ],
                "msg_total": 2,
            },
        )
        assert len(resp.messages) == 2
        assert resp.msg_total == 2
        assert resp.messages[0].msg_id == 1

    def test_empty(self) -> None:
        resp = MessageListResponse(code=0, result={})
        assert resp.messages == []
        assert resp.msg_total == 0

    def test_single_message_dict_is_tolerated(self) -> None:
        resp = MessageListResponse(
            code=0,
            result={"messages": {"msg_id": 1, "type": 1, "sender": 100}, "msg_total": "1"},
        )
        assert len(resp.messages) == 1
        assert resp.msg_total == 1


class TestCheckNewMsgResponse:
    def test_has_new(self) -> None:
        resp = CheckNewMsgResponse(code=0, result=[{"module": 1, "is_new": True}])
        assert resp.has_new(1) is True
        assert resp.has_new(2) is False

    def test_no_new(self) -> None:
        resp = CheckNewMsgResponse(code=0, result=[{"module": 1, "is_new": False}])
        assert resp.has_new(1) is False

    def test_empty(self) -> None:
        resp = CheckNewMsgResponse(code=0, result=[])
        assert resp.has_new(1) is False

    def test_single_dict_result_is_tolerated(self) -> None:
        resp = CheckNewMsgResponse(code=0, result={"module": 1, "is_new": "true"})  # type: ignore[arg-type]
        assert resp.has_new(1) is True


# endregion
