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
package simpleperf.demo.cpp_api

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import kotlin.time.Duration.Companion.milliseconds
import kotlinx.coroutines.delay

class MainActivity : ComponentActivity() {

  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)

    // Prevent spawning duplicate native workloads on rotation
    if (!isNativeInitialized) {
      runNativeCode()
      isNativeInitialized = true
    }

    setContent {
      MaterialTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
          // 1. State is now hoisted up to the Activity level
          var count by remember { mutableLongStateOf(0L) }

          // 2. The background polling loop runs here
          LaunchedEffect(Unit) {
            while (true) {
              count = getBusyThreadCount()
              delay(1000.milliseconds)
            }
          }

          // 3. We pass the state down to the UI
          Greeting(count = count)
        }
      }
    }
  }

  private external fun runNativeCode()

  private external fun getBusyThreadCount(): Long

  companion object {
    // Load the native library
    init {
      System.loadLibrary("native-lib")
    }

    // 2. Static flag to ensure native threads/setup only happen once
    private var isNativeInitialized = false
  }
}

@Composable
fun Greeting(count: Long) {
  Box(contentAlignment = Alignment.Center, modifier = Modifier.fillMaxSize()) {
    Text(text = "CppApi Count: $count")
  }
}

@Preview(showBackground = true)
@Composable
fun GreetingPreview() {
  MaterialTheme {
    Greeting(count=42L)
  }
}
