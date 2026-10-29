package com.homecompetition.app

import android.app.Activity
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.Executors

class AppUpdateBridge(private val activity: Activity, messenger: BinaryMessenger) {
    private val channel = MethodChannel(messenger, "homecompetition/updates")
    private val worker = Executors.newSingleThreadExecutor()
    private val directory get() = File(activity.cacheDir, "app-updates").apply { mkdirs() }.canonicalFile

    @Suppress("DEPRECATION")
    private fun current(): PackageInfo = activity.packageManager.getPackageInfo(
        activity.packageName, if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES)

    @Suppress("DEPRECATION")
    private fun version(info: PackageInfo): Long = if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong()

    @Suppress("DEPRECATION")
    private fun signatures(info: PackageInfo): Set<String> {
        val certs = if (Build.VERSION.SDK_INT >= 28) info.signingInfo?.apkContentsSigners else info.signatures
        return certs?.map { signature ->
            MessageDigest.getInstance("SHA-256").digest(signature.toByteArray())
                .joinToString("") { "%02x".format(it) }
        }?.toSet() ?: emptySet()
    }

    @Suppress("DEPRECATION")
    private fun validate(args: Map<*, *>): File {
        val code = (args["versionCode"] as? Number)?.toLong() ?: error("Phiên bản không hợp lệ.")
        val size = (args["size"] as? Number)?.toLong() ?: error("Kích thước không hợp lệ.")
        val expected = args["sha256"] as? String ?: error("Thiếu mã kiểm tra gói cập nhật.")
        check(Regex("[0-9a-f]{64}").matches(expected) && size in 1024L..125829120L)
        val file = File(args["path"] as? String ?: error("Thiếu file cập nhật.")).canonicalFile
        check(file.parentFile == directory && file.name == "HomeCompetition-$code.apk" && file.isFile) {
            "File cập nhật không hợp lệ."
        }
        check(file.length() == size) { "Kích thước gói cập nhật không khớp." }
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(65536)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
            }
        }
        check(digest.digest().joinToString("") { "%02x".format(it) } == expected) {
            "Gói cập nhật không đúng mã kiểm tra. Hãy tải lại."
        }
        val flags = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
        val archive = activity.packageManager.getPackageArchiveInfo(file.path, flags)
            ?: error("Không đọc được gói APK.")
        val installed = current()
        check(archive.packageName == activity.packageName) { "Gói cập nhật không thuộc HomeCompetition." }
        check(version(archive) == code && code > version(installed)) { "Bản cập nhật không mới hơn ứng dụng đang cài." }
        val trusted = signatures(installed)
        check(trusted.isNotEmpty() && signatures(archive) == trusted) {
            "Chữ ký gói cập nhật không khớp ứng dụng đang cài."
        }
        return file
    }

    init {
        channel.setMethodCallHandler { call, result ->
            if (call.method == "info") {
                try {
                    val info = current()
                    val network = activity.getSystemService(ConnectivityManager::class.java)
                    result.success(mapOf("version" to (info.versionName ?: ""), "versionCode" to version(info),
                        "directory" to directory.path, "unmetered" to !network.isActiveNetworkMetered))
                } catch (_: Exception) { result.error("UPDATE_INFO", "Chưa đọc được thông tin ứng dụng.", null) }
            } else if (call.method == "validate" || call.method == "install") {
                worker.execute {
                    try {
                        val file = validate(call.arguments as? Map<*, *> ?: error("Thiếu thông tin gói cập nhật."))
                        activity.runOnUiThread {
                            if (activity.isDestroyed) return@runOnUiThread
                            try {
                                if (call.method == "validate") {
                                    result.success(null)
                                } else if (Build.VERSION.SDK_INT >= 26 && !activity.packageManager.canRequestPackageInstalls()) {
                                    activity.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                                        Uri.parse("package:${activity.packageName}")))
                                    result.success("permission_required")
                                } else {
                                    val uri = FileProvider.getUriForFile(activity, "${activity.packageName}.updates", file)
                                    activity.startActivity(Intent(Intent.ACTION_VIEW).apply {
                                        setDataAndType(uri, "application/vnd.android.package-archive")
                                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                                    })
                                    result.success("installer_opened")
                                }
                            } catch (_: Exception) { result.error("UPDATE_INSTALL", "Chưa mở được trình cài đặt Android.", null) }
                        }
                    } catch (error: Exception) {
                        activity.runOnUiThread {
                            if (!activity.isDestroyed) result.error("UPDATE_VERIFY", error.message ?: "Chưa xác minh được gói cập nhật.", null)
                        }
                    }
                }
            } else { result.notImplemented() }
        }
    }

    fun close() { channel.setMethodCallHandler(null); worker.shutdown() }
}
