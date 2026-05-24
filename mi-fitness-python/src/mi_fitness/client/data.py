"""健康数据查询（心率、睡眠、步数等）。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, TypeVar

from pydantic import ValidationError

from mi_fitness.const import (
    DATA_KEY_BLOOD_PRESSURE,
    DATA_KEY_CALORIES,
    DATA_KEY_GOAL,
    DATA_KEY_HEART_RATE,
    DATA_KEY_INTENSITY,
    DATA_KEY_SLEEP,
    DATA_KEY_SPO2,
    DATA_KEY_STEPS,
    DATA_KEY_VALID_STAND,
    DATA_KEY_WEIGHT,
    DATA_TAG_DAILY_REPORT,
    RELATIVES_AGGREGATED_DATA_PATH,
    RELATIVES_FITNESS_DATA_PATH,
    RELATIVES_LATEST_DATA_PATH,
)
from mi_fitness.exceptions import DataNotSharedError, DataOutOfSharedTimeScopeError
from mi_fitness.models import (
    AggregatedDataItem,
    AggregatedDataResponse,
    BloodPressureData,
    CaloriesData,
    DailySummary,
    GoalData,
    HeartRateData,
    IntensityData,
    LatestDataItem,
    LatestDataResponse,
    LatestDataSnapshot,
    SleepData,
    Spo2Data,
    Spo2SummaryData,
    StepData,
    ValidStandData,
    WeightData,
)

if TYPE_CHECKING:
    from mi_fitness.client.api import MiHealthClient

_SeriesDataT = TypeVar("_SeriesDataT")
_LatestMetricT = TypeVar(
    "_LatestMetricT",
    GoalData,
    BloodPressureData,
    CaloriesData,
    IntensityData,
    Spo2Data,
    ValidStandData,
    WeightData,
)


async def _get_first_shared_or_none(
    fetcher: Callable[[], Awaitable[list[_SeriesDataT]]],
) -> _SeriesDataT | None:
    """摘要接口专用：未共享时返回 None，其余异常继续向上抛。"""
    try:
        result = await fetcher()
    except DataOutOfSharedTimeScopeError:
        raise
    except DataNotSharedError:
        return None
    return result[0] if result else None


# region 最新数据
async def _get_latest_response(client: MiHealthClient, relative_uid: int) -> LatestDataResponse:
    """获取并解析最新数据响应。"""
    resp = await client._request(
        "GET",
        RELATIVES_LATEST_DATA_PATH,
        params={"relative_uid": relative_uid},
    )
    return LatestDataResponse(**resp)


async def get_latest_items(client: MiHealthClient, relative_uid: int) -> list[LatestDataItem]:
    """获取亲友的原始最新数据项列表。"""
    return (await _get_latest_response(client, relative_uid)).data_items


async def get_latest_data(client: MiHealthClient, relative_uid: int) -> LatestDataSnapshot:
    """获取亲友的最新数据快照（强类型聚合视图）。"""
    return (await _get_latest_response(client, relative_uid)).snapshot


async def _get_latest_metric(
    client: MiHealthClient,
    relative_uid: int,
    *,
    attr_name: str,
    shared_key: str,
) -> _LatestMetricT | None:
    """读取最新快照中的单项数据，并在未共享时抛出明确异常。"""
    latest = await get_latest_data(client, relative_uid)
    value = getattr(latest, attr_name)
    if value is not None:
        return value

    shared_types = await client.get_shared_data_types(relative_uid)
    if shared_key not in shared_types:
        raise DataNotSharedError(f"未共享该数据类型: {shared_key}", data_type=shared_key)
    return None


# endregion


# region 聚合数据
async def get_aggregated_data(
    client: MiHealthClient,
    relative_uid: int,
    key: str,
    start_time: int,
    end_time: int,
    *,
    tag: str = DATA_TAG_DAILY_REPORT,
    limit: int = 30,
) -> AggregatedDataResponse:
    """获取亲友的聚合数据。"""
    resp = await client._request(
        "GET",
        RELATIVES_AGGREGATED_DATA_PATH,
        params={
            "relative_uid": relative_uid,
            "key": key,
            "tag": tag,
            "start_time": start_time,
            "end_time": end_time,
            "limit": limit,
        },
    )
    return AggregatedDataResponse(**resp)


async def get_fitness_data(
    client: MiHealthClient,
    relative_uid: int,
    key: str,
    start_time: int,
    end_time: int,
    *,
    limit: int = 30,
) -> AggregatedDataResponse:
    """获取亲友的原始测量/事件数据（如体重、血压、异常心率等）。"""
    resp = await client._request(
        "GET",
        RELATIVES_FITNESS_DATA_PATH,
        params={
            "relative_uid": relative_uid,
            "key": key,
            "start_time": start_time,
            "end_time": end_time,
            "limit": limit,
        },
    )
    return AggregatedDataResponse(**resp)


# endregion


# region 便捷方法
def _date_to_timestamps(query_date: date | None = None) -> tuple[int, int]:
    """将日期转换为当日 00:00 ~ 23:59:59 的时间戳。"""
    d = query_date or date.today()
    tz = timezone(timedelta(hours=8))
    start = int(datetime(d.year, d.month, d.day, tzinfo=tz).timestamp())
    end = start + 86400 - 1
    return start, end


def _build_window_timestamps(query_date: date | None, days: int) -> tuple[int, int, int]:
    """构造以 ``query_date`` 为结束日的查询窗口。"""
    window_days = max(days, 1)
    _, end = _date_to_timestamps(query_date)
    start = end - 86400 * window_days + 1
    return start, end, window_days


def _parse_series_items(
    items: list[AggregatedDataItem],
    parser: Callable[[AggregatedDataItem], _SeriesDataT],
) -> list[_SeriesDataT]:
    """逐条解析数据项，跳过单条脏数据。"""
    series: list[_SeriesDataT] = []
    for item in items:
        try:
            series.append(parser(item))
        except ValidationError:
            continue
    return series


async def _get_aggregated_series(
    client: MiHealthClient,
    relative_uid: int,
    key: str,
    parser: Callable[[AggregatedDataItem], _SeriesDataT],
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[_SeriesDataT]:
    """按日期范围拉取聚合数据并转换为目标模型。

    ``query_date`` 视为窗口结束日；``days=7`` 表示获取该日及之前 6 天的聚合数据。
    """
    start, end, window_days = _build_window_timestamps(query_date, days)
    resp = await get_aggregated_data(client, relative_uid, key, start, end, limit=window_days)
    return _parse_series_items(resp.data_items, parser)


async def _get_fitness_series(
    client: MiHealthClient,
    relative_uid: int,
    key: str,
    parser: Callable[[AggregatedDataItem], _SeriesDataT],
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[_SeriesDataT]:
    """按时间窗口拉取原始测量记录。

    ``get_fitness_data`` 不是按天一条的聚合接口，因此固定使用较宽松的 ``limit=30``，
    以避免一周内存在多次测量时被 ``days`` 误伤截断。
    """
    start, end, window_days = _build_window_timestamps(query_date, days)
    resp = await get_fitness_data(
        client,
        relative_uid,
        key,
        start,
        end,
        limit=max(window_days, 30),
    )
    return _parse_series_items(resp.data_items, parser)


async def get_heart_rate(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[HeartRateData]:
    """获取亲友的心率数据。"""
    return await _get_aggregated_series(
        client,
        relative_uid,
        DATA_KEY_HEART_RATE,
        AggregatedDataItem.as_heart_rate,
        query_date,
        days=days,
    )


async def get_sleep(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[SleepData]:
    """获取亲友的睡眠数据。"""
    return await _get_aggregated_series(
        client,
        relative_uid,
        DATA_KEY_SLEEP,
        AggregatedDataItem.as_sleep,
        query_date,
        days=days,
    )


async def get_steps(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[StepData]:
    """获取亲友的步数数据。"""
    return await _get_aggregated_series(
        client,
        relative_uid,
        DATA_KEY_STEPS,
        AggregatedDataItem.as_steps,
        query_date,
        days=days,
    )


async def get_calories_history(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[CaloriesData]:
    """获取亲友按天聚合的活动卡路里数据。"""
    return await _get_aggregated_series(
        client,
        relative_uid,
        DATA_KEY_CALORIES,
        AggregatedDataItem.as_calories,
        query_date,
        days=days,
    )


async def get_valid_stand_history(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[ValidStandData]:
    """获取亲友按天聚合的有效站立次数。"""
    return await _get_aggregated_series(
        client,
        relative_uid,
        DATA_KEY_VALID_STAND,
        AggregatedDataItem.as_valid_stand,
        query_date,
        days=days,
    )


async def get_intensity_history(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[IntensityData]:
    """获取亲友按天聚合的中高强度活动时长。"""
    return await _get_aggregated_series(
        client,
        relative_uid,
        DATA_KEY_INTENSITY,
        AggregatedDataItem.as_intensity,
        query_date,
        days=days,
    )


async def get_spo2_history(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[Spo2SummaryData]:
    """获取亲友按天聚合的血氧摘要。"""
    return await _get_aggregated_series(
        client,
        relative_uid,
        DATA_KEY_SPO2,
        AggregatedDataItem.as_spo2,
        query_date,
        days=days,
    )


async def get_weight_history(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[WeightData]:
    """获取亲友在指定窗口内的体重测量记录。"""
    return await _get_fitness_series(
        client,
        relative_uid,
        DATA_KEY_WEIGHT,
        AggregatedDataItem.as_weight,
        query_date,
        days=days,
    )


async def get_blood_pressure_history(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
    *,
    days: int = 1,
) -> list[BloodPressureData]:
    """获取亲友在指定窗口内的血压测量记录。"""
    return await _get_fitness_series(
        client,
        relative_uid,
        DATA_KEY_BLOOD_PRESSURE,
        AggregatedDataItem.as_blood_pressure,
        query_date,
        days=days,
    )


async def get_weight(client: MiHealthClient, relative_uid: int) -> WeightData | None:
    """获取亲友最新体重数据。"""
    return await _get_latest_metric(
        client,
        relative_uid,
        attr_name="weight",
        shared_key=DATA_KEY_WEIGHT,
    )


async def get_goal(client: MiHealthClient, relative_uid: int) -> GoalData | None:
    """获取亲友最新目标完成情况。"""
    return await _get_latest_metric(
        client,
        relative_uid,
        attr_name="goal",
        shared_key=DATA_KEY_GOAL,
    )


async def get_blood_pressure(client: MiHealthClient, relative_uid: int) -> BloodPressureData | None:
    """获取亲友最新血压数据。"""
    return await _get_latest_metric(
        client,
        relative_uid,
        attr_name="blood_pressure",
        shared_key=DATA_KEY_BLOOD_PRESSURE,
    )


async def get_calories(client: MiHealthClient, relative_uid: int) -> CaloriesData | None:
    """获取亲友最新活动卡路里。"""
    return await _get_latest_metric(
        client,
        relative_uid,
        attr_name="calories",
        shared_key=DATA_KEY_CALORIES,
    )


async def get_valid_stand(client: MiHealthClient, relative_uid: int) -> ValidStandData | None:
    """获取亲友最新有效站立次数。"""
    return await _get_latest_metric(
        client,
        relative_uid,
        attr_name="valid_stand",
        shared_key=DATA_KEY_VALID_STAND,
    )


async def get_intensity(client: MiHealthClient, relative_uid: int) -> IntensityData | None:
    """获取亲友最新中高强度活动时长。"""
    return await _get_latest_metric(
        client,
        relative_uid,
        attr_name="intensity",
        shared_key=DATA_KEY_INTENSITY,
    )


async def get_spo2(client: MiHealthClient, relative_uid: int) -> Spo2Data | None:
    """获取亲友最新血氧数据。"""
    return await _get_latest_metric(
        client,
        relative_uid,
        attr_name="spo2",
        shared_key=DATA_KEY_SPO2,
    )


async def get_daily_summary(
    client: MiHealthClient,
    relative_uid: int,
    query_date: date | None = None,
) -> DailySummary:
    """获取亲友的每日综合健康摘要（并发请求心率、睡眠、步数）。"""
    d = query_date or date.today()

    heart_rate, sleep, steps = await asyncio.gather(
        _get_first_shared_or_none(lambda: get_heart_rate(client, relative_uid, d)),
        _get_first_shared_or_none(lambda: get_sleep(client, relative_uid, d)),
        _get_first_shared_or_none(lambda: get_steps(client, relative_uid, d)),
    )

    return DailySummary(
        date=d.isoformat(),
        relative_uid=relative_uid,
        heart_rate=heart_rate,
        sleep=sleep,
        steps=steps,
    )


async def get_latest_daily_summary(
    client: MiHealthClient,
    relative_uid: int,
) -> DailySummary:
    """获取亲友最近一次有同步数据的每日综合健康摘要。"""
    member = await client.find_relative(relative_uid)
    query_date = date.today()
    if member.latest_data_time > 0:
        query_date = datetime.fromtimestamp(member.latest_data_time, tz=UTC).date()
    else:
        latest = await get_latest_data(client, relative_uid)
        if latest.updated_time > 0:
            query_date = datetime.fromtimestamp(latest.updated_time, tz=UTC).date()
    return await get_daily_summary(client, relative_uid, query_date)


# endregion
