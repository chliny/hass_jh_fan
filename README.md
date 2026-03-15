# JH Voice Fan

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![version](https://img.shields.io/badge/version-1.0.0-blue)

Home Assistant 自定义集成，通过蓝牙（BLE）控制 JH 智能语音循环扇。

## 功能

| 平台 | 实体 | 说明 |
|------|------|------|
| `fan` | JH Voice Fan | 风扇开关、风速调节、左右摇头 |
| `switch` | 左右摇头 | 独立控制左右摇头 |
| `switch` | 上下摇头 | 独立控制上下摇头 |
| `switch` | 语音播报 | 开启/关闭语音播报 |
| `select` | 定时关机 | 设置定时关机（关闭 / 1~12 小时） |

## 安装

### HACS（推荐）

1. 在 HACS 中点击右上角菜单 **自定义存储库**
2. 输入[本仓库地址](https://github.com/chliny/hass_jh_fan)，类别选择 **Integration**/**集成**, 确认**新增**
3. 在 HACS 搜索 **JH Voice Fan** 并下载安装
4. 重启 Home Assistant

### 手动安装

1. 将 `custom_components/jh_fan` 目录复制到 Home Assistant 的 `config/custom_components/` 目录下
2. 重启 Home Assistant

## 配置

本集成支持通过 UI 配置：

1. 确保 Home Assistant 已启用蓝牙集成
2. 风扇连接电源，以确保设备能被自动发现
3. 在`homeassistant` 前往 **设置 → 设备与服务 → 添加集成**
4. 搜索 **JH Voice Fan**, 添加集成
5. 在集成配置中，选择自动搜索到的设备

## 许可证

MIT License
