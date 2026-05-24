---
обновлено: 2026-05-23
---
# Mi Fitness


小米运动健康 SDK， 通过亲友列表获取其他账号的的心率、睡眠、步数等健康数据。

> **⚠️ 仅供学习与测试使用。** API 端点可能随版本更新而变化。

## 安装

```bash
pip install mi-fitness
# 或使用 uv
uv add mi-fitness
```

从源码安装：

```bash
git clone https://github.com/MistEO/MiSDK.git && cd MiSDK
uv sync
```

## 快速开始

### 登录（二维码扫码）

使用小米账号二维码扫码方式登录：

```python
import asyncio
from mi_fitness import XiaomiAuth

async def login():
    async with XiaomiAuth() as auth:
        await auth.login_qr()
        auth.save_token("token.json")
        print(f"登录成功！user_id = {auth.token.user_id}")

asyncio.run(login())
```

自定义二维码展示回调：

```python
async def login_with_callback():
    async def on_qr(qr_image_url: str, login_url: str) -> None:
        # qr_image_url 是二维码图片 URL
        print(f"请扫描: {qr_image_url}")

    async with XiaomiAuth() as auth:
        await auth.login_qr(qr_callback=on_qr)
        auth.save_token("token.json")
```

CLI 一行命令登录：

```bash
uv run python -m mi_fitness.cli qr-login
```

### 查询数据

```python
import asyncio
from mi_fitness import MiHealthClient

async def main():
    async with MiHealthClient.from_token("token.json") as client:
        # 亲友列表
        relatives = await client.get_relatives()
        for r in relatives:
            print(f"[{r.relative_uid}] {r.relative_note}")

        uid = relatives[0].relative_uid

        # 最新快照（强类型）
        latest = await client.get_latest_data(uid)
        print(latest.available_keys)
        print(latest.heart_rate)  # LatestHeartRate(bpm=84, ...)
        print(latest.steps)       # StepData(steps=3716, ...)

        # 最近同步日摘要（心率+睡眠+步数并发获取）
        summary = await client.get_latest_daily_summary(uid)
        print(f"步数: {summary.steps}, 睡眠: {summary.sleep}, 心率: {summary.heart_rate}")

asyncio.run(main())
```

### 亲友管理

```python
async def manage():
    async with MiHealthClient.from_token("token.json") as client:
        # 验证用户
        info = await client.verify_user(小米ID)
        print(f"找到: {info.nickname} (UID: {info.user_id})")

        # 发送邀请（默认共享全部数据类型）
        await client.invite_relative(info.user_id)

        # 删除亲友
        await client.delete_relative(亲友UID)
```

### 异常处理

```python
from mi_fitness import MiHealthClient, TokenExpiredError, APIError

async def safe_query():
    try:
        async with MiHealthClient.from_token("token.json") as client:
            relatives = await client.get_relatives()
    except TokenExpiredError:
        print("Token 已过期，请重新登录")
    except APIError as e:
        print(f"API 错误: {e} (HTTP {e.status_code})")
```

## API 一览

### 数据查询

| 方法 | 返回类型 | 说明 |
|------|---------|------|
| `get_heart_rate(uid, date)` | `list[HeartRateData]` | 日均/静息/最大/最小心率、最新采样 |
| `get_sleep(uid, date)` | `list[SleepData]` | 时长/评分/深睡/浅睡/REM/片段详情 |
| `get_steps(uid, date)` | `list[StepData]` | 步数/距离/卡路里 |
| `get_calories_history(uid, date, days=1)` | `list[CaloriesData]` | 按天/按周获取活动卡路里 |
| `get_valid_stand_history(uid, date, days=1)` | `list[ValidStandData]` | 按天/按周获取有效站立次数 |
| `get_intensity_history(uid, date, days=1)` | `list[IntensityData]` | 按天/按周获取中高强度活动时长 |
| `get_spo2_history(uid, date, days=1)` | `list[Spo2SummaryData]` | 按天/按周获取血氧摘要 |
| `get_weight_history(uid, date, days=1)` | `list[WeightData]` | 获取时间窗口内的体重测量记录 |
| `get_blood_pressure_history(uid, date, days=1)` | `list[BloodPressureData]` | 获取时间窗口内的血压测量记录 |
| `get_weight(uid)` | `WeightData \| None` | 体重/BMI |
| `get_goal(uid)` | `GoalData \| None` | 最新活力目标集合，支持 `steps_goal / calories_goal / intensity_goal` 便捷访问；不提供历史目标值 |
| `get_blood_pressure(uid)` | `BloodPressureData \| None` | 最新血压 |
| `get_calories(uid)` | `CaloriesData \| None` | 最新活动卡路里 |
| `get_valid_stand(uid)` | `ValidStandData \| None` | 最新有效站立次数 |
| `get_intensity(uid)` | `IntensityData \| None` | 最新中高强度活动时长 |
| `get_spo2(uid)` | `Spo2Data \| None` | 最新血氧 |
| `get_latest_data(uid)` | `LatestDataSnapshot` | 强类型最新快照（goal/heart_rate/sleep/steps/weight/...） |
| `get_latest_items(uid)` | `list[LatestDataItem]` | 原始 `data_list`，适合调试 |
| `get_daily_summary(uid, date)` | `DailySummary` | 心率+睡眠+步数并发获取 |
| `get_latest_daily_summary(uid)` | `DailySummary` | 自动使用最近一次同步日，减少空结果 |
| `get_aggregated_data(uid, key, start, end)` | `AggregatedDataResponse` | 自定义时间范围和数据类型 |
| `get_fitness_data(uid, key, start, end)` | `AggregatedDataResponse` | 原始测量/事件数据（如体重、血压、异常心率） |

### 亲友管理

| 方法 | 说明 |
|------|------|
| `get_relatives()` | 获取所有已绑定亲友 |
| `find_relative(keyword)` | 按备注名或 UID 查找 |
| `verify_user(xiaomi_id)` | 添加亲友前验证用户信息 |
| `invite_relative(uid)` | 邀请用户成为亲友 |
| `delete_relative(uid)` | 解除亲友关系 |
| `accept_invite(msg) / reject_invite(msg)` | 接受/拒绝邀请 |
| `has_new_invite()` | 是否有新邀请 |
| `get_invite_link_id()` | 获取二维码邀请链接 ID |
| `get_shared_data_types(uid)` | 查看对方共享了哪些数据类型 |
| `get_family_members()` | 家庭组成员列表 |

### 异常体系

| 异常 | 说明 |
|------|------|
| `MiSDKError` | 基础异常 |
| `AuthError` | 认证相关（登录失败等） |
| `TokenExpiredError` | Token 过期且自动刷新失败 |
| `DataNotSharedError` | 亲友未共享当前请求的数据类型 |
| `DataOutOfSharedTimeScopeError` | 查询日期超出亲友允许共享的时间范围 |
| `APIError` | API 非预期响应（含 `status_code` 和 `response_body`） |
| `DeviceUntrustedError` | 新设备需要短信验证 |
| `CaptchaRequiredError` | 触发图形验证码风控 |
| `FamilyMemberNotFoundError` | 找不到指定亲友 |
