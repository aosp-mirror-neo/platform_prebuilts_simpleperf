package simpleperf.example.cpp;

import android.os.Bundle;
import androidx.appcompat.app.AppCompatActivity;

public class MixActivity extends AppCompatActivity {

  // 1. Static flag to prevent thread duplication on screen rotation
  private static boolean isThreadRunning = false;

  static {
    System.loadLibrary("native-lib");
  }

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    setContentView(R.layout.activity_mix);

    // 2. Only spawn the thread once
    if (!isThreadRunning) {
      createBusyThread();
      isThreadRunning = true;
    }
  }

  void createBusyThread() {
    new Thread(new Runnable() {
      // Must remain volatile so ART doesn't strip the loop as dead code
      volatile int i = 0;

      @Override
      public void run() {
        // The Mixed Loop: Continuously jumps between Java and C++
        while (true) {
          i = callFunction(i);
        }
      }

    }, "MixThread").start(); // 3. Renamed to easily find it in simpleperf
  }

  private native int callFunction(int a);
}