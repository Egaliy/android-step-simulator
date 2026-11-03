package lab.steps

import android.content.Intent
import android.os.Bundle
import android.text.InputType
import android.widget.*
import androidx.activity.ComponentActivity
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.metadata.Metadata
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import java.util.UUID

open class MainActivity : ComponentActivity() {
    private lateinit var steps: EditText
    private lateinit var start: EditText
    private lateinit var end: EditText
    private lateinit var status: TextView
    private lateinit var generate: Button
    private var busy = false
    private val permissions = setOf(
        HealthPermission.getReadPermission(StepsRecord::class),
        HealthPermission.getWritePermission(StepsRecord::class)
    )
    private val request = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract()
    ) { granted ->
        status.text = if (granted.containsAll(permissions)) "Доступ разрешён. Можно запускать сценарий."
        else "Нужны оба разрешения: чтение и запись шагов."
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 48, 32, 32)
        }
        fun label(value: String, size: Float = 16f) = TextView(this).also {
            it.text = value; it.textSize = size; layout.addView(it)
        }
        label("Step Simulator", 28f)
        label("Лаборатория · синтетические данные\n")
        label("Количество шагов")
        steps = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_NUMBER
            setText("10000")
        }.also(layout::addView)
        label("Начало и конец (ISO 8601, UTC или смещение)")
        start = EditText(this).also(layout::addView)
        end = EditText(this).also(layout::addView)
        val finish = Instant.now().minusSeconds(5).truncatedTo(ChronoUnit.SECONDS)
        start.setText(finish.minusSeconds(3600).toString())
        end.setText(finish.toString())
        fun button(title: String, action: () -> Unit) = Button(this).also {
            it.text = title; it.setOnClickListener { action() }; layout.addView(it)
        }
        button("Разрешить доступ к шагам") {
            if (available()) request.launch(permissions)
        }
        generate = button("Generate · записать и проверить") {
            try {
                submit(Scenario(UUID.randomUUID().toString(), steps.text.toString().toLong(),
                    Instant.parse(start.text.toString().trim()), Instant.parse(end.text.toString().trim())))
            } catch (e: Exception) { status.text = "Ошибка ввода: ${e.message}" }
        }
        button("Открыть Health Connect") {
            try { startActivity(Intent(HealthConnectClient.ACTION_HEALTH_CONNECT_SETTINGS)) }
            catch (e: Exception) { status.text = "Не удалось открыть Health Connect: ${e.message}" }
        }
        button("О данных и разрешениях") { startActivity(Intent(this, PrivacyActivity::class.java)) }
        status = label("Сначала разрешите чтение и запись шагов.")
        status.setTextIsSelectable(true)
        setContentView(ScrollView(this).apply { addView(layout) })
        available()
    }

    private fun available(): Boolean {
        val code = HealthConnectClient.getSdkStatus(this)
        if (code != HealthConnectClient.SDK_AVAILABLE) {
            status.text = "Health Connect недоступен (код $code). Используйте Android 14+ и обновите системный модуль."
            return false
        }
        return true
    }

    protected fun submit(scenario: Scenario) {
        if (busy) return
        scenario.validate()
        busy = true
        generate.isEnabled = false
        status.text = "Запись и проверка…"
        lifecycleScope.launch {
            val result = JSONObject().put("scenario_id", scenario.id).put("expected", scenario.count)
                .put("start", scenario.start.toString()).put("end", scenario.end.toString())
            try {
                check(available()) { "Health Connect недоступен" }
                val client = HealthConnectClient.getOrCreate(this@MainActivity)
                check(client.permissionController.getGrantedPermissions().containsAll(permissions)) {
                    "Откройте Step Simulator и разрешите чтение и запись шагов"
                }
                val zone = ZoneId.systemDefault().rules
                val record = StepsRecord(
                    count = scenario.count, startTime = scenario.start, endTime = scenario.end,
                    startZoneOffset = zone.getOffset(scenario.start), endZoneOffset = zone.getOffset(scenario.end),
                    metadata = Metadata.manualEntry(clientRecordId = "synthetic-${scenario.id}", clientRecordVersion = 1)
                )
                val id = client.insertRecords(listOf(record)).recordIdsList.single()
                result.put("record_id", id)
                val read = client.readRecord(StepsRecord::class, id).record
                val passed = read.count == scenario.count && read.startTime == scenario.start &&
                    read.endTime == scenario.end && read.metadata.dataOrigin.packageName == packageName
                result.put("actual", read.count).put("origin", read.metadata.dataOrigin.packageName)
                    .put("recording_method", read.metadata.recordingMethod)
                    .put("status", if (passed) "PASS" else "FAIL")
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                result.put("status", "ERROR").put("error", e.message ?: e.javaClass.simpleName)
            } finally {
                busy = false
                generate.isEnabled = true
            }
            status.text = result.toString(2)
            // Atomic result files are available only through debug run-as, not external storage.
            try {
                val dir = File(filesDir, "results").apply { mkdirs() }
                val tmp = File(dir, "${scenario.id}.tmp")
                tmp.writeText(result.toString(2))
                check(tmp.renameTo(File(dir, "${scenario.id}.json"))) { "Не удалось сохранить результат" }
            } catch (e: Exception) { status.append("\nОшибка сохранения: ${e.message}") }
        }
    }
}
