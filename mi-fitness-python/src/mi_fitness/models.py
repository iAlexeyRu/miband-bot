"""健康数据结构。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import IntEnum
from functools import cached_property
from typing import Any, TypeVar

from pydantic import AliasChoices, BaseModel, Field, ValidationError, field_validator

_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _ts_to_datetime(ts: int) -> datetime | None:
    """将秒级时间戳转为 UTC datetime，0 返回 None。"""
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=UTC)


def _coerce_bool(value: Any) -> bool:
    """将接口返回的 bool / int / str 统一归一化为布尔值。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", ""}:
            return False
    return bool(value)


def _coerce_int(value: Any, default: int = 0) -> int:
    """尽力将接口返回值转为整数。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_optional_int(value: Any) -> int | None:
    """尽力将接口返回值转为整数，失败时返回 None。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_dict(value: Any) -> dict[str, Any]:
    """仅保留 dict 结果，其余统一视为空对象。"""
    return value if isinstance(value, dict) else {}


def _coerce_dict_list(value: Any) -> list[dict[str, Any]]:
    """将单个对象或列表中的 dict 条目安全归一化。"""
    if isinstance(value, dict):
        candidates = [value]
    elif isinstance(value, (list, tuple)):
        candidates = list(value)
    else:
        return []
    return [item for item in candidates if isinstance(item, dict) and item]


def _coerce_str_list(value: Any) -> list[str]:
    """仅保留非空字符串列表。"""
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _parse_model_list(value: Any, model: type[_ModelT]) -> list[_ModelT]:
    """安全解析模型列表，跳过明显损坏的条目。"""
    parsed: list[_ModelT] = []
    for item in _coerce_dict_list(value):
        try:
            parsed.append(model.model_validate(item))
        except ValidationError:
            continue
    return parsed


def _parse_model(value: Any, model: type[_ModelT]) -> _ModelT | None:
    """安全解析单个模型，失败时返回 None。"""
    try:
        return model.model_validate(value)
    except ValidationError:
        return None


class _DictResultResponse(BaseModel):
    """result 应为 dict 的响应基类。"""

    code: int = 0
    message: str = ""
    result: dict[str, Any] = Field(default_factory=dict)

    @field_validator("result", mode="before")
    @classmethod
    def _normalize_result(cls, value: Any) -> dict[str, Any]:
        return _coerce_dict(value)


class _ListResultResponse(BaseModel):
    """result 应为列表的响应基类。"""

    code: int = 0
    message: str = ""
    result: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("result", mode="before")
    @classmethod
    def _normalize_result(cls, value: Any) -> list[dict[str, Any]]:
        return _coerce_dict_list(value)


# region Token 持久化
class AuthToken(BaseModel):
    """登录凭证，可序列化用于持久化存储。

    Attributes:
        user_id: 小米用户 ID (userId)。
        c_user_id: cUserId（cookie 认证用）。
        service_token: serviceToken（cookie 认证用）。
        ssecurity: 加密密钥（RC4 加解密用）。
        pass_token: passToken（可用于 STS 交换）。
        device_id: 设备标识符。
    """

    user_id: str = ""
    c_user_id: str = ""
    service_token: str = ""
    ssecurity: str = ""
    pass_token: str = ""
    device_id: str = ""


# endregion


# region 亲友
class FamilyMember(BaseModel):
    """亲友信息（来自 get_relative_list 响应）。

    Attributes:
        relative_uid: 亲友的小米用户 UID（整数）。
        relative_note: 备注名。
        relative_icon: 头像 URL。
        latest_data_time: 最新数据时间戳。
        latest_abnormal_record_time: 最新异常记录时间戳。
        source_tag: 来源标记。
    """

    relative_uid: int
    relative_note: str = ""
    relative_icon: str = ""
    latest_data_time: int = 0
    latest_abnormal_record_time: int | None = 0
    source_tag: int = 0

    def __str__(self) -> str:
        return f"{self.relative_note or '未命名'} (UID: {self.relative_uid})"


# endregion


# region 最新心率
class LatestHeartRate(BaseModel):
    """实时心率点（来自心率聚合数据或 get_latest_data 的 latest_hr 字段）。

    Attributes:
        bpm: 心率（次/分）。
        time: 采集时间戳。
    """

    bpm: int = 0
    time: int = 0


