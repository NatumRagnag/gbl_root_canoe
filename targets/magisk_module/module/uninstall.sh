#!/system/bin/sh

MODDIR=${0%/*}

rm -rf "$MODDIR/tmp"
ui_print "gbl_uefi 模块已卸载。已部署到 persist/efisp 的启动文件、图片和 efisp 分区中的 BDS 会保留。"
