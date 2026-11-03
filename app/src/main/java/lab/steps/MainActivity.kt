package lab.steps

import android.content.Intent
import android.os.Bundle
import android.text.InputType
import android.widget.*
import androidx.activity.ComponentActivity
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.*
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
    private val metricPermissions = setOf(DistanceRecord::class, ActiveCaloriesBurnedRecord::class, ElevationGainedRecord::class, ExerciseSessionRecord::class).flatMap {
        listOf(HealthPermission.getReadPermission(it), HealthPermission.getWritePermission(it))
    }.toSet()
    private val request = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract()
    ) { granted ->
        status.text = if (granted.containsAll(permissions + metricPermissions)) "Access granted. Ready to run a scenario."
        else "Allow read and write access to the selected activity data."
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
        label("Lab · synthetic data\n")
        label("Walking test: 0.70 m and 0.04 active kcal per step; 0 m climb")
        label("Step count")
        steps = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_NUMBER
            setText("10000")
        }.also(layout::addView)
        label("Start and end (ISO 8601, UTC or offset)")
        start = EditText(this).also(layout::addView)
        end = EditText(this).also(layout::addView)
        val finish = Instant.now().minusSeconds(5).truncatedTo(ChronoUnit.SECONDS)
        start.setText(finish.minusSeconds(3600).toString())
        end.setText(finish.toString())
        fun button(title: String, action: () -> Unit) = Button(this).also {
            it.text = title; it.setOnClickListener { action() }; layout.addView(it)
        }
        button("Allow activity data access") {
            if (available()) request.launch(permissions + metricPermissions)
        }
        generate = button("Generate · write and verify") {
            try {
                submit(Scenario(UUID.randomUUID().toString(), steps.text.toString().toLong(),
                    Instant.parse(start.text.toString().trim()), Instant.parse(end.text.toString().trim()),
                    ActivityMetrics(steps.text.toString().toLong() * 0.70, steps.text.toString().toLong() * 0.04, 0.0, Instant.parse(start.text.toString().trim()))))
            } catch (e: Exception) { status.text = "Input error: ${e.message}" }
        }
        button("Open Health Connect") {
            try { startActivity(Intent(HealthConnectClient.ACTION_HEALTH_CONNECT_SETTINGS)) }
            catch (e: Exception) { status.text = "Could not open Health Connect: ${e.message}" }
        }
        button("Data and permissions") { startActivity(Intent(this, PrivacyActivity::class.java)) }
        status = label("First, allow access to read and write steps.")
        status.setTextIsSelectable(true)
        setContentView(ScrollView(this).apply { addView(layout) })
        available()
    }

    private fun available(): Boolean {
        val code = HealthConnectClient.getSdkStatus(this)
        if (code != HealthConnectClient.SDK_AVAILABLE) {
            status.text = "Health Connect unavailable (code $code). Use Android 14+ and update the system module."
            return false
        }
        return true
    }

    protected fun submit(scenario: Scenario) {
        if (busy) return
        scenario.validate()
        busy = true
        generate.isEnabled = false
        status.text = "Writing and verifying…"
        lifecycleScope.launch {
            val result = JSONObject().put("scenario_id", scenario.id).put("expected", scenario.count)
                .put("start", scenario.start.toString()).put("end", scenario.end.toString())
            try {
                check(available()) { "Health Connect unavailable" }
                val client = HealthConnectClient.getOrCreate(this@MainActivity)
                check(client.permissionController.getGrantedPermissions().containsAll(permissions + if (scenario.metrics != null) metricPermissions else emptySet())) {
                    "Open Step Simulator and allow read/write access to the requested activity types"
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
                scenario.metrics?.let { result.put("metrics", it.writeAndVerify(client, scenario, packageName)) }
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
                check(tmp.renameTo(File(dir, "${scenario.id}.json"))) { "Could not save the result" }
            } catch (e: Exception) { status.append("\nSave error: ${e.message}") }
        }
    }
}