# endregion


# region 心率
class HeartRateData(BaseModel):
    """心率每日汇总（来自 get_aggregated_data key=heart_rate）。

    Attributes:
        time: 数据时间戳（当天 0 点）。
        avg_hr: 日均心率。
        avg_rhr: 日均静息心率。
        max_hr: 最大心率。
        min_hr: 最小心率。
        latest_hr: 最新一次心率采样。
        abnormal_hr_count: 异常心率次数。
        aerobic_hr_zone_duration: 有氧心率区间时长（分钟）。
        anaerobic_hr_zone_duration: 无氧心率区间时长（分钟）。
        extreme_hr_zone_duration: 极限心率区间时长（分钟）。
        fat_burning_hr_zone_duration: 燃脂心率区间时长（分钟）。
        warm_up_hr_zone_duration: 热身心率区间时长（分钟）。
    """

    time: int = 0
    avg_hr: int = 0
    avg_rhr: int = 0
    max_hr: int = 0
    min_hr: int = 0
    latest_hr: LatestHeartRate | None = None
    abnormal_hr_count: int = 0
    aerobic_hr_zone_duration: int = 0
    anaerobic_hr_zone_duration: int = 0
    extreme_hr_zone_duration: int = 0
    fat_burning_hr_zone_duration: int = 0
    warm_up_hr_zone_duration: int = 0

    def __str__(self) -> str:
        return (
            f"HeartRate(avg={self.avg_hr}bpm, resting={self.avg_rhr}, "
            f"range={self.min_hr}-{self.max_hr})"
        )

    @property
    def at(self) -> datetime | None:
        """数据时间（UTC datetime）。"""
        return _ts_to_datetime(self.time)


# endregion


# region 睡眠片段
class SleepSegment(BaseModel):
    """睡眠片段（来自 sleep value 的 segment_details）。

    Attributes:
        bedtime: 入睡时间戳。
        wake_up_time: 醒来时间戳。
        duration: 持续时长（分钟）。
        sleep_deep_duration: 深睡时长（分钟）。
        sleep_light_duration: 浅睡时长（分钟）。
        timezone: 时区偏移。
        awake_count: 醒来次数。
        sleep_awake_duration: 清醒时长（分钟）。
    """

    bedtime: int = 0
    wake_up_time: int = 0
    duration: int = 0
    sleep_deep_duration: int = 0
    sleep_light_duration: int = 0
    timezone: int = 0
    awake_count: int = 0
    sleep_awake_duration: int = 0


# endregion


# region 睡眠
class SleepData(BaseModel):
    """睡眠每日汇总（来自 get_aggregated_data key=sleep）。

    Attributes:
        time: 数据时间戳。
        total_duration: 总睡眠时长（分钟）。
        sleep_score: 睡眠评分（0-100）。
        sleep_stage: 睡眠阶段数。
        sleep_deep_duration: 深睡时长（分钟）。
        sleep_light_duration: 浅睡时长（分钟）。
        sleep_rem_duration: REM 时长（分钟）。
        sleep_awake_duration: 清醒时长（分钟）。
        long_sleep_evaluation: 长期睡眠评估。
        day_sleep_evaluation: 日间小睡评估。
        avg_hr: 睡眠平均心率。
        max_hr: 睡眠最大心率。
        min_hr: 睡眠最小心率。
        avg_spo2: 睡眠平均血氧。
        segment_details: 睡眠片段列表。
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    total_duration: int = 0
    sleep_score: int = 0
    sleep_stage: int = 0
    sleep_deep_duration: int = 0
    sleep_light_duration: int = 0
    sleep_rem_duration: int = 0
    sleep_awake_duration: int = 0
    long_sleep_evaluation: int = 0
    day_sleep_evaluation: int = 0
    avg_hr: int = 0
    max_hr: int = 0
    min_hr: int = 0
    avg_spo2: int = 0
    segment_details: list[SleepSegment] = Field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"Sleep({self.total_duration}min, score={self.sleep_score}/100, "
            f"deep={self.sleep_deep_duration}min, light={self.sleep_light_duration}min, "
            f"rem={self.sleep_rem_duration}min)"
        )

    @property
    def at(self) -> datetime | None:
        """数据时间（UTC datetime）。"""
        return _ts_to_datetime(self.time)


# endregion


# region 步数
class StepData(BaseModel):
    """步数每日汇总（来自 get_aggregated_data key=steps）。

    Attributes:
        time: 数据时间戳。
        steps: 步数。
        distance: 距离（米）。
        calories: 消耗卡路里。
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    steps: int = 0
    distance: int = 0
    calories: int = 0
    goal: int = 0

    def __str__(self) -> str:
        return f"Steps({self.steps}步, {self.distance}m, {self.calories}cal)"

    @property
    def at(self) -> datetime | None:
        """数据时间（UTC datetime）。"""
        return _ts_to_datetime(self.time)


