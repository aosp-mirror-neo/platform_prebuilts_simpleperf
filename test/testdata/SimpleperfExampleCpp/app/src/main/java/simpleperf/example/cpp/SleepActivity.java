package simpleperf.example.cpp;

import android.os.Bundle;
import androidx.appcompat.app.AppCompatActivity;

public class SleepActivity extends AppCompatActivity {

  static {
    System.loadLibrary("native-lib");
  }

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    setContentView(R.layout.activity_sleep);
    createSleepThreadFromJNI();
  }

  private native void createSleepThreadFromJNI();
}