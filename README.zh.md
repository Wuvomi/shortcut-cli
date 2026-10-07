# shortcut-cli

> **无损、可复验**的双向转换：agent 可读命令(JSON) 与 iOS/macOS 快捷指令(`.shortcut`)之间互转。

![无损往返](https://img.shields.io/badge/%E5%BE%80%E8%BF%94-%E6%97%A0%E6%8D%9F-2ea44f)
![动作零丢失](https://img.shields.io/badge/%E5%8A%A8%E4%BD%9C%E4%BF%9D%E7%95%99-100%25-2ea44f)
[![基准已验证](https://img.shields.io/badge/benchmark-verified-1f6feb)](BENCHMARK.zh.md)
![平台 macOS](https://img.shields.io/badge/platform-macOS-lightgrey)
![许可证 MIT](https://img.shields.io/badge/license-MIT-blue)

[English](README.md) · **中文**

把快捷指令转成 JSON，改它（或让 AI 改它），再转回来——**一个动作都不丢**。不是普通"转换"，是经过验证的**无损**往返（[看基准测试](BENCHMARK.zh.md)）。

- **命令 → 快捷指令**(`compile`)：把 JSON 描述编译成可导入的 `.shortcut`，**默认自动签名**。
- **快捷指令 → 命令**(`decompile`)：把任意 `.shortcut`（已签名或未签名）反编译成可编辑 JSON 或可读伪代码。
- **iCloud 链接 → 快捷指令**(`fetch`)：从 `icloud.com/shortcuts/...` 分享链接下载 `.shortcut`。
- **导入**(`import`)：把 `.shortcut` 直接送进快捷指令 App 的添加对话框。

签名/解签名依赖 macOS，其余跨平台。输出中英双语。

---

## 谁需要它？（为什么做这个）

如果你曾经**让 Claude、Codex、ChatGPT、Gemini、Copilot、Cursor 或任意 AI 编程 agent 帮你生成一个快捷指令**，结果**一导入就丢了一半动作**——这个工具就是为此而生，因为我在这上面反复栽了跟头。

真凶既不是 AI，也不是签名。当 `.shortcut` 是**程序化生成**的，如果 `UUID` / `GroupingIdentifier` 被放在 action 顶层而不是 `WFWorkflowActionParameters` 里面，**新版导入器会静默丢弃整段控制流块**：在 macOS 上动作直接消失，在 iOS 上能导入但运行错乱。

`shortcut-cli` **自动修复这个根因**（canonical 归一化）并**默认签名**，让**AI 生成 / 自动生成的快捷指令真正能完整导入**。它也能反向工作——把任意快捷指令反编译成可读 JSON——还能从 iCloud 分享链接拉取。

如果你是搜这些关键词找来的——**快捷指令转换、claude 创建快捷指令、codex 创建快捷指令、codex 生成快捷指令、快捷指令生成、agent 创建快捷指令、agent 生成快捷指令、自动生成快捷指令、命令转快捷指令、反编译快捷指令、快捷指令导入丢失/裁切、快捷指令签名**——那你来对了，希望你能少走我当初走过的弯路。

---

## 平台支持

纯 Python 部分任意平台可跑；凡是碰 Apple 签名服务或 Apple Encrypted Archive 的，**只能 macOS**（这是 Apple 的硬限制，不是没做）。

| 命令 | macOS | Linux / Windows |
|---|:---:|:---:|
| `compile`（未签名，`--no-sign`） | ✅ | ✅ |
| `compile`（**签名**，默认） | ✅ | ❌ 需 Apple 签名 |
| `decompile` / `info`（未签名文件） | ✅ | ✅ |
| `decompile`（**已签名**文件） | ✅ | ❌ 需 `aea`/`aa` |
| `fetch`（iCloud） | ✅ | ✅ |
| `sign` · `import` | ✅ | ❌ |

非 macOS 上跑 macOS-only 命令会给清晰报错，不会崩溃。

## 安装

**预编译二进制**（无需 Python）——从 [Releases](https://github.com/Wuvomi/shortcut-cli/releases) 下 `shortcut-cli-macos` / `-linux` / `-windows.exe`：
```bash
chmod +x shortcut-cli-macos && ./shortcut-cli-macos --help
```

**源码运行**（Python 3.8+）：
```bash
git clone https://github.com/Wuvomi/shortcut-cli.git
cd shortcut-cli
python3 shortcut_cli.py --help
# 可选：软链到 PATH
ln -s "$PWD/shortcut_cli.py" ~/.local/bin/shortcut-cli && chmod +x shortcut_cli.py
```

macOS-only 部分要求**登录 iCloud**（签名走 Apple 的 iCloud 服务，**无需付费开发者账号**）。用到的系统工具：`shortcuts`、`aea`、`aa`、`openssl`。

## 用法

### `info` —— 看快捷指令概要
```bash
SHORTCUT_CLI_LANG=zh shortcut-cli info 某个.shortcut
```
```
名称      : 我的快捷指令
已签名    : 是 (AEA1)
动作数    : 21
结构健康  : top-level GroupingId=0(0) UUID=0(0) -> OK canonical
```
`结构健康` 那行告诉你它是否 canonical（能安全导入），还是会被裁切。

### `decompile` —— 快捷指令 → 命令
```bash
shortcut-cli decompile 某个.shortcut -o out.json   # 可回编译的 JSON
shortcut-cli decompile 某个.shortcut --pretty      # 可读伪代码
```
**已签名**的快捷指令也能解（自动解密 Apple Encrypted Archive）。

### `compile` —— 命令 → 快捷指令
```bash
shortcut-cli compile out.json --name "我的快捷指令"   # 默认签名
shortcut-cli compile out.json --no-sign               # 不签名
```
自动 canonical 归一化保证导入不裁切，再签名 → `out.signed.shortcut`。

命令格式就是快捷指令的 `WFWorkflowActions` 数组包一层，见 [`examples/`](examples/)：
```json
{
  "WFWorkflowName": "Hello",
  "WFWorkflowActions": [
    { "WFWorkflowActionIdentifier": "is.workflow.actions.alert",
      "WFWorkflowActionParameters": { "WFAlertActionTitle": "Hello" } }
  ]
}
```
最省事的写法：在 App 里搭个类似的 → `decompile` → 改 JSON → `compile`。

### 自动归一化控制流程

`compile` 在现有 canonical 归一化过程中自动修复两类生成结构，不需要额外参数或配置：

```bash
shortcut-cli compile examples/control_flow_normalization.json --no-sign
```

- **菜单顺序：**完整菜单的菜单项与分支标题为同一组字面文本、仅顺序不同的情况下，将 `WFMenuItems` 按分支顺序排列。分支标题、动作体、UUID 和分组保持不变。菜单项缺失或不同、动态标题、不支持的标记、重复或孤立的结束标记、嵌套不完整或分组 ID 重用时不作修改；不会添加或删除分支。
- **显式文本比较：**对已确认的文本比较结构，给未显式指定类型的命名变量添加 `WFStringContentItem` 转换，位置为 `WFInput.Variable.Value.Aggrandizements`。要求右侧是字符串或 `WFTextTokenString`，运算符支持文本，且没有其他条件参数。已有显式类型、未知或冲突的条件设置，以及未知或格式错误的变量修饰项保持不变；支持的属性读取顺序保持在新增转换之前。

在一个实际生成的工作流中，JSON 已有右侧变量，但 iOS 将比较字段显示得像缺少参数。将输入改为其他类型再改回文本后，字段恢复；重新导出的输入增加了以下元数据：

```json
{
  "Aggrandizements": [
    {
      "Type": "WFCoercionVariableAggrandizement",
      "CoercionItemClass": "WFStringContentItem"
    }
  ]
}
```

自动修复会添加该显式类型，同时保留左右两侧的值和运算符。文本比较的 `4` 是 **is**，`5` 是 **is not**（[类型映射源码](https://github.com/pfgithub/scpl/blob/master/src/Data/GetTypes.ts)）。编译器不会猜测作者希望在相等还是不相等时执行分支，也不会根据动作体的含义修复已经被重新标记的分支。

这些是有意的编译归一化操作，不是原始 JSON 的逐字段保留。`decompile` 仍保持原始内容不作修改。归一化具有幂等性；归一化后的编译/反编译/再编译结果稳定。

合成示例 [`examples/control_flow_normalization.json`](examples/control_flow_normalization.json) 演示两项自动修复，不包含私人数据、SSH 动作或其他 App 依赖。测试验证生成字段及内容保留边界；修复后文件的 iOS 界面行为尚未独立测试，不能据此认定 iOS 显示问题的根因。

运行跨平台回归测试：`python3 -m unittest discover -s tests -v`。

### `fetch` —— iCloud 链接 → 快捷指令
```bash
shortcut-cli fetch https://www.icloud.com/shortcuts/<id>
```
下载 `.shortcut`（未签名——可直接 decompile/改/compile）。

### `import` —— 送进快捷指令 App（macOS）
```bash
shortcut-cli import 某个.shortcut   # 未签名自动先签名，弹出"添加快捷指令"对话框
```

### `sign` / `verify`
```bash
shortcut-cli sign  某个.shortcut
shortcut-cli verify 某个.signed.shortcut   # 解包数动作
```

## 双语输出
输出跟随系统语言，也可强制：
```bash
SHORTCUT_CLI_LANG=zh shortcut-cli info x.shortcut   # 中文
SHORTCUT_CLI_LANG=en shortcut-cli info x.shortcut   # English
```

## 为什么可靠
`compile` 始终把 `UUID`/`GroupingIdentifier` 挪进 `WFWorkflowActionParameters`，`info` 会标出任何非 canonical 的文件。签名本身（`shortcuts sign`）是**无损**的——本工具用完整 round-trip（`decompile → compile → sign → verify`，动作数不变）证明了这点。

## 可靠性 / 往返保真度

**→ 完整数据、图示、可复跑脚本见 [BENCHMARK.zh.md](BENCHMARK.zh.md)。** 已在最多 61 动作、含嵌套 `if`/`repeat` 的真实快捷指令上验证无损。

`decompile` 捕获**整个** workflow（每个顶层字段 + 全部动作；图标等二进制用 base64 编码），`compile` 则执行上述 canonical 归一化。已经归一化的输入可以往返转换而不再改变内容。在真实快捷指令上实测：

- 对已经归一化的输入，**`原始 == 重编译`**（深度值比较），所有动作与 workflow 字段保持不变。
- **`compile` 确定性** —— 同输入 → 逐字节相同的输出。
- **多轮转换收敛到稳定定点**（`decompile → compile → decompile` 过一次后永久稳定）。
- 动作经**签名**后完全守恒（两次签名解出的内容完全一致）。

**不会逐字节相同的地方**（属于元数据/编码，不是你的逻辑）：
- 二进制 plist 序列化器会把字典**键顺序**规范化，所以重编码的字节/大小和 Apple 原始的略有不同——**值不变**。
- **签名文件非确定性**：Apple 签名内嵌时间戳，每次 `sign` 字节都不同（大小 ±1）。这是本质，不是工具缺陷。
- 签名时 Apple 会盖自己的 `WFWorkflowClientVersion`；除此之外无任何改动。

## 局限
- 签名 与 解签名文件**只能 macOS**（见上表）。
- `decompile` 出的是快捷指令原生 action JSON——无损但底层；暂无更高层 DSL。
- `fetch` 依赖当前 iCloud 快捷指令 records API 的结构。

## 关键词
快捷指令转换 · claude创建快捷指令 · codex创建快捷指令 · codex生成快捷指令 · 快捷指令生成 · agent创建快捷指令 · agent生成快捷指令 · 自动生成快捷指令 · 命令转快捷指令 · 反编译快捷指令 · 快捷指令导入丢失/裁切 · 快捷指令签名（无需开发者账号）· ChatGPT/Gemini/Copilot/Cursor 生成快捷指令 · iOS Shortcuts CLI · WFWorkflowActions。

## 许可证
MIT，见 [LICENSE](LICENSE)。
