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
                        val isConfigured = getSetting("passphrase_verifier") != null
                        val botConfigured = getSetting("bot_token") != null
                        val json = mapOf("configured" to isConfigured, "unlocked" to (masterKey != null), "bot_configured" to botConfigured)
                        return newJsonResponse(json)
                    }
                    uri == "/api/media" -> {
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
                    uri.startsWith("/api/download/") -> {
                        val nodeId = uri.removePrefix("/api/download/")
                        val storageDir = File(context.filesDir, "storage")
                        val encFile = File(storageDir, "$nodeId.enc")
                        if (!encFile.exists() || masterKey == null) return newFixedLengthResponse(Response.Status.NOT_FOUND, "text/plain", "File not found")

                        val decrypted = CryptoEngine.decryptBytes(encFile.readBytes(), masterKey!!)
                        return newFixedLengthResponse(Response.Status.OK, "application/octet-stream", ByteArrayInputStream(decrypted), decrypted.size.toLong())
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
                                newJsonResponse(mapOf("status" to "success", "unlocked" to true))
                            } else {
                                new401Response()
                            }
                        } catch (e: Exception) {
                            new401Response()
                        }
                    }
                    "/api/settings" -> {
                        val map = gson.fromJson(postData, Map::class.java)
                        (map["bot_token"] as? String)?.let { saveSetting("bot_token", it) }
                        (map["channel_id"] as? String)?.let { saveSetting("channel_id", it) }
                        return newJsonResponse(mapOf("status" to "success"))
                    }
                    "/api/nodes/wipe" -> {
                        val db = dbHelper.writableDatabase
                        db.execSQL("DELETE FROM nodes")
                        val storageDir = File(context.filesDir, "storage")
                        storageDir.listFiles()?.forEach { it.delete() }
                        return newJsonResponse(mapOf("status" to "success"))
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
                                    val body = MultipartBody.Builder()
                                        .setType(MultipartBody.FORM)
                                        .addFormDataPart("chat_id", channelId)
                                        .addFormDataPart("document", encFile.name, encFile.asRequestBody("application/octet-stream".toMediaType()))
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
        val db = dbHelper.writableDatabase
        val cv = ContentValues().apply {
            put("key", key)
            put("value", value)
        }
        db.insertWithOnConflict("settings", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
    }

    private fun getSetting(key: String): String? {
        val db = dbHelper.readableDatabase
        val cursor = db.rawQuery("SELECT value FROM settings WHERE key=?", arrayOf(key))
        var valResult: String? = null
        if (cursor.moveToFirst()) valResult = cursor.getString(0)
        cursor.close()
        return valResult
    }

    private fun newJsonResponse(data: Any): Response {
        val json = gson.toJson(data)
        return newFixedLengthResponse(Response.Status.OK, "application/json", json)
    }

    private fun new401Response(): Response = newFixedLengthResponse(Response.Status.UNAUTHORIZED, "application/json", "{\"detail\":\"Unauthorized\"}")
    private fun new400Response(): Response = newFixedLengthResponse(Response.Status.BAD_REQUEST, "application/json", "{\"detail\":\"Bad request\"}")

    private class DatabaseHelper(context: Context) : SQLiteOpenHelper(context, "vault.db", null, 1) {
        override fun onCreate(db: SQLiteDatabase) {
            db.execSQL("CREATE TABLE IF NOT EXISTS nodes (id TEXT PRIMARY KEY, name TEXT, type TEXT, parent_id TEXT, telegram_msg_id INTEGER, telegram_file_id TEXT, size_bytes INTEGER, mime_type TEXT, sha256 TEXT, created_at TEXT)")
            db.execSQL("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        }
        override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {}
    }
}
