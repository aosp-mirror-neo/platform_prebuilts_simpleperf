/*
 * Copyright (C) 2026 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package simpleperf.demo.java_api

import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.android.simpleperf.ProfileSession
import com.android.simpleperf.RecordOptions
import kotlin.system.exitProcess
import kotlin.time.Duration.Companion.milliseconds
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)

    setContent {
      MaterialTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
          // Replaces the TextView. Compose automatically updates the UI when this changes.
          var counter by remember { mutableLongStateOf(0L) }

          LaunchedEffect(Unit) {
            // 1. Launch the profiler on the IO dispatcher
            val profilerJob = launch(Dispatchers.IO) {
              runProfiler()
            }

            // 2. Launch the busy loop on the Default (CPU-intensive) dispatcher
            launch(Dispatchers.Default) {
              runBusyWorker(
                profilerJob = profilerJob,
                onTick = { count -> counter = count }
              )
            }
          }
          Box(contentAlignment = Alignment.Center, modifier = Modifier.fillMaxSize()) {
            Text(text = "JavaApi count: $counter")
          }
        }
      }
    }
  }

  private suspend fun runProfiler() {
    val recordOptions = RecordOptions()
    recordOptions.recordDwarfCallGraph().setDuration(100.0).setEvent("cpu-clock")
    val profileSession = ProfileSession()

    try {
      Log.e("simpleperf", "startRecording")
      profileSession.startRecording(recordOptions)

      (0 until 1).forEach { _ ->
        delay(1000.milliseconds) // Replaces Thread.sleep(1000)
        Log.e("simpleperf", "pauseRecording")
        profileSession.pauseRecording()

        delay(1000.milliseconds)
        Log.e("simpleperf", "resumeRecording")
        profileSession.resumeRecording()
      }

      delay(1000.milliseconds)
      Log.e("simpleperf", "stopRecording")
      profileSession.stopRecording()
      Log.e("simpleperf", "stopRecording successfully")

    } catch (e: Exception) {
      Log.e("simpleperf", "exception: ${e.message}")
    }
  }

  private suspend fun runBusyWorker(profilerJob: Job, onTick: (Long) -> Unit) {
    var times = 0L
    var dummy: Int

    // Replaces profileThread.isAlive()
    while (profilerJob.isActive) {
      dummy = 0
      while (dummy < 1000000) {
        dummy = callFunction(dummy)
      }

      delay(1.milliseconds) // Replaces Thread.sleep(1)

      times++

      // Updates the Compose state safely
      onTick(times)
    }

    // Exit after recording so test infrastructure can pull the trace file
    exitProcess(0)
  }

  private fun callFunction(a: Int): Int {
    return a + 1
  }
}
