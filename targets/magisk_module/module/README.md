# gbl_uefi 7.0-rc.1

GBL-based UEFI boot manager and playground: EFI boot entries, randomized boot
artwork, UEFI tools and anti-rollback inspection. BL/OTA helpers remain available.

## 当前设备 / Current device

本次七张图片专为 nezha 的 **1200×2608** 屏幕制作。原图以 890×1920 的原始像素
无损压缩存储，UEFI 解压后等比例缩放到 1104×2381，居中绘制在 1200×2608 黑底上。
左右各留 48 像素，上下约 113 像素，不裁切人物。每次 BDS 启动从七张中随机选一张，
允许连续两次随机到同一张。优先使用 Qualcomm RNG，失败时用计数器和时间混合。
每次启动的三秒音量键检测先于分区枚举和图片初始化；按音量上进菜单或首次没有保存默认
启动项时，跳过图片。当前源码修订仅完成离线构建与检查，尚未进行真机启动验证。

这覆盖的是 BDS 接管后的显示阶段，不能阻止此前的厂商 Logo 短暂出现。

## Fastboot 交接与验证范围

- 已有启动原因为 `FASTBOOT_MODE=2` 时，BDS 在入口立即返回父 ABL，不读取按键，
  不清除启动原因，不初始化分区、文件系统或图片。
- 三秒窗口内按音量下，请求携带原因 2 的冷重启；下一次进入 BDS 时走上述返回路径。
  这是原厂 ABL Fastboot 的交接请求，可能出现一次额外重启，不是直接跳转厂商内部地址。
- 启动原因协议不可用或 ResetSystem 意外返回时，转入明确标识的 BDS Fastboot 备用入口。
  BDS 自带 Fastboot 与原厂 ABL Fastboot 是不同实现。
- 恢复 BDS Fastboot 的 `reboot-bootloader` 专用处理，不再被通用 `reboot` 前缀吞掉。
- 修复 LZMA 库构造阶段访问未配置的固定地址：仅链接无构造函数的 raw 解码库。

**预发行版：只通过离线构建、源码路径测试和产物检查。未验证本机的冷启动、真实按键、
ResetReason 协议、原厂 Fastboot USB 枚举或刷写。不能承诺始终能进入 Fastboot，
尤其无法保证 BDS 入口之前发生异常时可恢复。**

独立 `efisp.img` 是同一份原始 AArch64 EFI 可执行文件，内容与模块内 `BDS.efi` 完全一致，
不是 FAT 文件系统镜像，不包含 ABL、boot.efi 或图片。它依赖匹配的外层 ABL 及已有启动环境；
模块内的工具与图片另部署到 persist/efisp。不要把 efisp.img 当成 ABL 镜像。
GOP 分辨率不匹配、图片缺失/损坏或内存不足时跳过图片，不阻止启动。
每个文件有尺寸限制和解压后 CRC32 检查；图片互相独立，坏一张会尝试其他图片。

## 已有 GBL 环境的安装方式

1. 在 Magisk/KernelSU 管理器安装本模块，语言跟随系统或已有模块设置。
2. 安装只布置管理工具，不刷写固件、不格式化、不重启；已移除旧版首次假回锁部署流程。
3. 已有 `/mnt/vendor/persist/efisp/boot.efi` 的设备，安装后在 WebUI 选择 **更新 BDS、工具与开机图片**。
   此操作会把 BDS 写入 efisp，并部署工具和图片，不改 A/B 槽位或 ABL。
4. 更新完成后等待用户自行安排下一次开机观察，不会自动重启。
   源文件和 host 测试通过不等于已完成本机实际启动画面验证。

更新前检查 persist 空间，预留至少 2 MiB。更新前的 efisp 原始分区和启动目录保存在
模块 `tmp/efisp-before.img` 与 `tmp/efisp-files-before.tar`；后续更新会覆盖这组备份，
需要长期保留时请复制到模块目录以外。

模块 ID 和显示名称均为 `gbl_uefi`。如果管理器中还留有旧 `fake_bl_efisp` 模块，
请不要同时使用两个模块发起更新任务。卸载模块不会自动删除已部署的 BDS 或 persist 图片。

## 文件与扩展

- `/mnt/vendor/persist/efisp/splash/1.sfb` … `7.sfb`：随机图片。
- `efisp/BOOTENTRIES`：EFI 启动项列表。
- `efisp/tools/`：UEFI 工具。
- WebUI：只读防回滚检查和 BDS/BL 更新工具。

删除或移走 `splash` 目录可以停用人物图片（普通默认启动的图片阶段会清为黑色；
按键菜单路径不做这次清屏）。
更换图片需要用仓库 `tools/splash/build_splash.py` 转换，PNG/JPEG 不能直接改扩展名使用。
当前绘制器固定匹配本次设备分辨率；其他分辨率应明确适配后再构建。

Current artwork targets a 1200x2608 GOP. It stores original-size pixels losslessly,
then uses integer bilinear scaling with black margins. It does not modify signed
vendor UEFI/imagefv resources. Missing or corrupt artwork is non-fatal.
