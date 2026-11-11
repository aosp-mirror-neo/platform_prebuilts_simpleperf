package simpleperf.example.java;

import android.os.Bundle;
import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends AppCompatActivity {

  // 1. Static flag to track if the profiling thread is already active
  private static boolean isThreadRunning = false;

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    setContentView(R.layout.activity_main);

    // 2. Only start the thread if it hasn't been started yet
    if (!isThreadRunning) {
      createBusyThread();
      isThreadRunning = true;
    }
  }

  void createBusyThread() {
    new Thread(new Runnable() {
      // Keeping volatile to prevent ART from optimizing the loop away
      volatile int i = 0;

      @Override
      public void run() {
        while (true) {
          i = callFunction(i);
        }
      }

      private int callFunction(int a) {
        return a + 1;
      }
    }, "BusyThread").start();
  }
}