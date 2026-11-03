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
            text = "Step Simulator — лабораторные данные\n\n" +
                "Доступ к шагам нужен для записи синтетических StepsRecord и чтения их обратно. " +
                "Записи имеют источник lab.steps и тип ручного ввода.\n\n" +
                "Приложение не отправляет данные в сеть. Результаты тестов хранятся локально; " +
                "debug-сборка позволяет выгружать их на Mac через ADB.\n\n" +
                "Удалить тестовые записи и отозвать разрешения можно в Health Connect → " +
                "Разрешения приложений → Step Simulator."
        })
    }
}
