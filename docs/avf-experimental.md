# AVF 实验分支 / Experimental AVF branch

本分支从上游 `7deea7c05bf3ecfd3414d7ec8a93c267724ed83c` 建立。
当前只适配已离线核对的 Xiaomi 17 Ultra / nezha / OS4.0.2.0.XPACNXM EFI。
它是实验补丁，尚未完成修改后的实际启动、数据解密及新 CSR/远程签发验收。

## 修改范围

现有补丁修改了送入 TEE KeyMint 的锁状态；AVF 的正常 BCC 构造路径又独立
读取 `DevInfo.is_unlocked`。本分支在该路径的映像偏移 `0x24588` 修改一条指令：

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

**本分支同步了上游的新 BDS 源码，但本次设备实验只使用独立 patcher 和生成的
测试 EFI。不要为了追加 AVF 补丁安装整个模块或刷入新 BDS；上游模块安装流程
仍可能更新 BDS、启动配置和 ABL，这不属于本次操作。**

## 自动 patch / OTA

**使用此分支构建的 `patch_abl`，原有的两个参数调用会自动包含 AVF 补丁。**

```sh
make -C submodules/patcher build
submodules/patcher/build/patch_abl LinuxLoader_stock.efi boot_avf_test.efi
```

- 已适配的原厂输入：先运行现有 TEE/bootconfig 补丁，再补 AVF。
- 已适配的当前 TEE-patched 输入：只补 AVF，不重新改动 TEE。
- 已有 AVF 补丁的输入：原样输出，可重复应用。
- 未识别的输入（包括新 OTA）：**返回失败，不生成输出**，必须先分析和增加适配。

这里使用完整文件 SHA-256 白名单，不靠单个指令或相同文件大小猜测版本。
旧版本模块、主分支及手机中已安装的 patcher 不会因创建此分支自动获得功能。
只有改用本分支构建的 patcher 才有该行为；仍需检查调用脚本是否正确处理失败。
不要把旧的输出文件当作本次失败后的成功产物。

只给当前已修改 EFI 追加 AVF，也可使用不依赖编译器的 Python 3 工具：

```sh
python3 tools/patch_avf_nezha.py boot_current_original.efi boot_avf_test.efi
```

该脚本保留输入，拒绝覆写已有输出，不接受未经现有 TEE 补丁处理的原厂镜像。

## 已适配文件

三种文件均为 1,089,536 字节；地址只适用于这一组文件。

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
# 私有目录包含 boot_current_original.efi 和 LinuxLoader_stock.efi 时：
AVF_TEST_IMAGE_DIR=/path/to/private/fixtures python3 submodules/patcher/tests/test_avf.py
```

测试覆盖 SHA-256 填充分界及长输入、未知/截断输入拒绝、无副作用失败、重复应用、
原厂与当前 EFI 的生成结果一致、C 与 Python 输出一致，以及只变化指定 4 字节。
上述静态验收不代替真机测试。

## 后续真机验收

保持现有 BDS 和持久启动项，通过已确认支持 EFI 的 Superfastboot 从电脑临时启动
测试 EFI。成功启动后，应确认数据仍能解密、TEE 状态保持，并新生成 AVF CSR 检查
`pvmfw` mode 和每一级签名；远程请求成功才算 RKP 修复完成。
失败时使用保留的正常启动入口；不要把原厂未修改 EFI 当作当前可解密的恢复副本。

No device boot or remote provisioning success is claimed by this branch.
