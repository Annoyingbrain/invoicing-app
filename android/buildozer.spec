[app]
title = Invoice MarLoN
package.name = invoicemarlon
package.domain = com.marlon

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf

version = 1.0.0

requirements = python3,kivy==2.3.0,reportlab,sqlite3

orientation = portrait
fullscreen = 0

android.permissions = WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,INTERNET
android.api = 33
android.minapi = 21
android.ndk = 25b
android.arch = arm64-v8a

# Accepts SDK/NDK licenses automatically during build
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
