package lab.steps

import android.app.Activity
import android.os.Bundle
import android.widget.TextView

class PrivacyActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(TextView(this).apply {
            textSize = 18f
            setPadding(32, 64, 32, 32)
            text = "Step Simulator — test data\n\n" +
                "Step access is required to write synthetic StepsRecord entries and read them back. " +
                "Records use the lab.steps source and manual-entry metadata.\n\n" +
                "The app does not send data over the network. Test results are stored locally; " +
                "the debug build supports exporting them to a Mac through ADB.\n\n" +
                "To delete test records or revoke permissions, open Health Connect → " +
                "App permissions → Step Simulator."
        })
    }
}
