# gbl_uefi 7.0-rc.1

这是一次启动修复的预发行版本。尚未进行真机启动或原厂 Fastboot USB 验证，不能当作已验证稳定版。

## 修复与功能

- 移除 LZMA guided-section 注册构造函数，改用无构造函数的 raw 解码库，避免应用启动前访问未配置的固定内存表。
- 已有 `FASTBOOT_MODE=2` 请求时，BDS 在入口返回父 ABL，保留启动原因，不触碰输入、分区、文件系统和绘图。
- 开机三秒音量键窗口先于分区枚举。音量上打开菜单；音量下按原项目方式请求带原因 2 的冷重启，然后由入口让出执行权。
- 无法读取启动原因，或重启调用意外返回时，明确显示并进入 BDS 自带 Fastboot 备用入口。
- 恢复 `reboot-bootloader` 专用处理，修复它被 `reboot` 前缀按普通重启处理的问题。
- 图片仅在找到已保存默认启动项后加载；菜单、首次未配置和 Fastboot 请求路径不加载图片。
- 模块名改为 gbl_uefi，包含七张随机开机图片、UEFI 工具与只读 A/B/指定镜像防回滚元数据检查。
- 模块安装只安装管理工具；固件部署是明确的 WebUI 操作，安装不自动刷写、格式化或重启。

## 下载文件

- `gbl_uefi.zip`：Magisk/KernelSU 模块，含 BDS、工具、图片和 WebUI。
- `efisp.img`：与 ZIP 中 `BDS.efi` 逐字节一致的原始 AArch64 EFI 可执行文件。
- `SHA256SUMS`：发行资产的 SHA-256。

`efisp.img` 不是 FAT 文件系统镜像，也不是 ABL 镜像。它不包含 persist 中的 `boot.efi`、启动项或图片，
不能单独完成新设备的首次部署。此版本依赖兼容的外层 ABL 与已有 GBL 启动环境。
图片绘制固定匹配 1200×2608 的 GOP；不修改原厂 imagefv 或 UEFI 资源签名。

## 验证范围

已通过 AArch64 RELEASE 编译、实际启动函数的 10 个模拟路径测试、按键/启动原因/重启载荷测试、
Fastboot 实际注册与前缀分发测试、七张图片解码与渲染、13 类损坏输入、
防回滚工具的 6 组自动化测试、WebUI 测试以及 ZIP/EFI 逐文件一致性检查。
构建与打包均检查链接结果中不存在出问题的 guided-section 注册构造函数。

这些检查没有模拟完整的 Qualcomm UEFI 或安全固件，也没有验证实体按键、电源时序、
启动原因驱动和父 ABL 在本机上的交接。因此不能保证一定能进入原厂 Fastboot。
音量下路径可能发生一次额外冷重启；它不是直接跳转厂商内部地址。
BDS 入口之前的异常、外层 ABL 不兼容及设备固件故障不在这个入口的恢复能力之内。

转为稳定发行前，需要在有可靠恢复能力的设备上验证：正常启动、音量上菜单、音量下到原厂
Fastboot、ADB/原厂请求 bootloader、BDS `reboot-bootloader`，并实际确认 USB Fastboot 枚举
及设备身份。此预发行没有替用户执行这些设备操作。

## 源码与本地验证

```sh
make -C tools/splash test
make -C tools/arb_inspect test
node tools/arb_inspect/tests/test_ui.cjs
make -C submodules/uefi build
make -C submodules/uefi tools
python3 tools/package_module.py
```

打包还需要已构建的 Android ARM64 `patch_abl`、`extractfv` 和 `arb_inspect`，详见相应 Makefile。
这些输出是 UEFI/模块资产，不使用 APK 签名，也不带 Xiaomi OEM 固件签名。
