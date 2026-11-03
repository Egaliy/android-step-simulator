package lab.steps

import java.time.Instant
import java.time.Duration

data class Scenario(val id: String, val count: Long, val start: Instant, val end: Instant) {
    fun validate() {
        require(id.matches(Regex("[a-zA-Z0-9_-]{1,80}"))) { "Invalid scenario ID" }
        require(count in 1..1_000_000) { "Steps: 1 to 1,000,000" }
        require(start < end) { "Start must be earlier than end" }
        require(end <= Instant.now()) { "The interval must not be in the future" }
        require(Duration.between(start, end) <= Duration.ofDays(1)) { "Maximum duration: 24 hours" }
        require(start >= Instant.now().minus(Duration.ofDays(29))) { "Use an interval within the last 29 days" }
    }
}
