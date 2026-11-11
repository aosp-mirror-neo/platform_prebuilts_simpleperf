package simpleperf.example.java;

import android.app.Service;
import android.content.Intent;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.Message;
import android.os.Messenger;

public class MultiProcessService extends Service {

  public static final int MSG_START_BUSY_THREAD = 1;
  // Initialize with the Service's main looper
  final Messenger mMessenger = new Messenger(new IncomingHandler(Looper.getMainLooper()));

  public MultiProcessService() {
  }

  @Override
  public IBinder onBind(Intent intent) {
    return mMessenger.getBinder();
  }

  void createBusyThread() {
    new Thread(new Runnable() {
      volatile int i = 0;

      @Override
      public void run() {
        // The intentional busy wait loop for profiling
        while (true) {
          i = callFunction(i);
        }
      }

      private int callFunction(int a) {
        return a + 1;
      }
    }, "BusyService").start();
  }

  // Explicitly require a Looper to prevent crashes on Android 11+
  class IncomingHandler extends Handler {

    IncomingHandler(Looper looper) {
      super(looper);
    }

    @Override
    public void handleMessage(Message msg) {
      switch (msg.what) {
        case MSG_START_BUSY_THREAD:
          createBusyThread();
          break; // Added break so future test cases don't fall through
      }
      super.handleMessage(msg);
    }
  }
}