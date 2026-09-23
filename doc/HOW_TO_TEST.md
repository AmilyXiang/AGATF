# 如何测试（Testing Guide）

本文件说明如何验证 OEM DeskPhone Automation Framework 的当前实现。

框架当前处于 PPT v2 的 P0 阶段，已实现：

- Device Profile / DUT Pool
- Logical Role → DUT Instance Binding
- Resource Binder
- Case Selection 状态：READY / NOT_APPLICABLE / BLOCKED_RESOURCE / CONFIG_ERROR
- Atomic Step Parser / Compiler
- Resource Reserve / Release（执行期资源锁定与释放）
- Provider Registry + API / Physical Provider 选择（同一 Case 绑定不同后端）
- CLI `validate` / `list` / `plan` / `run`
- Structured exit codes（结构化退出码）
- JUnit XML 输出

---

## 1. 环境要求

- Python 3.12+
- pytest 9.x

安装 pytest（如未安装）：

```powershell
python -m pip install pytest
```

所有命令都在仓库根目录执行：

```powershell
cd d:\shares\AGATF
```

---

## 2. 快速验证（一条命令）

运行全部自动化测试：

```powershell
python -m pytest -q
```

预期结果：所有测试通过，例如：

```text
55 passed
```

---

## 3. 自动化测试说明

测试位于 `tests/` 目录，按职责划分：

| 测试文件 | 验证内容 |
|---|---|
| `tests/test_selection.py` | Case 过滤与四种状态（协议 / 能力 / 资源 / DUT 数量 / 角色能力 / 配置错误） |
| `tests/test_dut_binding.py` | 逻辑角色绑定到不同 DUT 实例、DUT Pool、端到端 role_bindings |
| `tests/test_compiler.py` | Case 编译成抽象 Atomic Steps（ACTION / VERIFICATION）、非法动作报错 |
| `tests/test_reservation.py` | 资源预留冲突、释放后复用、执行后自动释放 |
| `tests/test_cli_commands.py` | validate / list / run 的退出码与 JUnit 输出 |
| `tests/test_provider_binding.py` | 同一 Case 按 operation_mode 绑定 API / Physical Provider，Case 不变 |
| `tests/test_ppt_contract.py` | Test Plan 契约：保留 case steps、compiled_steps、协议过滤 |
| `tests/test_action_url.py` | Action URL 回调监听与闭环验证（真机事件到达才算通过） |
| `tests/test_ssh_client.py` | 通用 SSH 传输工具与 secret_ref 解析 |
| `tests/test_ale700a_provider.py` | ALE-700A Active URI provider 的动作映射与验证 |

### 运行单个测试文件

```powershell
python -m pytest -q tests/test_selection.py
```

### 运行单个测试用例

```powershell
python -m pytest -q tests/test_selection.py::test_missing_lab_resource_is_blocked_resource
```

### 查看详细输出

```powershell
python -m pytest -v
```

---

## 4. 手动验证 CLI 闭环

框架提供四个命令：`validate` / `list` / `plan` / `run`。

> Case 库固定在 `cases/` 目录（按 scope 拆分为 `common.json` / `sip.json` / `noe.json`），命令**不再需要 `--cases`**；用 `--scope`（`common` / `sip` / `noe`）选择子集，省略 `--scope` 则纳入全部适用 Case。
>
> 下面用 `tests/fixtures/` 里的通用配置（OEM_PHONE_A physical + 台架资源）演示，可覆盖资源绑定与 Provider 选择等全部场景。真机验证见 4.6。

### 4.1 validate（只校验，不执行）

```powershell
python cli.py validate --device tests/fixtures/device.json --lab tests/fixtures/lab.json --scope common
```

预期输出每个 Case 的状态，不执行任何测试：

```text
READY TC_CALL_001: ready
NOT_APPLICABLE TC_SIP_REG_001: scope 'sip' != requested 'common'
```

退出码：无问题为 `0`；有 CONFIG_ERROR 为 `2`；有 BLOCKED_RESOURCE 为 `3`。

### 4.2 list（列出 Case 及状态）

```powershell
python cli.py list --device tests/fixtures/device.json --lab tests/fixtures/lab.json
```

预期输出：

```text
READY            TC_CALL_001      basic_call
NOT_APPLICABLE   TC_NOE_INIT_001  noe_initialization
```

### 4.3 生成 Test Plan

```powershell
python cli.py plan --device tests/fixtures/device.json --lab tests/fixtures/lab.json --output out/plan.json --scope common
```

预期输出：

- 不适用的 Case 会被打印状态，例如：

```text
NOT_APPLICABLE TC_SIP_REG_001: scope 'sip' != requested 'common'
NOT_APPLICABLE TC_NOE_INIT_001: scope 'noe' != requested 'common'
Generated plan: out\plan.json
```

- 生成的 `out/plan.json` 中，每个 Case 应包含：
  - `role_bindings`（如 `caller → dut_01`、`callee → dut_02`）
  - `resource_bindings`（如 `audio → mic-02`）
  - `compiled_steps`（如 `phone.hold` / `verify.call_on_hold`）

### 4.4 执行 Test Plan（可选输出 JUnit）

```powershell
python cli.py run --plan out/plan.json --junit out/results.xml
```

预期输出：

