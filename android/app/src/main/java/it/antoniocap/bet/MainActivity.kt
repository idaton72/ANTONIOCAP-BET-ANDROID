package it.antoniocap.bet

import android.app.Activity
import android.os.Bundle
import android.widget.*
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

class MainActivity : Activity() {

    private lateinit var server: EditText
    private lateinit var status: TextView
    private lateinit var results: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        server = findViewById(R.id.server)
        status = findViewById(R.id.status)
        results = findViewById(R.id.results)

        val prefs = getSharedPreferences("antoniocap", MODE_PRIVATE)
        server.setText(prefs.getString("server", ""))

        findViewById<Button>(R.id.test).setOnClickListener { testServer() }
        findViewById<Button>(R.id.load).setOnClickListener { loadTop50() }
    }

    private fun baseUrl(): String {
        val base = server.text.toString().trim().trimEnd('/')
        getSharedPreferences("antoniocap", MODE_PRIVATE)
            .edit().putString("server", base).apply()
        return base
    }

    private fun request(path: String, readTimeout: Int = 20000): String {
        val base = baseUrl()

        require(base.startsWith("http://") || base.startsWith("https://")) {
            "Inserisci un indirizzo http:// o https:// valido"
        }

        val c = URL("$base$path").openConnection() as HttpURLConnection
        c.connectTimeout = 12000
        c.readTimeout = readTimeout
        c.requestMethod = "GET"

        val code = c.responseCode
        val stream =
            if (code in 200..299) c.inputStream else c.errorStream

        val body = stream?.bufferedReader()?.use { it.readText() }.orEmpty()

        if (code !in 200..299)
            error("Server HTTP $code: $body")

        return body
    }

    private fun testServer() {
        status.text = "Verifica motore…"
        results.text = ""

        thread {
            try {
                val j = JSONObject(request("/health"))

                runOnUiThread {
                    status.text =
                        "✓ Motore ${j.optString("engine", "3.8.6")} raggiungibile"
                }

            } catch (e: Exception) {
                runOnUiThread {
                    status.text = "✗ Server non raggiungibile"
                    results.text = e.message ?: e.javaClass.simpleName
                }
            }
        }
    }

    private fun loadTop50() {
        status.text = "Analisi TOP 50 in corso…"
        results.text = ""

        thread {
            try {

                val j = JSONObject(request("/api/top50", 240000))
                val rows = j.optJSONArray("rows") ?: JSONArray()
                val src = j.optJSONArray("sources") ?: JSONArray()

                val sb = StringBuilder("FONTI\n")

                for (i in 0 until src.length()) {
                    val s = src.optJSONObject(i) ?: continue

                    sb.append(if (s.optBoolean("ok")) "✓ " else "✗ ")
                        .append(s.optString("source", s.optString("name", "Fonte")))
                        .append("  ")
                        .append(s.optInt("count", 0))
                        .append("\n")
                }

                sb.append("\nTOP 50\n\n")

                for (i in 0 until rows.length()) {

                    val r = rows.optJSONObject(i) ?: continue

                    val score =
                        if (r.has("multisource_score"))
                            r.optInt("multisource_score")
                        else if (r.has("final_score"))
                            r.optInt("final_score")
                        else
                            r.optInt("score")

                    val pick =
                        r.optString(
                            "multisource_pick",
                            r.optString("pick")
                        )

                    val market =
                        r.optString(
                            "multisource_market",
                            r.optString("market")
                        )

                    sb.append(i + 1)
                        .append(". ")
                        .append(r.optString("home"))
                        .append(" - ")
                        .append(r.optString("away"))
                        .append("\n   ")
                        .append(market)
                        .append(" • ")
                        .append(pick)
                        .append(" • ")
                        .append(score)
                        .append("/100\n\n")
                }

                runOnUiThread {
                    status.text = "✓ ${rows.length()} partite • motore 3.8.6"
                    results.text = sb.toString()
                }

            } catch (e: Exception) {
                runOnUiThread {
                    status.text = "✗ Analisi non completata"
                    results.text = e.message ?: e.javaClass.simpleName
                }
            }
        }
    }
}
