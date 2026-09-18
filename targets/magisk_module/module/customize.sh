#!/system/bin/sh
# Install management tools only; firmware updates are explicit WebUI actions.
SKIPMOUNT=true
ui_print "============================================="
ui_print "  gbl_uefi - UEFI boot manager and playground"
ui_print "============================================="
ui_lang=zh
case "$(getprop persist.sys.locale 2>/dev/null)" in en*) ui_lang=en ;; esac
if [ -f /data/adb/modules/gbl_uefi/lang.txt ]; then
  case "$(cat /data/adb/modules/gbl_uefi/lang.txt)" in en) ui_lang=en ;; zh) ui_lang=zh ;; esac
fi
printf '%s\n' "$ui_lang" > "$MODPATH/lang.txt"
if [ "$ui_lang" = zh ]; then
  sed -i 's/^description=.*/description=GBL UEFI 实验项目：启动菜单、随机图片、防回滚检查；修复解压初始化并添加原厂 Fastboot 交接。预发行版，尚未真机验证。/' "$MODPATH/module.prop"
else
  sed -i 's/^description=.*/description=GBL UEFI playground: boot menu, random artwork, rollback inspection and native Fastboot handoff. Prerelease; no device boot validation./' "$MODPATH/module.prop"
fi
for item in BDS.efi bin/bl_flasher.sh bin/arb_check.sh bin/arb_inspect bin/patch_abl bin/extractfv; do
  [ -s "$MODPATH/$item" ] || abort "Missing module payload: $item"
done
for picture in 1 2 3 4 5 6 7; do
  [ -s "$MODPATH/efisp/splash/$picture.sfb" ] || abort "Missing artwork: $picture"
done
set_perm_recursive "$MODPATH" 0 0 0755 0644
set_perm_recursive "$MODPATH/bin" 0 0 0755 0755
set_perm "$MODPATH/customize.sh" 0 0 0755
set_perm "$MODPATH/uninstall.sh" 0 0 0755
if [ "$ui_lang" = zh ]; then
  ui_print "gbl_uefi 已安装。安装过程不刷写固件、不格式化、不重启。"
  ui_print "预发行版：启动和原厂 Fastboot 交接尚未完成真机验证。"
  ui_print "已有 GBL 环境：在 WebUI 选择更新 BDS、工具与开机图片。"
  ui_print "本模块不再提供需要清数据的首次假回锁部署流程。"
else
  ui_print "gbl_uefi installed. Installation does not flash firmware, format data or reboot."
  ui_print "Prerelease: boot and native Fastboot handoff are not device-validated."
  ui_print "For an existing GBL setup, use Update BDS, Tools & Artwork in the WebUI."
  ui_print "Fresh fake-lock provisioning is not part of this module."
fi
