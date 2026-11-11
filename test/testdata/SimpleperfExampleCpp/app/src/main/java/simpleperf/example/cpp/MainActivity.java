package simpleperf.example.cpp;

import android.os.Bundle;
import android.widget.TextView;
import androidx.appcompat.app.AppCompatActivity;
import simpleperf.example.cpp.databinding.ActivityMainBinding;

public class MainActivity extends AppCompatActivity {

  private static boolean isThreadStarted = false;

  static {
    System.loadLibrary("native-lib");
  }

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);

    // Made local to onCreate
    ActivityMainBinding binding = ActivityMainBinding.inflate(getLayoutInflater());
    setContentView(binding.getRoot());

    TextView tv = binding.sampleText;
    tv.setText(stringFromJNI());

    if (!isThreadStarted) {
      createBusyThreadFromJNI();
      isThreadStarted = true;
    }
  }

  public native String stringFromJNI();

  private native void createBusyThreadFromJNI();
}