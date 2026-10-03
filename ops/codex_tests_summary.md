Added [backend/tests/test_season_acceptance.py](backend/tests/test_season_acceptance.py) and modified no other source file.

The requested pytest command passes: **6 passed, 1 strict xfail**. The F1 test is xfailed because `run_f1_season` raises `IndexError` when its eight sprint scoring places are applied to the required five-driver field. The engine was left unchanged.