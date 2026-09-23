# ALE-700A OEM 接入模板说明

## 1. 目标

本文档把已验证可用的 ALE-700A 接入方案整理成一个可复用的 OEM 模板，供后续新增设备厂商时直接沿用。当前方案已在真实设备上验证通过，且框架级测试已通过：

- `python -m pytest -q`
- 结果：55 passed, 0 failed

---

## 2. 设计原则

1. 框架保持中立
   - `core/` 只保留通用模型、resolver、compiler、executor、provider 抽象。
   - OEM 设备细节不应污染框架核心。

2. OEM 逻辑单独收敛
   - 设备能力、动作映射、回调事件、认证规则属于 `oem/<vendor>/`。

3. 通用传输能力抽离
   - HTTP / SSH / 串口等底层传输能力放到 `tools/`。
   - OEM 模块只负责把抽象步骤翻译成目标设备协议。

4. 验证必须闭环
   - 只确认命令发出不够，必须确认真实设备状态变化。
   - ALE-700A 的 Action URL 监听就是这个闭环验证机制。

---

## 3. 当前已验证的 ALE-700A 方案

### 3.1 技术路径

- 控制模式：Active URI over HTTP
- 访问方式：HTTP GET 到 `/cgi-bin/ConfigManApp.com?key=...`
- 认证：Basic Auth / password
- 验证方式：Action URL callback
- 设备绑定：DUT 编号绑定到角色，例如 `caller` / `callee`

### 3.2 关键实现位置

- [oem/ale700a/provider.py](../oem/ale700a/provider.py)
- [oem/ale700a/action_url.py](../oem/ale700a/action_url.py)
- [tools/http_client.py](../tools/http_client.py)
- [tools/ssh_client.py](../tools/ssh_client.py)
- [config/device_ale700a.json](../config/device_ale700a.json)
- [config/lab_ale700a.json](../config/lab_ale700a.json)

### 3.3 真实设备验证结论

已验证以下事实：

- 设备名及 ACL/IP 过滤会影响访问
- 设备在源 IP 被锁定时会返回 403，且 403 可能覆盖所有路径
- 这不是 AGATF 的逻辑错误，而是设备安全策略问题
- 解除 IP 禁止后，真实设备联调恢复正常

这条经验必须写进后续 OEM 接入 checklist，以避免误判成代码问题。

---

## 4. 模板结构

新增 OEM 时，推荐保持如下目录结构：

```text
OEM_ROOT/
├── __init__.py
├── provider.py
├── action_url.py
└── ...
```

对应模式：

- `provider.py`：定义具体设备动作映射和执行入口
- `action_url.py`：监听设备回调并等待状态事件
- `__init__.py`：导出公共接口

---

## 5. 扩展模板的责任分工

### OEM 模块职责

- 把抽象 atomic step 翻译成设备特定命令
- 处理设备认证、端口、URL 结构
- 解析设备 callback / event
- 处理设备特有的状态验收方式

### 通用工具职责

- 统一 HTTP、SSH、串口调用方式
- 处理超时、重试、鉴权和日志
- 提供稳定的底层调用接口，供 OEM 模块复用

### 配置职责

- `device` 配置：设备能力和协议
- `lab` 配置：账号、IP、callback、DUT 绑定
- 让设备参数和实验环境参数分离

---

## 6. 典型新增 OEM 的 checklist

1. 确认设备控制协议
   - HTTP / SSH / Serial / other

2. 确认是否有设备状态 callback
   - 若有，建立一个 `ActionUrlListener` 方案
   - 若没有，需要设计其他状态确认方式

3. 定义抽象动作映射
   - `phone.dial`
   - `phone.hold`
   - `phone.resume`
   - `verify.call_connected`
   - `verify.call_on_hold`

4. 设计 config schema
   - device profile
   - lab profile
   - DUT binding

5. 真实设备验收
   - 端口和认证是否正确
   - callback 是否真的能收到
   - 失败时是否存在安全策略或 IP lockout

6. 运行回归测试
   - `pytest` 全量验证
   - 真实设备 smoke test

---

## 7. 结论

ALE-700A 已经证明：AGATF 的 OEM 接入架构是可行的，关键在于把设备特性放到 OEM 层，而把框架逻辑保留在通用层。该方案已经可作为后续新 OEM 接入的模板，尤其适合在 HTTP / callback 型设备场景中复用。

后续新增其他厂商时，直接复制这个结构，并更换：

- 控制方式
- 动作 key 映射
- callback 事件名
- 认证与网络参数

即可从同一套 AGATF 框架中快速产出新 OEM 接入。
