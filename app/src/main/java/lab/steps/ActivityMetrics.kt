package lab.steps

import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.records.*
import androidx.health.connect.client.records.metadata.Metadata
import androidx.health.connect.client.units.Energy
import androidx.health.connect.client.units.Length
import org.json.JSONObject
import java.time.Instant
import java.time.ZoneId
import kotlin.math.abs

/** Explicit test values, not sensor measurements or personal energy estimates. */
data class ActivityMetrics(val distanceMeters: Double, val activeKcal: Double, val elevationMeters: Double, val workoutStart: Instant? = null) {
    fun validate(s: Scenario) {
        require(distanceMeters.isFinite() && distanceMeters in 0.0..1000000.0) { "Invalid distance" }
        require(activeKcal.isFinite() && activeKcal in 0.0..100000.0) { "Invalid active calories" }
        require(elevationMeters.isFinite() && elevationMeters in 0.0..100000.0) { "Invalid elevation gain" }
        require(workoutStart == null || (workoutStart <= s.start && workoutStart >= s.end.minusSeconds(86400))) { "Invalid workout start" }
    }
    suspend fun writeAndVerify(client: HealthConnectClient, s: Scenario, packageName: String): JSONObject {
        val zone = ZoneId.systemDefault().rules
        fun metadata(kind: String) = Metadata.manualEntry(clientRecordId = "synthetic-${s.id}-$kind", clientRecordVersion = 1)
        val records = mutableListOf<Record>(
            DistanceRecord(startTime=s.start, endTime=s.end, startZoneOffset=zone.getOffset(s.start), endZoneOffset=zone.getOffset(s.end), distance=Length.meters(distanceMeters), metadata=metadata("distance")),
            ActiveCaloriesBurnedRecord(startTime=s.start, endTime=s.end, startZoneOffset=zone.getOffset(s.start), endZoneOffset=zone.getOffset(s.end), energy=Energy.kilocalories(activeKcal), metadata=metadata("active-kcal")),
            ElevationGainedRecord(startTime=s.start, endTime=s.end, startZoneOffset=zone.getOffset(s.start), endZoneOffset=zone.getOffset(s.end), elevation=Length.meters(elevationMeters), metadata=metadata("elevation"))
        )
        workoutStart?.let { a -> records.add(ExerciseSessionRecord(startTime=a, endTime=s.end, startZoneOffset=zone.getOffset(a), endZoneOffset=zone.getOffset(s.end), exerciseType=ExerciseSessionRecord.EXERCISE_TYPE_WALKING, title="Synthetic walking test", notes="Manual synthetic test data; not sensor measurements.", metadata=metadata("walking"))) }
        val ids = client.insertRecords(records).recordIdsList
        check(ids.size == records.size) { "Incomplete metrics write" }
        val distance = client.readRecord(DistanceRecord::class,ids[0]).record
        val calories = client.readRecord(ActiveCaloriesBurnedRecord::class,ids[1]).record
        val elevation = client.readRecord(ElevationGainedRecord::class,ids[2]).record
        for (r in listOf<Record>(distance,calories,elevation)) {
            check(r.metadata.dataOrigin.packageName == packageName && r.metadata.recordingMethod == Metadata.RECORDING_METHOD_MANUAL_ENTRY) { "Unexpected metrics source" }
        }
        check(distance.startTime == s.start && distance.endTime == s.end && abs(distance.distance.inMeters-distanceMeters)<0.000001)
        check(calories.startTime == s.start && calories.endTime == s.end && abs(calories.energy.inKilocalories-activeKcal)<0.000001)
        check(elevation.startTime == s.start && elevation.endTime == s.end && abs(elevation.elevation.inMeters-elevationMeters)<0.000001)
        val result = JSONObject().put("distance_m",distance.distance.inMeters).put("active_kcal",calories.energy.inKilocalories).put("elevation_m",elevation.elevation.inMeters).put("status","PASS")
        workoutStart?.let { a ->
            val exercise = client.readRecord(ExerciseSessionRecord::class,ids[3]).record
            check(exercise.startTime == a && exercise.endTime == s.end && exercise.exerciseType == ExerciseSessionRecord.EXERCISE_TYPE_WALKING && exercise.metadata.dataOrigin.packageName == packageName && exercise.metadata.recordingMethod == Metadata.RECORDING_METHOD_MANUAL_ENTRY)
            result.put("workout_start",a.toString()).put("workout_end",s.end.toString())
        }
        result.put("record_ids",org.json.JSONArray(ids))
        return result
    }
}