- 每个 Case 的 evidence，`status` 为 `pass`，步骤为抽象 Atomic Steps
- evidence 中包含 `reserved_resources`（执行期锁定的 DUT / 资源）
- 生成 `out/results.xml`（JUnit 格式，供 Jenkins 消费）
- 退出码：全部 pass 为 `0`；有 case 失败为 `4`

### 4.6 真机验证（可选）

对真实设备用**实例配置** + `--live`，并用 `--dut` 指定受控设备：

```powershell
python cli.py run --plan out/plan.json --live --device config/device/device_ale700a.json --lab config/lab/lab_ale700a.json --dut dut_ale_01 --insecure --junit out/results.xml
```

OEM 专属调试命令不在中立 CLI 里，放在 OEM 入口：

```powershell
python -m oem.ale700a press --ip 10.10.6.136 --key SPEAKER
python -m oem.ale700a listen
```

### 4.5 结构化退出码

| 退出码 | 含义 |
|---|---|
| `0` | 成功 / 全部 pass |
| `1` | 参数错误（argparse） |
| `2` | CONFIG_ERROR |
| `3` | BLOCKED_RESOURCE |
| `4` | 测试失败（有 fail case） |

在 PowerShell 中可用 `$LASTEXITCODE` 查看上一条命令的退出码。

---

## 5. 状态判定说明

`plan` 阶段对每个 Case 会给出以下状态之一：

| 状态 | 含义 | 触发条件示例 |
|---|---|---|
| `READY` | 可执行，进入 Test Plan | 所有条件满足 |
| `NOT_APPLICABLE` | 不适用（协议 / 能力 / scope / 模式不匹配） | SIP 设备遇到 NOE-only Case |
| `BLOCKED_RESOURCE` | 台架资源或 DUT 不足 | 缺少 audio 资源；DUT 数量不够；角色能力不满足 |
| `CONFIG_ERROR` | Case 配置错误 | 缺少 id / name / steps |

只有 `READY` 的 Case 才会进入 Test Plan 并被执行。

---

## 6. 常见验证场景

### 场景 A：验证协议过滤

用 SIP 设备生成 `common` scope 计划，NOE Case 应被标记为 `NOT_APPLICABLE`，不出现在 plan 中。

### 场景 B：验证资源不足

将 `tests/fixtures/lab.json` 中 `resources` 移除 `audio`，重新生成 plan，`TC_AUDIO_001` 应变为 `BLOCKED_RESOURCE`。

### 场景 C：验证多 DUT 绑定

`tests/fixtures/lab.json` 中的 `duts` 提供两台 DUT，`TC_CALL_001` / `TC_HOLD_001` / `TC_AUDIO_001` 的 `caller` 与 `callee` 应绑定到两个不同实例。

### 场景 D：验证 Atomic Step 编译

检查 `out/plan.json` 中的 `compiled_steps`，确认每个业务步骤被拆成 `ACTION` + `VERIFICATION`，且不包含任何 SSH / REST / Robot / Camera 等 OEM 具体实现。

### 场景 E：验证退出码

执行 `validate` 后用 `$LASTEXITCODE` 检查退出码。移除 `audio` 资源后运行 `validate`，退出码应为 `3`（BLOCKED_RESOURCE）。

### 场景 F：验证 JUnit 输出

执行 `run --junit out/results.xml`，检查生成的 XML 根节点为 `testsuite`，`tests` 与 `failures` 数量正确。

### 场景 G：验证同一 Case 绑定不同 Provider

同一个 Case（如 Hold）在不同 `operation_mode` 下应绑定到不同 Provider，但 Case 本身不变。

```powershell
# physical 模式（tests/fixtures/device.json 默认 operation_mode = physical）
python cli.py plan --device tests/fixtures/device.json --lab tests/fixtures/lab.json --output out/plan_physical.json --scope common

# api 模式（复制一份 device 配置并将 operation_mode 改为 api）
```

验证点：

- physical 配置生成的 plan 中，provider 为 `physical_provider`
- api 配置生成的 plan 中，provider 为 `api_provider`
- 两份 plan 的 `compiled_steps` 完全相同（证明 Case 本身未改变）

---

## 7. Provider 说明

Provider 将抽象原子步骤（如 `phone.hold`）落地成具体操作。当前有三个桩 Provider，能力相同但 HOW 不同：

| Provider | backend | HOW 示例 |
|---|---|---|
| `stub_provider` | any | 通用桩，任何模式可用 |
| `api_provider` | api | `REST POST /calls/{id}/hold`、`API state == HELD` |
| `physical_provider` | physical | `Robot presses Hold key`、`Camera reads 'On Hold'` |

Resolver 根据设备的 `operation_mode` 选择 backend 匹配的 Provider；API / Physical 只是实现策略，不是不同的 Case。

---

## 8. 输入文件说明

| 文件 | 作用 |
|---|---|
| `config/device/` | Device Profile：`device_template.json` 样本 + 各设备实例（如 `device_ale700a.json`），纯类型字段 |
| `config/lab/` | Lab Config：`lab_template.json` 样本 + 各实例（DUT Pool，每台 DUT 的 ip/control/number） |
| `cases/` | Case Repository（固定目录）：按 scope 拆分为 `common.json` / `sip.json` / `noe.json`，用 `--scope` 选择 |
| `tests/fixtures/` | 测试与文档示例用的通用配置（OEM_PHONE_A physical + 台架资源） |
| `out/plan.json` | 生成的 Test Plan（执行契约） |
| `out/results.xml` | 执行结果的 JUnit XML（供 Jenkins 发布） |