# endregion


# region 体重
class WeightData(BaseModel):
    """体重数据（来自 get_latest_data / get_fitness_data key=weight）。

    Attributes:
        time: 数据时间戳。
        weight: 体重（千克）。
        bmi: BMI 指数。
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    weight: float = 0.0
    bmi: float = 0.0

    def __str__(self) -> str:
        return f"Weight({self.weight}kg, BMI={self.bmi})"

    @property
    def at(self) -> datetime | None:
        """数据时间（UTC datetime）。"""
        return _ts_to_datetime(self.time)


# endregion


# region 血压
class BloodPressureData(BaseModel):
    """血压数据（来自 get_latest_data / get_fitness_data key=blood_pressure）。

    Attributes:
        time: 数据时间戳。
        systolic: 收缩压（高压 mmHg）。
        diastolic: 舒张压（低压 mmHg）。
        pulse: 脉搏（bpm）。
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    systolic: int = Field(default=0, validation_alias=AliasChoices("systolic", "systolic_pressure"))
    diastolic: int = Field(
        default=0, validation_alias=AliasChoices("diastolic", "diastolic_pressure")
    )
    pulse: int | None = None

    def __str__(self) -> str:
        base = f"BloodPressure({self.systolic}/{self.diastolic} mmHg)"
        return f"{base}, pulse={self.pulse}" if self.pulse is not None else base

    @property
    def at(self) -> datetime | None:
        """数据时间（UTC datetime）。"""
        return _ts_to_datetime(self.time)


# endregion


# region 最新快照指标
class GoalMetric(IntEnum):
    """活力指标中的单项目标类型。"""

    STEPS = 1
    CALORIES = 2
    INTENSITY = 4

    @classmethod
    def from_field(cls, field: int) -> GoalMetric | None:
        """将接口返回的 field 编号映射为已知目标类型。"""
        try:
            return cls(field)
        except ValueError:
            return None

    @property
    def key(self) -> str:
        """稳定的英文键名，适合代码分支和序列化。"""
        return {
            GoalMetric.STEPS: "steps",
            GoalMetric.CALORIES: "calories",
            GoalMetric.INTENSITY: "intensity",
        }[self]

    @property
    def label(self) -> str:
        """与 App 文案接近的展示名称。"""
        return {
            GoalMetric.STEPS: "步数",
            GoalMetric.CALORIES: "卡路里",
            GoalMetric.INTENSITY: "中高强度",
        }[self]


class GoalItem(BaseModel):
    """单个健康目标条目。

    Attributes:
        field: 目标类型编号。
        target_value: 目标值。
        achieved_value: 已完成值。
    """

    field: int = 0
    target_value: int | float = 0
    achieved_value: int | float = 0

    @property
    def metric(self) -> GoalMetric | None:
        """已知目标类型；未知 field 返回 None。"""
        return GoalMetric.from_field(self.field)

    @property
    def metric_key(self) -> str:
        """目标键名；未知类型保留 field 以便继续排查。"""
        metric = self.metric
        return metric.key if metric is not None else f"unknown:{self.field}"

    @property
    def metric_label(self) -> str:
        """目标展示名；未知类型保留原始编号。"""
        metric = self.metric
        return metric.label if metric is not None else f"未知目标({self.field})"


