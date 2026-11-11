package simpleperf.example.kotlin

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlin.time.Duration
import kotlin.time.TimeSource

class SleepActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    SleepScreen()
                }
            }
        }
        createRunSleepCoroutine()
    }

    @Composable
    fun SleepScreen() {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(text = "SimpleperfExampleKotlin")
                Text(text = "Running a half busy half sleep coroutine!")
            }
        }
    }

    @Preview(showBackground = true)
    @Composable
    fun DefaultPreview() {
        MaterialTheme {
            SleepScreen()
        }
    }

    fun createRunSleepCoroutine() {
        CoroutineScope(Dispatchers.Default).launch {
            var counter = 0
            var totalRunTime: Duration = Duration.ZERO
            var totalSleepTime: Duration = Duration.ZERO

            fun runFunction(): Duration {
                val mark = TimeSource.Monotonic.markNow()
                var i = 0
                while (i < 10000000) {
                    counter = callFunction(counter)
                    i++
                }
                return mark.elapsedNow()
            }

            fun sleepFunction(sleepDuration: Duration): Duration {
                val mark = TimeSource.Monotonic.markNow()
                val millis = sleepDuration.inWholeMilliseconds
                val nanos = (sleepDuration.inWholeNanoseconds % 1_000_000).toInt()
                // Use Thread.sleep instead of delay() to ensure the off-cpu profiler
                // captures this specific application function on the OS thread sleep stack.
                Thread.sleep(millis, nanos)
                return mark.elapsedNow()
            }

            while (true) {
                totalRunTime += runFunction()
                if (totalSleepTime < totalRunTime) {
                    totalSleepTime += sleepFunction(totalRunTime - totalSleepTime)
                }
            }
        }
    }

    fun callFunction(i: Int): Int {
        return i + 1
    }
}
