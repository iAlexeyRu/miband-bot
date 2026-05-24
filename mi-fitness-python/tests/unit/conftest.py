"""conftest.py —— pytest 公共 fixture。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mi_fitness.auth import XiaomiAuth
from mi_fitness.models import AuthToken


@pytest.fixture
def ssecurity() -> str:
    """测试用 ssecurity（base64 编码的 16 字节密钥）。"""
    return "56nienlY7Ayh4VVJ0ywGGg=="


@pytest.fixture
def auth_token(ssecurity: str) -> AuthToken:
    """构造一个已登录的 AuthToken。"""
    return AuthToken(
        user_id="123456",
        c_user_id="c_test_user",
        service_token="test_service_token",
        ssecurity=ssecurity,
        pass_token="test_pass_token",
        device_id="an_test_device",
    )


@pytest.fixture
def mock_auth(auth_token: AuthToken) -> XiaomiAuth:
    """构造一个已登录的 mock XiaomiAuth 实例。"""
    auth = XiaomiAuth.__new__(XiaomiAuth)
    auth.username = "test"
    auth._password = ""
    auth.token = auth_token
    auth._http = MagicMock()
    auth._ticket_token = ""
    auth._token_path = None
    return auth


# region 常用 API 响应模板
RELATIVE_LIST_RESPONSE = {
    "code": 0,
    "message": "ok",
    "result": {
        "relative_list": [
            {
                "relative_uid": 1452722403,
                "relative_note": "妈妈",
                "relative_icon": "https://example.com/avatar.jpg",
                "latest_data_time": 1717488000,
                "latest_abnormal_record_time": 0,
                "source_tag": 1,
            },
            {
                "relative_uid": 9876543210,
                "relative_note": "爸爸",
                "relative_icon": "",
                "latest_data_time": 1717484400,
                "latest_abnormal_record_time": 0,
                "source_tag": 1,
            },
        ]
    },
}

VERIFY_USER_RESPONSE = {
    "code": 0,
    "message": "ok",
    "result": {
        "userId": 1452722403,
        "nickname": "测试用户",
        "icon": "https://example.com/icon.jpg",
    },
}

INVITE_RESPONSE = {
    "code": 0,
    "message": "ok",
    "result": {"send_ret": 1},
}

DELETE_RESPONSE = {
    "code": 0,
    "message": "ok",
    "result": {"delete_ret": True},
}

OPERATE_INVITE_RESPONSE = {
    "code": 0,
    "message": "ok",
    "result": {"operate_ret": True},
}

INVITE_ID_RESPONSE = {
    "code": 0,
    "message": "ok",
    "result": {"invite_link_id": 467184968352742400},
}

SHARED_TYPES_RESPONSE = {
    "code": 0,
    "message": "ok",
    "result": {
        "keys": ["goal", "heart_rate", "sleep", "steps"],
    },
}

LATEST_DATA_RESPONSE = {
    "code": 0,
    "message": "ok",
    "result": {
        "data_list": [
            {
                "time": 1717488000,
                "key": "goal",
                "value": (
                    '{"date_time":1717488000,"goal_items":['
                    '{"field":2,"target_value":400,"achieved_value":13},'
                    '{"field":1,"target_value":6000,"achieved_value":3716}'
                    "]}"
                ),
            },
            {
                "time": 1717488000,
                "key": "heart_rate",
                "value": '{"time":1717491600,"bpm":84}',
            },
            {
                "time": 1717488000,
                "key": "sleep",
                "value": (
                    '{"date_time":1717488000,"total_duration":436,'
                    '"sleep_stage":3,"sleep_score":86,'
                    '"long_sleep_evaluation":7,"day_sleep_evaluation":0}'
                ),
            },
            {
                "time": 1717488000,
                "key": "steps",
                "value": '{"date_time":1717488000,"steps":3716,"distance":2193,"calories":143,"goal":6000}',
            },
            {
                "time": 1717488000,
                "key": "calories",
                "value": '{"date_time":1717488000,"calories":230,"goal":300}',
            },
            {
                "time": 1717488000,
                "key": "valid_stand",
                "value": '{"date_time":1717488000,"count":7}',
            },
            {
                "time": 1717488000,
                "key": "intensity",
                "value": '{"date_time":1717488000,"duration":15}',
            },
            {
                "time": 1717488000,
                "key": "weight",
                "value": '{"time":1717488000,"weight":65.5,"bmi":22.1}',
            },
            {
                "time": 1717488000,
                "key": "spo2",
                "value": '{"time":1717495200,"spo2":96}',
            },
            {
                "key": "blood_pressure",
            },
        ],
        "latest_data_time": 1717495200,
    },
}

AGGREGATED_HR_RESPONSE = {
    "code": 0,
    "message": "ok",
    "result": {
        "data_list": [
            {
                "sid": "miothealth",
                "tag": "daily_report",
                "key": "heart_rate",
                "time": 1717430400,
                "value": (
                    '{"avg_hr":72,"avg_rhr":62,"max_hr":120,"min_hr":55,'
                    '"latest_hr":{"bpm":75,"time":1717488000},'
                    '"abnormal_hr_count":0,'
                    '"aerobic_hr_zone_duration":30,'
                    '"anaerobic_hr_zone_duration":0,'
                    '"extreme_hr_zone_duration":0,'
                    '"fat_burning_hr_zone_duration":15,'
                    '"warm_up_hr_zone_duration":10}'
                ),
                "update_time": 1717488000,
                "watermark": "w1",
                "source_sid_list": [],
            }
        ],
        "has_more": False,
    },
}

AGGREGATED_SLEEP_RESPONSE = {
    "code": 0,
    "message": "ok",
    "result": {
        "data_list": [
            {
                "sid": "miothealth",
                "tag": "daily_report",
                "key": "sleep",
                "time": 1717430400,
                "value": (
                    '{"total_duration":480,"sleep_score":85,"sleep_stage":4,'
                    '"sleep_deep_duration":120,"sleep_light_duration":200,'
                    '"sleep_rem_duration":100,"sleep_awake_duration":60,'
                    '"long_sleep_evaluation":1,"day_sleep_evaluation":0,'
                    '"avg_hr":60,"max_hr":80,"min_hr":50,"avg_spo2":97,'
                    '"segment_details":[{"bedtime":1717365600,"wake_up_time":1717394400,'
                    '"duration":480,"sleep_deep_duration":120,"sleep_light_duration":200,'
                    '"timezone":28800,"awake_count":2,"sleep_awake_duration":60}]}'
                ),
                "update_time": 1717488000,
                "watermark": "w2",
                "source_sid_list": [],
            }
        ],
        "has_more": False,
    },
}

AGGREGATED_STEPS_RESPONSE = {
    "code": 0,
    "message": "ok",
    "result": {
        "data_list": [
            {
                "sid": "miothealth",
                "tag": "daily_report",
                "key": "steps",
                "time": 1717430400,
                "value": '{"steps":8500,"distance":6200,"calories":320}',
                "update_time": 1717488000,
                "watermark": "w3",
                "source_sid_list": [],
            }
        ],
        "has_more": False,
    },
}

FITNESS_WEIGHT_RESPONSE = {
    "code": 0,
    "message": "ok",
    "result": {
        "data_list": [
            {
                "sid": "xiaomiwear_app_manually",
                "tag": "",
                "key": "weight",
                "time": 1773753142,
                "value": '{"bmi":16.97531,"time":1773753142,"weight":55.0}',
                "update_time": 1773753142,
                "watermark": "w5",
                "source_sid_list": [],
            }
        ],
        "has_more": False,
    },
}

FITNESS_BLOOD_PRESSURE_RESPONSE = {
    "code": 0,
    "message": "ok",
    "result": {
        "data_list": [
            {
                "sid": "xiaomiwear_app_manually",
                "tag": "",
                "key": "blood_pressure",
                "time": 1773753098,
                "value": (
                    '{"systolic_pressure":33,"diastolic_pressure":30,"pulse":60,"time":1773753098}'
                ),
                "update_time": 1773753098,
                "watermark": "w6",
                "source_sid_list": [],
            }
        ],
        "has_more": False,
    },
}

FAMILY_MEMBER_RESPONSE = {
    "code": 0,
    "message": "ok",
    "result": {
        "family_user_list": [
            {"userId": 123, "nickname": "家人1"},
        ]
    },
}

MESSAGE_LIST_RESPONSE = {
    "code": 0,
    "message": "ok",
    "result": {
        "messages": [
            {
                "msg_id": 152824796151809,
                "module": 1,
                "type": 1,
                "receiver": 3188565001,
                "sender": 1452722403,
                "extra_data": '{"invite_id":4777767,"auth_data":["heart_rate","sleep"],"nick_name":"测试用户","icon":"https://example.com/avatar.jpg"}',
                "is_new": 2,
                "data_status": 0,
                "create_time": 1772628283,
                "last_modify": 1772628283,
            },
            {
                "msg_id": 152821515157506,
                "module": 1,
                "type": 5,
                "receiver": 3188565001,
                "sender": 1452722403,
                "extra_data": '{"nick_name":"测试用户","icon":"https://example.com/avatar.jpg"}',
                "is_new": 2,
                "data_status": 1,
                "create_time": 1772625154,
                "last_modify": 1772625154,
            },
        ],
        "msg_total": 2,
    },
}

CHECK_NEW_MSG_RESPONSE = {
    "code": 0,
    "message": "ok",
    "result": [{"module": 1, "is_new": True}],
}

CHECK_NO_NEW_MSG_RESPONSE = {
    "code": 0,
    "message": "ok",
    "result": [{"module": 1, "is_new": False}],
}
# endregion
