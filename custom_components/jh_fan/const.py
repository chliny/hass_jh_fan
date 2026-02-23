"""Constants for the JH Voice Fan integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "jh_fan"

CONF_MAC_ADDRESS = "mac_address"
CONF_DEVICE_ID = "device_id"

SERVICE_UUID = "0000FFB0-0000-1000-8000-00805F9B34FB"
WRITE_CHAR_UUID = "0000FFB1-0000-1000-8000-00805F9B34FB"
NOTIFY_CHAR_UUID = "0000FFB2-0000-1000-8000-00805F9B34FB"

FRAME_HEAD = 0xAA
FRAME_TAIL = 0x55

# DP点定义 (与微信小程序一致)
DP_GET_ALL = 0  # 获取所有状态
DP_SWITCH = 1  # 开关
DP_LEVEL = 2  # 风速档位
DP_TIMING_OFF = 3  # 定时关机
DP_LR_OSCILLATE = 4  # 左右摇头
DP_UD_OSCILLATE = 5  # 上下摇头
DP_ANION = 6  # 负离子
DP_MODE = 7  # 模式
DP_VOICE_ANNOUNCE = 8  # 语音播报
DP_SLEEP_MODE = 10  # 睡眠模式
DP_TIMING_ON = 15  # 定时开机
DP_CHILD_LOCK = 26  # 童锁
DP_NATURAL_WIND = 27  # 自然风

# 状态上报命令码
CMD_STATUS_REPORT = 0x53

SPEED_COUNT = 8

DEFAULT_NAME = "JH Fan"
DEFAULT_ATTEMPTS = 3
CONNECTION_TIMEOUT = 10.0
COMMAND_DELAY = 0.1
