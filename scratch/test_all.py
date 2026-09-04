import os
import sys

def run_all_tests():
    print("=================================================================")
    print("      AI RESEARCH LAB — FULL INTEGRATED TEST SUITE               ")
    print("=================================================================\n")
    
    test_files = [
        "scratch/test_slice1.py",
        "scratch/test_slice2.py",
        "scratch/test_slice3.py",
        "scratch/test_slice4.py",
        "scratch/test_slice5.py",
        "scratch/test_slice6.py",
        "scratch/test_slice7.py",
    ]
    
    total = len(test_files)
    passed = 0
    
    for tf in test_files:
        print(f"\n---> Running: {tf} ...")
        ret = os.system(f"PYTHONPATH=. ./venv/bin/python {tf}")
        if ret == 0:
            passed += 1
            print(f"[PASS] {tf}")
        else:
            print(f"[FAIL] {tf} (Exit code: {ret})")
            sys.exit(1)
            
    print("\n=================================================================")
    print(f"      TEST RESULTS: {passed}/{total} SLICES PASSED (100% SUCCESS)  ")
    print("=================================================================\n")

if __name__ == "__main__":
    run_all_tests()
