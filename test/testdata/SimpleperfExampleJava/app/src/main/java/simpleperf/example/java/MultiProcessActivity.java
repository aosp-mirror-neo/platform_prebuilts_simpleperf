package simpleperf.example.java;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.os.Bundle;
import android.os.IBinder;
import android.os.Message;
import android.os.Messenger;
import android.os.RemoteException;
import android.util.Log;
import androidx.appcompat.app.AppCompatActivity;

public class MultiProcessActivity extends AppCompatActivity {

  public static final String TAG = "MultiProcessActivity";
  // 1. Static flags to prevent duplicate threads on screen rotation
  private static boolean isLocalThreadRunning = false;
  private static boolean isRemoteThreadStarted = false;
  Messenger mService = null;
  boolean mBound;
  private final ServiceConnection mConnection = new ServiceConnection() {
    @Override
    public void onServiceConnected(ComponentName componentName, IBinder iBinder) {
      mService = new Messenger(iBinder);
      mBound = true;

      // 3. Only tell the Service to start its thread once
      if (!isRemoteThreadStarted) {
        Message message = new Message();
        message.what = MultiProcessService.MSG_START_BUSY_THREAD;
        try {
          mService.send(message);
          isRemoteThreadStarted = true;
        } catch (RemoteException e) {
          Log.d(TAG, e.toString());
        }
      }
    }

    @Override
    public void onServiceDisconnected(ComponentName componentName) {
      mService = null;
      mBound = false;
    }
  };

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    setContentView(R.layout.activity_multi_process);

    bindService(new Intent(this, MultiProcessService.class), mConnection,
        Context.BIND_AUTO_CREATE);

    // 2. Only start the local thread once
    if (!isLocalThreadRunning) {
      createBusyThread();
      isLocalThreadRunning = true;
    }
  }

  @Override
  protected void onDestroy() {
    super.onDestroy();

    if (mBound) {
      unbindService(mConnection);
      mBound = false;
    }
  }

  void createBusyThread() {
    new Thread(new Runnable() {
      // Must remain volatile so ART doesn't optimize the loop away
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