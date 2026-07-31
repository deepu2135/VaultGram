package com.vaultgram.app

import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.SecretKey
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.PBEKeySpec
import javax.crypto.spec.SecretKeySpec

object CryptoEngine {
    private const val KEY_SIZE = 256
    private const val ITERATIONS = 100000
    private const val GCM_IV_LENGTH = 12
    private const val GCM_TAG_LENGTH = 128

    fun deriveKey(passphrase: String, salt: ByteArray): SecretKey {
        val factory = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
        val spec = PBEKeySpec(passphrase.toCharArray(), salt, ITERATIONS, KEY_SIZE)
        val tmp = factory.generateSecret(spec)
        return SecretKeySpec(tmp.encoded, "AES")
    }

    fun encryptBytes(data: ByteArray, secretKey: SecretKey): ByteArray {
        val iv = ByteArray(GCM_IV_LENGTH)
        SecureRandom().nextBytes(iv)

        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        val spec = GCMParameterSpec(GCM_TAG_LENGTH, iv)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey, spec)

        val cipherText = cipher.doFinal(data)
        return iv + cipherText
    }

    fun decryptBytes(encryptedData: ByteArray, secretKey: SecretKey): ByteArray {
        val iv = encryptedData.copyOfRange(0, GCM_IV_LENGTH)
        val cipherText = encryptedData.copyOfRange(GCM_IV_LENGTH, encryptedData.size)

        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        val spec = GCMParameterSpec(GCM_TAG_LENGTH, iv)
        cipher.init(Cipher.DECRYPT_MODE, secretKey, spec)

        return cipher.doFinal(cipherText)
    }

    fun encryptFile(inputFile: File, outputFile: File, secretKey: SecretKey): String {
        val rawBytes = inputFile.readBytes()
        val encrypted = encryptBytes(rawBytes, secretKey)
        outputFile.writeBytes(encrypted)

        val digest = MessageDigest.getInstance("SHA-256")
        val hashBytes = digest.digest(rawBytes)
        return hashBytes.joinToString("") { "%02x".format(it) }
    }
}
