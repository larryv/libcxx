//===----------------------------------------------------------------------===//
//
//                     The LLVM Compiler Infrastructure
//
// This file is distributed under the University of Illinois Open Source
// License. See LICENSE.TXT for details.
//
//===----------------------------------------------------------------------===//

// <atomic>

// struct atomic_flag

// atomic_flag(const atomic_flag&) = delete;

#include <atomic>
#include <cassert>

int main()
{
    std::atomic_flag f0;
    std::atomic_flag f(f0);
}