class GoalData(BaseModel):
    """每日目标完成情况（来自 get_latest_data key=goal）。

    Attributes:
        time: 目标所属日期时间戳。
        goal_items: 当日所有目标项。

    便捷属性:
        ``steps_goal`` / ``calories_goal`` / ``intensity_goal`` 会返回对应的目标条目。
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    goal_items: list[GoalItem] = Field(default_factory=list)

    @field_validator("goal_items", mode="before")
    @classmethod
    def _normalize_goal_items(cls, value: Any) -> list[GoalItem]:
        return _parse_model_list(value, GoalItem)

    def __str__(self) -> str:
        return f"GoalData({len(self.goal_items)} items)"

    @cached_property
    def items_by_field(self) -> dict[int, GoalItem]:
        """按原始 field 编号索引目标项。"""
        return {item.field: item for item in self.goal_items}

    @property
    def available_metrics(self) -> list[GoalMetric]:
        """当前响应中出现的已知目标类型。"""
        metrics: list[GoalMetric] = []
        for item in self.goal_items:
            if item.metric is not None:
                metrics.append(item.metric)
        return metrics

    @property
    def unknown_goal_items(self) -> list[GoalItem]:
        """当前响应中未识别的目标项。"""
        return [item for item in self.goal_items if item.metric is None]

    def get_item(self, metric: GoalMetric | int) -> GoalItem | None:
        """按目标类型读取对应条目。"""
        return self.items_by_field.get(int(metric))

    @property
    def steps_goal(self) -> GoalItem | None:
        """步数目标。"""
        return self.get_item(GoalMetric.STEPS)

    @property
    def calories_goal(self) -> GoalItem | None:
        """卡路里目标。"""
        return self.get_item(GoalMetric.CALORIES)

    @property
    def intensity_goal(self) -> GoalItem | None:
        """中高强度活动目标。"""
        return self.get_item(GoalMetric.INTENSITY)

    @property
    def at(self) -> datetime | None:
        """数据时间（UTC datetime）。"""
        return _ts_to_datetime(self.time)


class CaloriesData(BaseModel):
    """每日活动卡路里（来自 get_latest_data key=calories）。

    Attributes:
        time: 数据时间戳。
        calories: 已消耗活动卡路里。
        goal: 卡路里目标值。
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    calories: int = 0
    goal: int = 0

    def __str__(self) -> str:
        return f"Calories({self.calories} cal, goal={self.goal})"

    @property
    def at(self) -> datetime | None:
        """数据时间（UTC datetime）。"""
        return _ts_to_datetime(self.time)


class ValidStandData(BaseModel):
    """每日有效站立次数（来自 get_latest_data key=valid_stand）。

    Attributes:
        time: 数据时间戳。
        count: 有效站立次数。
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    count: int = 0

    def __str__(self) -> str:
        return f"ValidStand({self.count})"

    @property
    def at(self) -> datetime | None:
        """数据时间（UTC datetime）。"""
        return _ts_to_datetime(self.time)


class IntensityData(BaseModel):
    """每日中高强度活动时长（来自 get_latest_data key=intensity）。

    Attributes:
        time: 数据时间戳。
        duration: 中高强度活动时长（分钟）。
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    duration: int = 0

    def __str__(self) -> str:
        return f"Intensity({self.duration} min)"

    @property
    def at(self) -> datetime | None:
        """数据时间（UTC datetime）。"""
        return _ts_to_datetime(self.time)


