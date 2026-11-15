# AVF 实验分支 / Experimental AVF branch

本分支从上游 `7deea7c05bf3ecfd3414d7ec8a93c267724ed83c` 建立。
AVF 指令模式来自已离线核对的 Xiaomi 17 Ultra / nezha / OS4.0.2.0.XPACNXM EFI。
现在和 TEE 补丁一样，在 `PatchBuffer()` 的同一处理流程内按指令结构定位，
不再以完整文件哈希或固定文件偏移作为原厂/OTA 输入的准入条件。
它是实验补丁，尚未完成修改后的实际启动、数据解密及新 CSR/远程签发验收。

## 修改范围

现有补丁修改了送入 TEE KeyMint 的锁状态；AVF 的正常 BCC 构造路径又独立
读取 `DevInfo.is_unlocked`。在当前样本中，补丁点位于映像偏移 `0x24588`：

```text
29 75 77 39   LDRB W9, [X9,#0xddd]
09 00 80 52   MOV  W9, #0
```

这使随后 NORMAL/DEBUG 选择不再采用真实解锁字节。其余启动条件选择 mode=3 的
逻辑仍保留；全局 DevInfo、现有 TEE 补丁和 Dummy DICE fallback 均不修改。
本补丁改变 DICE 的状态输入，不恢复真实的启动验证，也不保证服务器接受 CSR。
NORMAL/DEBUG 与 protected/non-protected VM 是不同概念；本补丁不启用普通 VM。

仅处理**被 BDS 加载的 EFI 文件**，不修改物理 ABL、BDS/efisp 分区、persist
其他文件、默认启动项或任何安全存储。本文的两个 patcher 不会刷机或重启。

OTA 继续沿用现有脚本的“提取 EFI → 调用 patch_abl → 安装输出”流程。
本次指令匹配更新没有新增刷写模式、修改 BDS 或调整 ABL 的回滚策略。
原有安装脚本对 BDS、启动配置和 ABL 的处理仍是独立于 patcher 的步骤。

## 自动 patch / OTA

**使用此分支构建的 `patch_abl`，原有的两个参数调用会自动包含 AVF 补丁。**

```sh
make -C submodules/patcher build
submodules/patcher/build/patch_abl LinuxLoader_stock.efi boot_avf_test.efi
```

- 原厂/OTA 输入：运行上游 TEE/bootconfig 补丁，随后识别并追加 AVF。
- 文件哈希、文件大小、函数位置、相关地址和临时寄存器发生变化，不会单独导致拒绝。
- AVF 指令结构不存在、候选不唯一、寄存器关系不匹配或 PE 无效：**返回失败**。
- 为兼容第一版的用法，下面列出的当前 TEE-patched / 已有 AVF 样本仍支持直接输入；
  这两个已修改镜像通过哈希识别后跳过 TEE 重复处理。新 OTA 不需要加入此列表。

AVF 定位只扫描 ARM64 PE32+ 的可执行节，识别一段 17 条指令的模式：
读取两个额外标志、设置 NORMAL 常量、读取解锁字节、组合标志、比较解锁字节、
以 CINC 选择 NORMAL/DEBUG、保留 mode=3 的 CSEL 分支，最后写入模式字段。
匹配允许 ADRP 位移、LDRB/STR 偏移、栈位移及四个临时寄存器变化，并核对寄存器关联。
只替换其中的解锁字节读取为同一目标寄存器的 `MOV #0`，其余字节不变。
不同的指令调度、控制流或 BCC 构造实现仍需要新增经过检查的模式。

旧版本模块、主分支及手机中已安装的 patcher 不会因创建此分支自动获得功能。
只有改用本分支构建的 patcher 才有该行为。模块的 `bl_flasher.sh` 同时增加了
提取/补丁失败即停止的处理，阻止旧流程在失败后继续复制 ABL；成功路径保持上游行为。
不要把旧的输出文件当作本次失败后的成功产物。

只给当前已修改 EFI 追加 AVF，也可使用不依赖编译器的 Python 3 工具：

```sh
python3 tools/patch_avf_nezha.py boot_current_original.efi boot_avf_test.efi
```

该脚本仍是当前样本专用的哈希限定辅助工具；它不参与 OTA 自动 patch。
它保留输入，拒绝覆写已有输出，不接受未经现有 TEE 补丁处理的原厂镜像。

## 已核对的回归样本

三种文件均为 1,089,536 字节；固定地址只描述这一组样本，不是 OTA 地址限制。

| 输入/输出状态 | SHA-256 |
| --- | --- |
| 原厂 LinuxLoader | `7c0b96923fd8d7d30e3462aa2427cfc10cafdc1f7f5b8243ac6285fe0204442f` |
| 当前已应用 TEE 补丁 | `39cfb80eb6cb3ce73c43b347cb9e63bf36694f24d733d79808df71d248d1ef52` |
| 追加 AVF 实验补丁 | `14058f4e11282bcbcc57eedac5f438bc73ab73cc24f4bec42d2dd812f2a29b68` |

设备读取的固件和 CSR 不提交到此公开仓库。

## 验证

```sh
make -C submodules/patcher build
python3 submodules/patcher/tests/test_avf.py
python3 submodules/patcher/tests/test_avf_scripts.py
# 私有目录包含 boot_current_original.efi 和 LinuxLoader_stock.efi 时：
AVF_TEST_IMAGE_DIR=/path/to/private/fixtures python3 submodules/patcher/tests/test_avf.py
```

测试覆盖 SHA-256、PE 边界检查、非代码节和多候选拒绝、模式及寄存器关联变化拒绝、
函数搬移、地址/栈位移与寄存器重新分配、重复应用，以及原厂/当前样本输出一致。
另有基于私有样本的合成 OTA 变体测试：改变哈希与大小、移动 AVF 指令块并修正
ADRP 位移，确认完整 `patch_abl` 调用仍同时完成 TEE 和 AVF 修改。
这些合成变体仅用于离线测试，不是可启动固件，也不代表已经验证另一版真实 OTA。
当前真实样本的输出仍与第一版测试 EFI 完全一致；上述静态验收不代替真机测试。

另外五项脚本测试通过模拟命令验证：提取失败或 patcher 失败时不使用输出，
EFI 更新失败或 GBL 检测失败时不继续复制 ABL；成功检测仍遵循原来的分支。
测试中的分区写入命令全部替换为记录调用的模拟函数。

## 后续真机验收

保持现有 BDS 和持久启动项，通过已确认支持 EFI 的 Superfastboot 从电脑临时启动
测试 EFI。成功启动后，应确认数据仍能解密、TEE 状态保持，并新生成 AVF CSR 检查
`pvmfw` mode 和每一级签名；远程请求成功才算 RKP 修复完成。
失败时使用保留的正常启动入口；不要把原厂未修改 EFI 当作当前可解密的恢复副本。

No device boot or remote provisioning success is claimed by this branch.
