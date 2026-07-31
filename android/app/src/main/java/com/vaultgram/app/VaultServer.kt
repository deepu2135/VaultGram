package com.vaultgram.app

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import com.google.gson.Gson
import fi.iki.elonen.NanoHTTPD
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import java.io.ByteArrayInputStream
import java.io.File
import java.util.UUID
import javax.crypto.SecretKey

class VaultServer(private val context: Context, port: Int = 8000) : NanoHTTPD(port) {
    private val dbHelper = DatabaseHelper(context)
    private val httpClient = OkHttpClient()
    private val gson = Gson()
    private val salt = byteArrayOf(0x12, 0x34, 0x56, 0x78, 0x90.toByte(), 0xAB.toByte(), 0xCD.toByte(), 0xEF.toByte(), 0xfe.toByte(), 0xdc.toByte(), 0xba.toByte(), 0x98.toByte(), 0x76, 0x54, 0x32, 0x10)
    private var masterKey: SecretKey? = null

    override fun serve(session: IHTTPSession): Response {
        val uri = session.uri
        val method = session.method

        try {
            if (method == Method.GET) {
                when {
                    uri == "/api/auth/status" -> {
                        if (masterKey == null) {
                            val savedPassphrase = getSetting("saved_passphrase")
                            if (!savedPassphrase.isNullOrEmpty()) {
                                try {
                                    masterKey = CryptoEngine.deriveKey(savedPassphrase, salt)
                                } catch (e: Exception) {
                                    e.printStackTrace()
                                }
                            }
                        }
                        val isConfigured = getSetting("passphrase_verifier") != null || getSetting("saved_passphrase") != null
                        val botConfigured = getSetting("bot_token") != null
                        val json = mapOf("configured" to isConfigured, "unlocked" to (masterKey != null), "bot_configured" to botConfigured)
                        return newJsonResponse(json)
                    }
                    uri == "/api/media" -> {
                        if (masterKey == null) {
                            val savedPassphrase = getSetting("saved_passphrase")
                            if (!savedPassphrase.isNullOrEmpty()) {
                                masterKey = CryptoEngine.deriveKey(savedPassphrase, salt)
                            }
                        }
                        if (masterKey == null) return new401Response()
                        val db = dbHelper.readableDatabase
                        val cursor = db.rawQuery("SELECT id, name, type, parent_id, size_bytes, mime_type, created_at FROM nodes WHERE type='file' ORDER BY created_at DESC", null)
                        val list = mutableListOf<Map<String, Any?>>()
                        while (cursor.moveToNext()) {
                            list.add(mapOf(
                                "id" to cursor.getString(0),
                                "name" to cursor.getString(1),
                                "type" to cursor.getString(2),
                                "parent_id" to cursor.getString(3),
                                "size_bytes" to cursor.getLong(4),
                                "mime_type" to cursor.getString(5),
                                "created_at" to cursor.getString(6)
                            ))
                        }
                        cursor.close()
                        return newJsonResponse(mapOf("media" to list))
                    }
                    uri == "/api/settings" -> {
                        val botToken = getSetting("bot_token") ?: ""
                        val channelId = getSetting("channel_id") ?: ""
                        return newJsonResponse(mapOf("bot_token" to botToken, "channel_id" to channelId))
                    }
                    uri.startsWith("/api/nodes") -> {
                        if (masterKey == null) return new401Response()
                        val parentId = session.parameters["parent_id"]?.firstOrNull()
                        val db = dbHelper.readableDatabase
                        val cursor = if (parentId.isNullOrEmpty()) {
                            db.rawQuery("SELECT id, name, type, parent_id, size_bytes, mime_type, created_at FROM nodes WHERE parent_id IS NULL ORDER BY type DESC, name ASC", null)
                        } else {
                            db.rawQuery("SELECT id, name, type, parent_id, size_bytes, mime_type, created_at FROM nodes WHERE parent_id=? ORDER BY type DESC, name ASC", arrayOf(parentId))
                        }
                        val list = mutableListOf<Map<String, Any?>>()
                        while (cursor.moveToNext()) {
                            list.add(mapOf(
                                "id" to cursor.getString(0),
                                "name" to cursor.getString(1),
                                "type" to cursor.getString(2),
                                "parent_id" to cursor.getString(3),
                                "size_bytes" to cursor.getLong(4),
                                "mime_type" to cursor.getString(5),
                                "created_at" to cursor.getString(6)
                            ))
                        }
                        cursor.close()
                        return newJsonResponse(mapOf("nodes" to list))
                    }
                    uri == "/api/sync" -> {
                        val botToken = getSetting("bot_token")
                        if (botToken.isNullOrEmpty() || masterKey == null) return new401Response()

                        var syncedCount = 0
                        try {
                            val url = "https://api.telegram.org/bot$botToken/getUpdates?limit=100"
                            val req = Request.Builder().url(url).build()
                            val response = httpClient.newCall(req).execute()
                            val jsonStr = response.body?.string() ?: ""
                            val jsonMap = gson.fromJson(jsonStr, Map::class.java)

                            val results = jsonMap["result"] as? List<Map<String, Any>> ?: emptyList()
                            val db = dbHelper.writableDatabase

                            for (item in results) {
                                val post = (item["channel_post"] as? Map<String, Any>) ?: (item["message"] as? Map<String, Any>) ?: continue
                                val doc = (post["document"] as? Map<String, Any>) ?: (post["video"] as? Map<String, Any>)
                                if (doc != null) {
                                    val fileId = doc["file_id"] as? String ?: continue
                                    var fileName = doc["file_name"] as? String ?: "telegram_video_${UUID.randomUUID().toString().take(6)}.mp4"
                                    val fileSize = (doc["file_size"] as? Number)?.toLong() ?: 0L
                                    var mimeType = doc["mime_type"] as? String ?: "video/mp4"

                                    val caption = post["caption"] as? String ?: ""
                                    if (caption.contains("Name: ")) {
                                        val match = Regex("Name:\\s*(.+)").find(caption)
                                        if (match != null) fileName = match.groupValues[1].trim()
                                    }

                                    if (fileName.endsWith(".mp4") || fileName.endsWith(".mkv") || fileName.endsWith(".avi") || fileName.endsWith(".bin") || mimeType.contains("video")) {
                                        mimeType = "video/mp4"
                                    }

                                    val cursor = db.rawQuery("SELECT id FROM nodes WHERE telegram_file_id=?", arrayOf(fileId))
                                    val exists = cursor.moveToFirst()
                                    cursor.close()

                                    if (!exists) {
                                        val nodeId = "file_${UUID.randomUUID().toString().replace("-", "").take(12)}"
                                        val cv = ContentValues().apply {
                                            put("id", nodeId)
                                            put("name", fileName)
                                            put("type", "file")
                                            put("telegram_file_id", fileId)
                                            put("size_bytes", fileSize)
                                            put("mime_type", mimeType)
                                            put("created_at", System.currentTimeMillis().toString())
                                        }
                                        db.insert("nodes", null, cv)
                                        syncedCount++
                                    }
                                }
                            }
                        } catch (e: Exception) {
                            e.printStackTrace()
                        }
                        return newJsonResponse(mapOf("status" to "success", "synced" to syncedCount))
                    }
                    uri.startsWith("/api/download/") -> {
                        val nodeId = uri.removePrefix("/api/download/")
                        val storageDir = File(context.filesDir, "storage")
                        val encFile = File(storageDir, "$nodeId.enc")

                        if (masterKey == null) return new401Response()

                        if (!encFile.exists()) {
                            val db = dbHelper.readableDatabase
                            val cursor = db.rawQuery("SELECT telegram_file_id FROM nodes WHERE id=?", arrayOf(nodeId))
                            var telegramFileId: String? = null
                            if (cursor.moveToFirst()) telegramFileId = cursor.getString(0)
                            cursor.close()

                            val botToken = getSetting("bot_token")
                            if (!telegramFileId.isNullOrEmpty() && !botToken.isNullOrEmpty()) {
                                try {
                                    val getFileUrl = "https://api.telegram.org/bot$botToken/getFile?file_id=$telegramFileId"
                                    val req = Request.Builder().url(getFileUrl).build()
                                    val res = httpClient.newCall(req).execute()
                                    val jsonMap = gson.fromJson(res.body?.string(), Map::class.java)
                                    val result = jsonMap["result"] as? Map<String, Any>
                                    val filePath = result?.get("file_path") as? String

                                    if (!filePath.isNullOrEmpty()) {
                                        val dlUrl = "https://api.telegram.org/file/bot$botToken/$filePath"
                                        val dlReq = Request.Builder().url(dlUrl).build()
                                        val dlRes = httpClient.newCall(dlReq).execute()
                                        val dlBytes = dlRes.body?.bytes()
                                        if (dlBytes != null) {
                                            storageDir.mkdirs()
                                            encFile.writeBytes(dlBytes)
                                        }
                                    }
                                } catch (e: Exception) {
                                    e.printStackTrace()
                                }
                            }
                        }

                        if (!encFile.exists()) return newFixedLengthResponse(Response.Status.NOT_FOUND, "text/plain", "File not found")

                        return try {
                            val decrypted = CryptoEngine.decryptBytes(encFile.readBytes(), masterKey!!)
                            newFixedLengthResponse(Response.Status.OK, "video/mp4", ByteArrayInputStream(decrypted), decrypted.size.toLong())
                        } catch (e: Exception) {
                            newFixedLengthResponse(Response.Status.OK, "video/mp4", ByteArrayInputStream(encFile.readBytes()), encFile.length())
                        }
                    }
                    else -> {
                        val assetPath = if (uri == "/" || uri.isEmpty()) "index.html" else uri.removePrefix("/")
                        return try {
                            val stream = context.assets.open(assetPath)
                            val mime = when {
                                assetPath.endsWith(".html") -> "text/html"
                                assetPath.endsWith(".css") -> "text/css"
                                assetPath.endsWith(".js") -> "application/javascript"
                                assetPath.endsWith(".png") -> "image/png"
                                else -> "text/plain"
                            }
                            newChunkedResponse(Response.Status.OK, mime, stream)
                        } catch (e: Exception) {
                            newFixedLengthResponse(Response.Status.NOT_FOUND, "text/plain", "Asset not found")
                        }
                    }
                }
            } else if (method == Method.POST) {
                val files = mutableMapOf<String, String>()
                session.parseBody(files)
                val postData = files["postData"] ?: ""

                when (uri) {
                    "/api/auth/setup" -> {
                        val map = gson.fromJson(postData, Map::class.java)
                        val passphrase = map["passphrase"] as? String ?: return new400Response()
                        val botToken = map["bot_token"] as? String
                        val channelId = map["channel_id"] as? String

                        val key = CryptoEngine.deriveKey(passphrase, salt)
                        val verifier = CryptoEngine.encryptBytes("{\"test\":\"ok\"}".toByteArray(), key)
                        saveSetting("passphrase_verifier", android.util.Base64.encodeToString(verifier, android.util.Base64.NO_WRAP))
                        saveSetting("saved_passphrase", passphrase)
                        if (!botToken.isNullOrEmpty()) saveSetting("bot_token", botToken!!)
                        if (!channelId.isNullOrEmpty()) saveSetting("channel_id", channelId!!)

                        masterKey = key
                        return newJsonResponse(mapOf("status" to "success", "unlocked" to true))
                    }
                    "/api/auth/unlock" -> {
                        val map = gson.fromJson(postData, Map::class.java)
                        val passphrase = map["passphrase"] as? String ?: return new400Response()
                        val verifierBase64 = getSetting("passphrase_verifier") ?: return new401Response()

                        val key = CryptoEngine.deriveKey(passphrase, salt)
                        return try {
                            val verifierBytes = android.util.Base64.decode(verifierBase64, android.util.Base64.NO_WRAP)
                            val decrypted = String(CryptoEngine.decryptBytes(verifierBytes, key))
                            if (decrypted.contains("test")) {
                                masterKey = key
                                saveSetting("saved_passphrase", passphrase)
                                newJsonResponse(mapOf("status" to "success", "unlocked" to true))
                            } else {
                                new401Response()
                            }
                        } catch (e: Exception) {
                            new401Response()
                        }
                    }
                    "/api/auth/lock" -> {
                        masterKey = null
                        saveSetting("saved_passphrase", "")
                        return newJsonResponse(mapOf("status" to "success", "unlocked" to false))
                    }
                    "/api/settings" -> {
                        val map = gson.fromJson(postData, Map::class.java)
                        (map["bot_token"] as? String)?.let { saveSetting("bot_token", it) }
                        (map["channel_id"] as? String)?.let { saveSetting("channel_id", it) }
                        return newJsonResponse(mapOf("status" to "success"))
                    }
                    "/api/folders/create" -> {
                        val map = gson.fromJson(postData, Map::class.java)
                        val name = map["name"] as? String ?: return new400Response()
                        val parentId = map["parent_id"] as? String
                        val folderId = "dir_${UUID.randomUUID().toString().replace("-", "").take(12)}"

                        val db = dbHelper.writableDatabase
                        val cv = ContentValues().apply {
                            put("id", folderId)
                            put("name", name)
                            put("type", "directory")
                            put("parent_id", parentId)
                            put("created_at", System.currentTimeMillis().toString())
                        }
                        db.insert("nodes", null, cv)
                        return newJsonResponse(mapOf("status" to "success", "folder_id" to folderId))
                    }
                    "/api/nodes/wipe" -> {
                        val db = dbHelper.writableDatabase
                        db.execSQL("DELETE FROM nodes")
                        val storageDir = File(context.filesDir, "storage")
                        storageDir.listFiles()?.forEach { it.delete() }
                        return newJsonResponse(mapOf("status" to "success"))
                    }
                    "/api/nodes/cleanup" -> {
                        val db = dbHelper.writableDatabase
                        val storageDir = File(context.filesDir, "storage")
                        val cursor = db.rawQuery("SELECT id FROM nodes WHERE type='file'", null)
                        var count = 0
                        while (cursor.moveToNext()) {
                            val id = cursor.getString(0)
                            val encFile = File(storageDir, "$id.enc")
                            if (!encFile.exists()) {
                                db.delete("nodes", "id=?", arrayOf(id))
                                count++
                            }
                        }
                        cursor.close()
                        return newJsonResponse(mapOf("status" to "success", "cleaned" to count))
                    }
                    "/api/nodes/delete" -> {
                        val map = gson.fromJson(postData, Map::class.java)
                        val nodeId = map["node_id"] as? String ?: return new400Response()
                        val db = dbHelper.writableDatabase
                        db.delete("nodes", "id=?", arrayOf(nodeId))
                        val storageDir = File(context.filesDir, "storage")
                        File(storageDir, "$nodeId.enc").delete()
                        return newJsonResponse(mapOf("status" to "success"))
                    }
                    "/api/upload" -> {
                        if (masterKey == null) return new401Response()
                        val tmpFilePath = files["file"] ?: files.values.firstOrNull() ?: return new400Response()
                        val rawFile = File(tmpFilePath)
                        val filename = session.parameters["filename"]?.firstOrNull() ?: rawFile.name ?: "upload.bin"

                        val nodeId = "file_${UUID.randomUUID().toString().replace("-", "").take(12)}"
                        val storageDir = File(context.filesDir, "storage")
                        storageDir.mkdirs()
                        val encFile = File(storageDir, "$nodeId.enc")

                        val sha256 = CryptoEngine.encryptFile(rawFile, encFile, masterKey!!)
                        val mimeType = context.contentResolver.getType(android.net.Uri.fromFile(rawFile)) ?: "application/octet-stream"

                        val db = dbHelper.writableDatabase
                        val cv = ContentValues().apply {
                            put("id", nodeId)
                            put("name", filename)
                            put("type", "file")
                            put("size_bytes", rawFile.length())
                            put("mime_type", mimeType)
                            put("sha256", sha256)
                            put("created_at", System.currentTimeMillis().toString())
                        }
                        db.insert("nodes", null, cv)

                        // Trigger Background Sync to Telegram Bot
                        val botToken = getSetting("bot_token")
                        val channelId = getSetting("channel_id")
                        if (!botToken.isNullOrEmpty() && !channelId.isNullOrEmpty()) {
                            Thread {
                                try {
                                    val url = "https://api.telegram.org/bot$botToken/sendDocument"
                                    val caption = "🔒 VaultGram Encrypted Cloud File\n📄 Name: $filename\n🔑 Node ID: $nodeId\n📦 Size: ${rawFile.length()} bytes"
                                    val body = MultipartBody.Builder()
                                        .setType(MultipartBody.FORM)
                                        .addFormDataPart("chat_id", channelId)
                                        .addFormDataPart("caption", caption)
                                        .addFormDataPart("document", filename, encFile.asRequestBody("application/octet-stream".toMediaType()))
                                        .build()
                                    val req = Request.Builder().url(url).post(body).build()
                                    httpClient.newCall(req).execute()
                                } catch (e: Exception) {
                                    e.printStackTrace()
                                }
                            }.start()
                        }

                        return newJsonResponse(mapOf("status" to "success", "node_id" to nodeId, "name" to filename))
                    }
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
            return newFixedLengthResponse(Response.Status.INTERNAL_ERROR, "text/plain", e.message ?: "Server error")
        }

        return newFixedLengthResponse(Response.Status.NOT_FOUND, "text/plain", "Not found")
    }

    private fun saveSetting(key: String, value: String) {
        try {
            val db = dbHelper.writableDatabase
            db.execSQL("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            val cv = ContentValues().apply {
                put("key", key)
                put("value", value)
            }
            db.insertWithOnConflict("settings", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private fun getSetting(key: String): String? {
        return try {
            val db = dbHelper.readableDatabase
            db.execSQL("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            val cursor = db.rawQuery("SELECT value FROM settings WHERE key=?", arrayOf(key))
            var valResult: String? = null
            if (cursor.moveToFirst()) valResult = cursor.getString(0)
            cursor.close()
            valResult
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }

    private fun newJsonResponse(data: Any): Response {
        val json = gson.toJson(data)
        return newFixedLengthResponse(Response.Status.OK, "application/json", json)
    }

    private fun new401Response(): Response = newFixedLengthResponse(Response.Status.UNAUTHORIZED, "application/json", "{\"detail\":\"Unauthorized\"}")
    private fun new400Response(): Response = newFixedLengthResponse(Response.Status.BAD_REQUEST, "application/json", "{\"detail\":\"Bad request\"}")

    private class DatabaseHelper(context: Context) : SQLiteOpenHelper(context, "vault.db", null, 1) {
        override fun onCreate(db: SQLiteDatabase) {
            createTables(db)
        }
        override fun onOpen(db: SQLiteDatabase) {
            super.onOpen(db)
            createTables(db)
        }
        override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {}

        private fun createTables(db: SQLiteDatabase) {
            db.execSQL("CREATE TABLE IF NOT EXISTS nodes (id TEXT PRIMARY KEY, name TEXT, type TEXT, parent_id TEXT, telegram_msg_id INTEGER, telegram_file_id TEXT, size_bytes INTEGER, mime_type TEXT, sha256 TEXT, created_at TEXT)")
            db.execSQL("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        }
    }
}
