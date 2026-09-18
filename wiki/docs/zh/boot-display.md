# BDS 启动画面与其他系统

## 画面在哪里绘制

原始 `efisp` 分区存放可执行的 `BDS.efi`，不是 BMP/JPEG 图片，也不是这里的
启动文件目录。模块把入口和工具放在 `/mnt/vendor/persist/efisp/`。

主要源码位于 `submodules/uefi/edk2/QcomModulePkg/Application/LinuxLoader/`：

| 文件 / 函数 | 用途 |
| --- | --- |
| `LinuxLoader.c` / `LinuxLoaderEntry` | 检查音量上键，选择默认启动或菜单 |
| `SuperFbMenu.c` / `SfbPrepareBootScreen` | 启动前整理画面；默认启动不清屏、不叠加 Booting 文字，菜单启动只清掉菜单 |
| `SuperFbMenu.c` / `SfbShowEnteringMenu` | `Entering Boot Menu` 和 3 秒停留 |
| `SuperFbMenu.c` / `SfbShowFastbootMode` | `FASTBOOT MODE` |
| `SuperFbMenu.c` / `SfbBeginScreen`、`SfbDrawRow`、`SfbDrawMenu` | 菜单标题、颜色、选中项 |
| `SuperFbEntries.c` / `SfbLaunchEntry` | 加载驱动，然后 `LoadImage` / `StartImage` 启动 EFI |

原来的 `Booting %s` 文本输出已移除。`SuperFbSplash.c` 现在负责随机启动图片，
每次启动先处理已有的原厂 Fastboot 启动原因，再执行三秒音量键检测；仅在未请求菜单或原厂 Fastboot 且找到已保存的默认项时，
才初始化图片功能并随机显示一张。按键进入菜单、首次没有默认项时均跳过图片。
`BOOTENTRIES` 中的 `Android:boot.efi`
决定菜单名称，但文字格式、颜色、布局由 C 代码决定。修改这些源码需要重新
构建 BDS 后更新设备；只更新 WebUI 不会改变开机画面。

## 换照片的范围

BDS 接管显示后可以绘制图片。当前实现从 persist 的 `efisp/splash` 目录读取
`1.sfb` 至 `7.sfb`，使用 EDK2 LZMA 解压器还原原始像素，校验 CRC32 后通过 GOP
绘制。图片以原始 890×1920 像素无损存储，运行时等比例缩放到 1104×2381，
居中显示在 1200×2608 黑底上。原始 PNG 和转换器位于
`targets/magisk_module/assets/splash-source` 与 `tools/splash`。

图片缺失、损坏、内存不足、GOP 缺失或分辨率不匹配时跳过图片，不阻止原有启动。
当前实现保留菜单和错误处理；按音量上进入的菜单不初始化图片，手动选择启动项
也不会新加载图片。如果默认启动曾加载图片后返回菜单，可复用本次缓存。原始 PNG/JPEG
需转换后部署，不能直接改扩展名。主机测试使用相同解压器和缩放代码；实际启动时
后续加载器是否再次重绘仍需真机观察。

更早的厂商第一屏可能由 XBL/厂商 UEFI 或 ABL 绘制，来源依机型而定。当前仓库
不能确认它是否来自 `splash`、`logo`、其他资源分区或固件内嵌资源。因此 BDS
绘制只能保证在它接管之后覆盖画面，不能保证上电最早的一帧也被替换。完整替换
需要先确认机型、分区和原始资源格式。

## Linux / Windows

当前 BDS 已具备 ARM64 EFI 程序的链式启动入口，也支持入口目录的 `DRIVER.LIST`
预加载 UEFI 驱动。但它依赖手机现有的 UEFI 环境，不能自动补齐完整 PC 固件能力。

- Linux：可以以 ARM64 GRUB 或带 EFI stub 的内核作为后续入口。仍需适配本机的
  内核、DTB/平台描述、initramfs、启动参数及硬件驱动。现有 `SfbLaunchEntry` 不设置
  `LoadedImage.LoadOptions`，需要由 GRUB 等二级加载器配置参数，或另行实现参数传递。
- Windows：可以研究启动 ARM64 Windows Boot Manager，但能运行 EFI 文件不等于
  Windows 能启动或可用。需要该机型的 ACPI/平台适配、正确的内存与中断/多核初始化、
  UEFI 服务以及存储、显示、USB、电源等 Windows 驱动。此仓库没有验证这些条件。
  x64 Windows 引导程序不能直接作为 ARM64 EFI 程序运行。

参考：[Linux EFI stub](https://docs.kernel.org/admin-guide/efi-stub.html)、
[Microsoft SoC UEFI 要求](https://learn.microsoft.com/en-us/windows-hardware/drivers/bringup/uefi-requirements-that-apply-to-all-windows-platforms)、
[Microsoft UEFI 固件要求](https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/oem-uefi)。