class Spo2Data(BaseModel):
    """最新血氧数据（来自 get_latest_data key=spo2）。

    Attributes:
        time: 测量时间戳。
        spo2: 血氧百分比。
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    spo2: int = 0

    def __str__(self) -> str:
        return f"Spo2({self.spo2}%)"

    @property
    def at(self) -> datetime | None:
        """数据时间（UTC datetime）。"""
        return _ts_to_datetime(self.time)


class Spo2SummaryData(BaseModel):
    """每日血氧摘要（来自 get_aggregated_data key=spo2）。

    Attributes:
        time: 数据时间戳。
        avg_spo2: 平均血氧。
        max_spo2: 最高血氧。
        min_spo2: 最低血氧。
        lack_spo2_count: 低血氧次数。
        latest_spo2: 当日最近一次血氧采样。
    """

    time: int = Field(default=0, validation_alias=AliasChoices("time", "date_time"))
    avg_spo2: int = 0
    max_spo2: int = 0
    min_spo2: int = 0
    lack_spo2_count: int = 0
    latest_spo2: Spo2Data | None = None

    def __str__(self) -> str:
        return (
            f"Spo2Summary(avg={self.avg_spo2}%, range={self.min_spo2}-{self.max_spo2}, "
            f"lack={self.lack_spo2_count})"
        )

    @property
    def at(self) -> datetime | None:
        """数据时间（UTC datetime）。"""
        return _ts_to_datetime(self.time)


# endregion


# region 用户验证
class VerifiedUserInfo(BaseModel):
    """verify_userinfo_by_id 响应中的用户信息。

    Attributes:
        user_id: 小米用户 UID。
        nickname: 昵称。
        icon: 头像 URL。
    """

    user_id: int = Field(alias="userId", default=0)
    nickname: str = ""
    icon: str = ""

    model_config = {"populate_by_name": True}


# endregion


# region 最新数据项
class LatestDataItem(BaseModel):
    """get_latest_data 响应中的单条数据项。

    value 字段是 JSON 字符串，需要根据 key 解析为对应类型。

    Attributes:
        time: 数据时间戳。
        key: 数据类型（heart_rate / sleep / steps / weight / blood_pressure 等）。
        value: JSON 字符串或数值。
    """

    time: int = 0
    key: str = ""
    value: str | int | float = ""

    @field_validator("value", mode="before")
    @classmethod
    def _normalize_value(cls, value: Any) -> str | int | float:
        """确保 dict/list 形式的 value 也能被统一解析。"""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, (str, int, float)):
            return value
        return ""

    def parse_value(self) -> dict[str, Any] | int | float:
        """将 value 字段从 JSON 字符串解析为字典。

        Returns:
            解析后的字典或原始数值。
        """
        if isinstance(self.value, (int, float)):
            return self.value
        try:
            parsed = json.loads(self.value)
        except (json.JSONDecodeError, TypeError):
            return {}
        if isinstance(parsed, (dict, int, float)):
            return parsed
        return {}

    def _parse_dict_value(self) -> dict[str, Any]:
        """将 value 解析为字典，失败时返回空对象。"""
        parsed = self.parse_value()
        return parsed if isinstance(parsed, dict) else {}

    def as_goal(self) -> GoalData | None:
        """解析为目标完成数据。"""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        return _parse_model(data, GoalData)

    def as_heart_rate(self) -> LatestHeartRate | None:
        """解析为最新一次心率采样。"""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        return _parse_model(data, LatestHeartRate)

    def as_sleep(self) -> SleepData | None:
        """解析为最新睡眠摘要。"""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        segments = data.pop("segment_details", [])
        data["segment_details"] = _parse_model_list(segments, SleepSegment)
        return _parse_model(data, SleepData)

    def as_steps(self) -> StepData | None:
        """解析为最新步数摘要。"""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        return _parse_model(data, StepData)

    def as_weight(self) -> WeightData | None:
        """解析为最新体重。"""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        return _parse_model(data, WeightData)

    def as_blood_pressure(self) -> BloodPressureData | None:
        """解析为最新血压。"""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        return _parse_model(data, BloodPressureData)

    def as_calories(self) -> CaloriesData | None:
        """解析为最新卡路里摘要。"""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        return _parse_model(data, CaloriesData)

    def as_valid_stand(self) -> ValidStandData | None:
        """解析为最新有效站立统计。"""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        return _parse_model(data, ValidStandData)

    def as_intensity(self) -> IntensityData | None:
        """解析为最新中高强度活动时长。"""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        return _parse_model(data, IntensityData)

    def as_spo2(self) -> Spo2Data | None:
        """解析为最新血氧。"""
        data = self._parse_dict_value()
        if not data:
            return None
        data.setdefault("time", self.time)
        return _parse_model(data, Spo2Data)


# endregion


# region 聚合数据项
class AggregatedDataItem(BaseModel):
    """get_aggregated_data 响应中的单条数据项。

    Attributes:
        sid: 数据来源 SID。
        tag: 数据标签（如 daily_report）。
        key: 数据类型。
        time: 数据时间戳。
        value: JSON 字符串值。
        update_time: 更新时间戳。
        watermark: 水印（增量同步用）。
        source_sid_list: 数据来源列表。
    """

    sid: str = ""
    tag: str = ""
    key: str = ""
    time: int = 0
    value: str = ""
    update_time: int = 0
    watermark: str = ""
    source_sid_list: list[str] = Field(default_factory=list)

    @field_validator("watermark", mode="before")
    @classmethod
    def _stringify_watermark(cls, v: Any) -> str:
        """API 有时返回 int 类型的 watermark。"""
        return str(v) if v is not None else ""

    @field_validator("value", mode="before")
    @classmethod
    def _stringify_value(cls, v: Any) -> str:
        """确保 value 始终是字符串（API 可能返回 dict）。"""
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        return str(v) if v is not None else ""

    def parse_value(self) -> dict[str, Any]:
        """将 value 字段从 JSON 字符串解析为字典。"""
        try:
            parsed = json.loads(self.value)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def as_heart_rate(self) -> HeartRateData:
        """解析为心率数据。"""
        data = self.parse_value()
        data["time"] = self.time
        latest = data.get("latest_hr")
        if isinstance(latest, dict):
            data["latest_hr"] = LatestHeartRate.model_validate(latest)
        elif latest is not None:
            data["latest_hr"] = None
        return HeartRateData.model_validate(data)

    def as_sleep(self) -> SleepData:
        """解析为睡眠数据。"""
        data = self.parse_value()
        data["time"] = self.time
        segments = data.pop("segment_details", [])
        data["segment_details"] = _parse_model_list(segments, SleepSegment)
        return SleepData.model_validate(data)

    def as_steps(self) -> StepData:
        """解析为步数数据。"""
        data = self.parse_value()
        data["time"] = self.time
        return StepData.model_validate(data)

    def as_weight(self) -> WeightData:
        """解析为体重历史数据。"""
        data = self.parse_value()
        data["time"] = self.time
        return WeightData.model_validate(data)

    def as_blood_pressure(self) -> BloodPressureData:
        """解析为血压历史数据。"""
        data = self.parse_value()
        data["time"] = self.time
        return BloodPressureData.model_validate(data)

    def as_calories(self) -> CaloriesData:
        """解析为卡路里数据。"""
        data = self.parse_value()
        data["time"] = self.time
        return CaloriesData.model_validate(data)

    def as_valid_stand(self) -> ValidStandData:
        """解析为有效站立数据。"""
        data = self.parse_value()
        data["time"] = self.time
        return ValidStandData.model_validate(data)

    def as_intensity(self) -> IntensityData:
        """解析为中高强度活动时长数据。"""
        data = self.parse_value()
        data["time"] = self.time
        return IntensityData.model_validate(data)

    def as_spo2(self) -> Spo2SummaryData:
        """解析为血氧摘要数据。"""
        data = self.parse_value()
        data["time"] = self.time
        latest = data.get("latest_spo2")
        if isinstance(latest, dict):
            data["latest_spo2"] = _parse_model(latest, Spo2Data)
        elif latest is not None:
            data["latest_spo2"] = None
        return Spo2SummaryData.model_validate(data)


# endregion


# region 每日摘要
class DailySummary(BaseModel):
    """每日健康数据摘要（由 get_daily_summary 返回）。

    Attributes:
        date: 查询日期（ISO 格式）。
        relative_uid: 亲友 UID。
        heart_rate: 心率汇总数据。
        sleep: 睡眠汇总数据。
        steps: 步数汇总数据。
    """

    date: str = ""
    relative_uid: int = 0
    heart_rate: HeartRateData | None = None
    sleep: SleepData | None = None
    steps: StepData | None = None

    def __str__(self) -> str:
        parts = [f"DailySummary({self.date}, UID={self.relative_uid}"]
        if self.heart_rate:
            parts.append(f"hr={self.heart_rate.avg_hr}bpm")
        if self.sleep:
            parts.append(f"sleep={self.sleep.total_duration}min")
        if self.steps:
            parts.append(f"steps={self.steps.steps}")
        return ", ".join(parts) + ")"


# endregion


# region 最新快照
class LatestDataSnapshot(BaseModel):
    """最新健康快照。

    将 get_latest_data 的异构 data_list 收敛为固定字段，未知 key 或解析失败的 payload
    保留到 extras，避免上层因为单条脏数据失去整份快照。
    """

    updated_time: int = 0
    goal: GoalData | None = None
    heart_rate: LatestHeartRate | None = None
    sleep: SleepData | None = None
    blood_pressure: BloodPressureData | None = None
    steps: StepData | None = None
    calories: CaloriesData | None = None
    valid_stand: ValidStandData | None = None
    intensity: IntensityData | None = None
    weight: WeightData | None = None
    spo2: Spo2Data | None = None
    extras: dict[str, dict[str, Any] | int | float] = Field(default_factory=dict)

    @classmethod
    def from_items(
        cls,
        items: list[LatestDataItem],
        *,
        updated_time: int = 0,
    ) -> LatestDataSnapshot:
        """从原始 data_list 构建类型化快照。"""
        payload: dict[str, Any] = {"updated_time": updated_time}
        extras: dict[str, dict[str, Any] | int | float] = {}
        parsers = {
            "goal": LatestDataItem.as_goal,
            "heart_rate": LatestDataItem.as_heart_rate,
            "sleep": LatestDataItem.as_sleep,
            "blood_pressure": LatestDataItem.as_blood_pressure,
            "steps": LatestDataItem.as_steps,
            "calories": LatestDataItem.as_calories,
            "valid_stand": LatestDataItem.as_valid_stand,
            "intensity": LatestDataItem.as_intensity,
            "weight": LatestDataItem.as_weight,
            "spo2": LatestDataItem.as_spo2,
        }

        for item in items:
            parser = parsers.get(item.key)
            raw_value = item.parse_value()
            if parser is None:
                extras[item.key] = raw_value
                continue

            parsed = parser(item)
            if parsed is not None:
                payload[item.key] = parsed
                continue

            if raw_value not in ({}, "", 0, 0.0):
                extras[item.key] = raw_value

        return cls(**payload, extras=extras)

    def __str__(self) -> str:
        keys = ", ".join(self.available_keys) or "empty"
        return f"LatestDataSnapshot({keys})"

    @property
    def at(self) -> datetime | None:
        """快照更新时间（UTC datetime）。"""
        return _ts_to_datetime(self.updated_time)

    @property
    def available_keys(self) -> list[str]:
        """当前快照中可用的数据键。"""
        known_keys = [
            "goal",
            "heart_rate",
            "sleep",
            "blood_pressure",
            "steps",
            "calories",
            "valid_stand",
            "intensity",
            "weight",
            "spo2",
        ]
        keys = [key for key in known_keys if getattr(self, key) is not None]
        keys.extend(sorted(self.extras))
        return keys


# endregion


# region API 响应包装
class RelativeListResponse(_DictResultResponse):
    """get_relative_list 响应。"""

    @property
    def relatives(self) -> list[FamilyMember]:
        """解析亲友列表。"""
        return _parse_model_list(self.result.get("relative_list"), FamilyMember)


class LatestDataResponse(_DictResultResponse):
    """get_latest_data 响应。"""

    @property
    def data_items(self) -> list[LatestDataItem]:
        """解析数据项列表。"""
        return _parse_model_list(self.result.get("data_list"), LatestDataItem)

    @property
    def latest_data_time(self) -> int:
        """最新数据更新时间。"""
        return _coerce_int(self.result.get("latest_data_time"), default=0)

    @property
    def snapshot(self) -> LatestDataSnapshot:
        """解析为类型化快照。"""
        return LatestDataSnapshot.from_items(self.data_items, updated_time=self.latest_data_time)


class AggregatedDataResponse(_DictResultResponse):
    """get_aggregated_data / get_fitness_data 响应。"""

    @property
    def data_items(self) -> list[AggregatedDataItem]:
        """解析数据项列表。"""
        return _parse_model_list(self.result.get("data_list"), AggregatedDataItem)

    @property
    def has_more(self) -> bool:
        """是否有更多数据。"""
        return _coerce_bool(self.result.get("has_more", False))

    @property
    def next_key(self) -> str:
        """下一页的起始 key。"""
        value = self.result.get("next_key", "")
        return str(value) if value is not None else ""


# endregion


# region 亲友管理 API 响应
class VerifyUserResponse(_DictResultResponse):
    """verify_userinfo_by_id 响应。"""

    @property
    def user_info(self) -> VerifiedUserInfo | None:
        """解析用户信息，未找到时返回 None。"""
        if not self.result or not self.result.get("userId"):
            return None
        return VerifiedUserInfo.model_validate(self.result)


class InviteResponse(_DictResultResponse):
    """send_invite 响应。"""

    @property
    def success(self) -> bool:
        """邀请是否发送成功。"""
        return _coerce_int(self.result.get("send_ret"), default=0) == 1


class OperateInviteResponse(_DictResultResponse):
    """operate_invite 响应（同意/拒绝邀请）。"""

    @property
    def success(self) -> bool:
        """操作是否成功。"""
        return _coerce_bool(self.result.get("operate_ret"))


class DeleteRelativeResponse(_DictResultResponse):
    """delete_relative 响应。"""

    @property
    def success(self) -> bool:
        """删除是否成功。"""
        return _coerce_bool(self.result.get("delete_ret"))


class SharedDataTypesResponse(_DictResultResponse):
    """get_shared_data_types 响应。"""

    @property
    def keys(self) -> list[str]:
        """可共享的数据类型列表。"""
        return _coerce_str_list(self.result.get("keys"))


class InviteUniqueIdResponse(_DictResultResponse):
    """get_invite_unique_id 响应。"""

    @property
    def invite_link_id(self) -> int:
        """二维码邀请链接 ID。"""
        return _coerce_int(self.result.get("invite_link_id"), default=0)


class FamilyMemberResponse(_DictResultResponse):
    """get_family_member 响应。"""

    @property
    def family_user_list(self) -> list[dict[str, Any]]:
        """家庭成员列表（原始字典）。"""
        return _coerce_dict_list(self.result.get("family_user_list"))


# endregion


# region 消息
class InviteMessage(BaseModel):
    """亲友邀请消息（来自 get_msg_list 响应）。

    Attributes:
        msg_id: 消息 ID（operate_invite 用）。
        module: 消息模块（1=亲友）。
        type: 消息类型（1=待处理邀请，5=历史通知）。
        receiver: 接收方 UID。
        sender: 发送方 UID。
        extra_data: JSON 字符串，包含 invite_id、nick_name、icon 等。
        is_new: 是否新消息。
        data_status: 数据状态（0=待处理，1=已处理）。
        create_time: 创建时间戳。
    """

    msg_id: int = 0
    module: int = 0
    type: int = 0
    receiver: int = 0
    sender: int = 0
    extra_data: str = ""
    is_new: int = 0
    data_status: int = 0
    create_time: int = 0
    last_modify: int = 0

    @field_validator("extra_data", mode="before")
    @classmethod
    def _normalize_extra_data(cls, value: Any) -> str:
        """确保 extra_data 在解析前始终是 JSON 字符串。"""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value) if value is not None else ""

    @cached_property
    def _parsed_extra(self) -> dict[str, Any]:
        """解析 extra_data JSON（缓存结果）。"""
        try:
            parsed = json.loads(self.extra_data)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @property
    def invite_id(self) -> int | None:
        """解析 extra_data 中的 invite_id（仅 type=1 时存在）。"""
        return _coerce_optional_int(self._parsed_extra.get("invite_id"))

    @property
    def nick_name(self) -> str:
        """解析 extra_data 中的昵称。"""
        return self._parsed_extra.get("nick_name", "")

    @property
    def icon(self) -> str:
        """解析 extra_data 中的头像 URL。"""
        return self._parsed_extra.get("icon", "")

    @property
    def is_pending(self) -> bool:
        """是否为待处理的邀请。"""
        return self.type == 1 and self.data_status == 0


class MessageListResponse(_DictResultResponse):
    """get_msg_list 响应。"""

    @property
    def messages(self) -> list[InviteMessage]:
        """消息列表。"""
        return _parse_model_list(self.result.get("messages"), InviteMessage)

    @property
    def msg_total(self) -> int:
        """消息总数。"""
        return _coerce_int(self.result.get("msg_total"), default=0)


class CheckNewMsgResponse(_ListResultResponse):
    """check_new_msg 响应。"""

    def has_new(self, module: int = 1) -> bool:
        """指定 module 是否有新消息。"""
        for item in self.result:
            if _coerce_int(item.get("module"), default=0) == module and _coerce_bool(
                item.get("is_new")
            ):
                return True
        return False


# endregion
