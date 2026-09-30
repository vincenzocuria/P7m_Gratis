package app.vcuria.p7m_gratis

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import java.util.concurrent.Executors

class MainActivity : FlutterActivity() {
    private var channel: MethodChannel? = null
    private val reader = Executors.newSingleThreadExecutor()
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        channel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "app.vcuria.p7m/files")
        channel!!.setMethodCallHandler { call, result ->
            if (call.method == "initialFile") {
                val uri = documentUri(intent)
                if (uri == null) result.success(null) else read(uri) { data, error ->
                    if (error != null) result.error("READ", error, null) else result.success(data)
                }
            } else result.notImplemented()
        }
    }
    private fun documentUri(source: Intent?): Uri? = when(source?.action) {
        Intent.ACTION_VIEW -> source.data
        Intent.ACTION_SEND -> source.getParcelableExtra(Intent.EXTRA_STREAM) as? Uri
        else -> null
    }
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        documentUri(intent)?.let { uri -> read(uri) { data, error ->
            channel?.invokeMethod(if (error == null) "openFile" else "fileError", data ?: error)
        } }
    }
    private fun read(uri: Uri, complete: (Map<String, Any>?, String?) -> Unit) {
        reader.execute {
            try {
                require(uri.scheme == "content" || uri.scheme == "file")
                var name = "documento.p7m"
                contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
                    if (cursor.moveToFirst()) name = cursor.getString(0) ?: name
                }
                val bytes = contentResolver.openInputStream(uri)!!.use { stream ->
                    val output = java.io.ByteArrayOutputStream()
                    val buffer = ByteArray(65536)
                    while (true) {
                        val count = stream.read(buffer)
                        if (count < 0) break
                        require(output.size() + count <= 50 * 1024 * 1024) { "Limite di 50 MB superato" }
                        output.write(buffer, 0, count)
                    }
                    output.toByteArray()
                }
                runOnUiThread { complete(mapOf("bytes" to bytes, "name" to name), null) }
            } catch (e: Exception) {
                runOnUiThread { complete(null, e.message ?: "Impossibile leggere il documento") }
            }
        }
    }
    override fun onDestroy() { reader.shutdown(); super.onDestroy() }
}
