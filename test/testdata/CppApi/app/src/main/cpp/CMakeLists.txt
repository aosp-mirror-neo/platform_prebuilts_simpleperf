cmake_minimum_required(VERSION 3.22.1)
project(CppApiDemo LANGUAGES CXX)

set(SIMPLEPERF_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../../../../app_api/cpp")

add_library(
        native-lib
        SHARED
        native-lib.cpp
        ${SIMPLEPERF_DIR}/simpleperf.cpp)

target_include_directories(native-lib
        PRIVATE
        ${SIMPLEPERF_DIR})

find_library(
        log-lib
        log)

target_link_libraries(
        native-lib
        PRIVATE
        ${log-lib})
