package com.vaultgram.app

import android.os.Bundle
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    private lateinit var webView: WebView
    private var vaultServer: VaultServer? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // Start Embedded VaultEngine Server on 127.0.0.1:8000
        try {
            vaultServer = VaultServer(applicationContext, 8000)
            vaultServer?.start()
        } catch (e: Exception) {
            e.printStackTrace()
        }

        webView = WebView(this)
        setContentView(webView)

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = true
            allowContentAccess = true
            useWideViewPort = true
            loadWithOverviewMode = true
            cacheMode = WebSettings.LOAD_NO_CACHE
        }

        webView.webViewClient = WebViewClient()
        webView.loadUrl("http://127.0.0.1:8000/")
    }

    override fun onDestroy() {
        super.onDestroy()
        try {
            vaultServer?.stop()
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }
}
