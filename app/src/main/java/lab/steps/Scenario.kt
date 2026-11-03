package lab.steps

import java.time.Instant
import java.time.Duration

data class Scenario(val id: String, val count: Long, val start: Instant, val end: Instant) {
    fun validate() {
        require(id.matches(Regex("[a-zA-Z0-9_-]{1,80}"))) { "Некорректный ID сценария" }
        require(count in 1..1_000_000) { "Шаги: от 1 до 1 000 000" }
        require(start < end) { "Начало должно быть раньше конца" }
        require(end <= Instant.now()) { "Интервал не должен быть в будущем" }
        require(Duration.between(start, end) <= Duration.ofDays(1)) { "Максимум 24 часа" }
        require(start >= Instant.now().minus(Duration.ofDays(29))) { "Используйте последние 29 дней" }
    }
}
