#include <jni.h>
#include <pthread.h>
#include <cstdlib>
#include <ctime>
#include <string>
#include <atomic>

#define noinline __attribute__((__noinline__))

extern "C" JNIEXPORT jstring JNICALL
Java_simpleperf_example_cpp_MainActivity_stringFromJNI(
    JNIEnv* env,
    jobject /* this */) {
  std::string hello = "Hello from C++";
  return env->NewStringUTF(hello.c_str());
}

static void ThrowErrnoException(JNIEnv* env,
                                const char* function_name,
                                int err) {
  jclass cls = env->FindClass("android/system/ErrnoException");
  if (cls == nullptr) return;

  jmethodID cid = env->GetMethodID(cls, "<init>", "(Ljava/lang/String;I)V");
  if (cid == nullptr) return;

  jstring msg = env->NewStringUTF(function_name);
  if (msg == nullptr) return;

  auto obj = (jthrowable) env->NewObject(cls, cid, msg, err);
  if (obj == nullptr) return;

  env->Throw(obj);
}

noinline int CallFunction(int a) {
  const char* num_str = "1";
  // Prevents clang from optimizing out the string and conversion
  asm volatile("" : "+r" (num_str));
  char* endptr;
  long val = strtol(num_str, &endptr, 10);
  if (*endptr != '\0') {
    return a;
  }
  return a + static_cast<int>(val);
}

noinline void* BusyLoopThread(void*) {
  // 1. Name the thread so simpleperf can display it cleanly
  pthread_setname_np(pthread_self(), "BusyThreadC++");

  volatile int i = 0;
  while (true) {
    i = CallFunction(i);
  }
  return nullptr;
}

// 2. Atomic guard to prevent accidental duplicate threads
static std::atomic<bool> is_busy_thread_started{false};

extern "C" JNIEXPORT void JNICALL
Java_simpleperf_example_cpp_MainActivity_createBusyThreadFromJNI(
    JNIEnv* env,
    jobject /* this */) {

  // Ensure we only spawn one thread per process
  bool expected = false;
  if (is_busy_thread_started.compare_exchange_strong(expected, true)) {
    pthread_t thread;
    int ret = pthread_create(&thread, nullptr, BusyLoopThread, nullptr);
    if (ret) {
      ThrowErrnoException(env, "pthread_create", ret);
      is_busy_thread_started = false; // Reset on failure
    }
  }
}

static inline uint64_t GetSystemClock() {
  timespec ts{};
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return static_cast<uint64_t>(ts.tv_sec) * 1000000000ULL + ts.tv_nsec;
}

constexpr int LOOP_COUNT = 100000000;

static uint64_t noinline RunFunction() {
  uint64_t start_time_in_ns = GetSystemClock();
  for (volatile int i = 0; i < LOOP_COUNT; i += 1) {
    // Active CPU wait
  }
  return GetSystemClock() - start_time_in_ns;
}

static uint64_t noinline SleepFunction(uint64_t sleep_time_in_ns) {
  uint64_t start_time_in_ns = GetSystemClock();
  struct timespec req{};
  req.tv_sec = static_cast<time_t>(sleep_time_in_ns / 1000000000ULL);
  req.tv_nsec = static_cast<time_t>(sleep_time_in_ns % 1000000000ULL);
  nanosleep(&req, nullptr);
  return GetSystemClock() - start_time_in_ns;
}

static void* SleepThread(void*) {
  pthread_setname_np(pthread_self(), "SleepThreadC++");

  uint64_t total_sleep_time_in_ns = 0;
  uint64_t total_run_time_in_ns = 0;

  while (true) {
    total_run_time_in_ns += RunFunction();
    if (total_sleep_time_in_ns < total_run_time_in_ns) {
      total_sleep_time_in_ns +=
          SleepFunction(total_run_time_in_ns - total_sleep_time_in_ns);
    }
  }
  return nullptr;
}

static std::atomic<bool> is_sleep_thread_started{false};

extern "C" JNIEXPORT void JNICALL
Java_simpleperf_example_cpp_SleepActivity_createSleepThreadFromJNI(
    JNIEnv* env,
    jobject /* this */) {

  bool expected = false;
  if (is_sleep_thread_started.compare_exchange_strong(expected, true)) {
    pthread_t thread;
    int ret = pthread_create(&thread, nullptr, SleepThread, nullptr);
    if (ret) {
      ThrowErrnoException(env, "pthread_create", ret);
      is_sleep_thread_started = false;
    }
  }
}

extern "C" JNIEXPORT int JNICALL
Java_simpleperf_example_cpp_MixActivity_callFunction(
    JNIEnv* env,
    jobject /* this */,
    int a) {
  return CallFunction(a);
}
