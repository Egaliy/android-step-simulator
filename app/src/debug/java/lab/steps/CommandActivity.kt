package lab.steps

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import java.time.Instant

/** Debug-only adb entry point, protected by the system DUMP permission. */
class CommandActivity : MainActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState == null) execute(intent)
    }
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        execute(intent)
    }
    private fun execute(intent: Intent) {
        try {
            submit(Scenario(
                requireNotNull(intent.getStringExtra("scenario_id")),
                requireNotNull(intent.getStringExtra("steps")).toLong(),
                Instant.parse(requireNotNull(intent.getStringExtra("start"))),
                Instant.parse(requireNotNull(intent.getStringExtra("end")))
            ))
        } catch (e: Exception) {
            Toast.makeText(this, "Scenario error: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }
}
